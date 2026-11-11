# Pipeline crawl chạy tự động 02:00 hằng ngày (S2-T05, US-07)

Mỗi đêm 02:00 (giờ Việt Nam) workflow GitHub Actions `crawl-daily`
(`.github/workflows/crawl-daily.yml`) chạy đúng lệnh vẫn chạy ở máy:

    python scripts/crawl.py run --source=itviec --run-type=daily --max-jobs=150

tức ① cập nhật tỷ giá → ② crawl + chuẩn hóa + upsert Supabase → đóng tin hết hạn / bị gỡ (S2-T06)
→ ③ gắn kỹ năng + mức. Mỗi lượt ghi một dòng `ops.crawl_runs` cho từng nguồn.

## Vì sao GitHub Actions, không phải Cloud Run Job

Kế hoạch ban đầu của S2-T05 là Cloud Run Job + Cloud Scheduler + Secret Manager. Các dịch vụ này
bắt buộc project GCP gắn tài khoản thanh toán (thẻ), dù chi phí của một job mỗi ngày gần như bằng
0. Nhóm không có tài khoản thanh toán, nên chuyển sang GitHub Actions:

| Yêu cầu | Cloud Run (kế hoạch) | GitHub Actions (đang dùng) |
|---|---|---|
| Chạy lệnh crawl theo lô | Cloud Run Job | Job `crawl` trên runner `ubuntu-latest` |
| Lịch 02:00 hằng ngày | Cloud Scheduler | `on.schedule` cron `0 19 * * *` (UTC) |
| Giữ bí mật `DATABASE_URL` | Secret Manager | GitHub Secrets |
| Cần thẻ thanh toán | Có | Không |

Đánh đổi của GitHub Actions:

- **Giờ chạy không chính xác**: lịch có thể trễ vài chục phút khi GitHub quá tải. Crawl hằng đêm
  chấp nhận được.
- **Tự tắt khi repo không hoạt động**: ở repo public, workflow theo lịch tự tắt sau 60 ngày repo
  không có hoạt động. Bật lại ở tab Actions → crawl-daily → Enable workflow.
- **Lịch chỉ chạy trên nhánh `main`**: workflow chỉ có hiệu lực sau khi PR được merge.
- **Repo private** dùng hạn mức phút miễn phí của chủ repo; repo public không tính phút.

Dockerfile và `scripts/deploy_crawl_job.sh` vẫn giữ để chuyển sang GCP khi có billing (mục cuối).

## Cài đặt (một lần)

1. Lấy chuỗi kết nối Supabase loại **Session pooler** (Dashboard → Connect): host
   `aws-…pooler.supabase.com`, cổng 5432, user `postgres.<ref>`. Không dùng "Direct connection"
   (`db.<ref>.supabase.co`): địa chỉ đó chỉ có IPv6, runner GitHub không kết nối được. Mật khẩu có
   ký tự đặc biệt (`@`, `#`, `/`…) thì mã hóa URL, ví dụ `@` thành `%40`.
2. Trên GitHub: repo → Settings → Secrets and variables → Actions → **New repository secret**,
   tên `DATABASE_URL`, giá trị là chuỗi ở bước 1. Cần quyền admin repo (nhờ chủ repo nếu thiếu).
3. Merge PR có file `.github/workflows/crawl-daily.yml` vào `main`.

## Chạy tay và nghiệm thu

DoD: *pipeline chạy thành công trên cloud; lịch tự động 02:00 được kích hoạt.*

1. Tab **Actions** → **crawl-daily** → **Run workflow** (nhánh `main`, giữ mặc định) → chờ xanh.
   Log bước "Crawl, upsert, …" có dòng `KẾT QUẢ itviec: success …`.
2. Lịch đang bật: ở trang workflow crawl-daily không có thông báo "This scheduled workflow is
   disabled", và file workflow có `cron: "0 19 * * *"`.
3. Kiểm trên DB (lượt chạy tay ghi `run_type = 'manual'`, lượt theo lịch ghi `'daily'`):

       select id, source_id, run_type, status, started_at, finished_at,
              items_seen, items_new, items_updated, items_closed, error_sample
         from ops.crawl_runs order by id desc limit 5;

Bằng chứng cho PR / tab AC: link lượt chạy tay ở bước 1, và sáng hôm sau link lượt chạy có nhãn
"scheduled" cùng dòng `ops.crawl_runs` có `run_type = 'daily'`, `started_at` từ 19:00 UTC
(= 02:00 giờ Việt Nam) trở đi.

Chạy tay với nguồn khác: ô `sources` nhận nhiều nguồn cách nhau bằng dấu cách, ví dụ
`itviec vietnamworks`; ô `max_jobs` là số tin tối đa mỗi nguồn.

## Lưu ý vận hành

- **Một nguồn lỗi là cả lượt báo đỏ**, các nguồn khác vẫn chạy và vẫn ghi DB. Ngày 11/11/2026 trang
  danh sách VietnamWorks trả 0 link tin (`scripts/crawl.py probe --source vietnamworks`), nên lịch
  chỉ chạy `itviec`. Sửa xong `config/sources.yaml` thì đổi `'itviec'` trong biến `SOURCES` của
  workflow thành `'itviec vietnamworks'`.
- **Bị chặn (403/429)**: runner GitHub dùng IP trung tâm dữ liệu, nguồn có thể chặn dù ở máy cá
  nhân vẫn chạy được. Crawler sẽ dừng nguồn đó, không tìm cách vượt (`docs/data_sources.md`).
  Khi gặp, báo nhóm để liên hệ lại nguồn.
- **Model Tầng 2** (`models/jev_local_v1.joblib`) không nằm trên git, nên workflow gắn kỹ năng chỉ
  bằng luật (phiên bản `…+no-model`). Ngày 11/11/2026 toàn bộ `core.job_skills` cũng là `no-model`.
  Khi nhóm muốn dùng model trên cloud thì phải đưa model lên (ví dụ GitHub Release) và tải về trong
  workflow; nếu không, mỗi đêm workflow sẽ gắn lại và ghi đè kết quả gắn bằng model ở máy.
- **HTML gốc** ghi vào đĩa tạm của runner và mất sau mỗi lượt; `raw.job_snapshots` vẫn giữ JSON-LD
  gốc. Không tải HTML lên artifact vì artifact của repo public ai cũng tải được.
- **Đếm "vắng mặt 3 lượt" (S2-T06)** chỉ chạy khi lượt đó đi hết trang danh sách của nguồn.
  Danh sách dài hơn `max_jobs` hoặc `listing.max_pages` thì đêm đó chỉ đóng tin quá hạn và tin
  404/410.
- **Tạm dừng lịch**: tab Actions → crawl-daily → "…" → Disable workflow.

## Phương án GCP: Cloud Run Job (khi có billing)

| Thành phần | Tên | Ghi chú |
|---|---|---|
| Image | `asia-southeast1-docker.pkg.dev/<project>/job-matching/pipeline:<commit>` | `Dockerfile` ở gốc repo, build bằng Cloud Build |
| Cloud Run Job | `crawl-daily` (asia-southeast1) | 1 task, không tự chạy lại, timeout 1 giờ, 1 CPU / 1 GiB |
| Cloud Scheduler | `crawl-daily-0200` | `0 2 * * *`, múi giờ `Asia/Ho_Chi_Minh` |
| Secret Manager | `job-matching-database-url` | Job nhận qua biến môi trường `DATABASE_URL` |
| Service account | `crawl-job@…` | Chạy job; chỉ đọc được secret trên |
| Service account | `crawl-scheduler@…` | Scheduler dùng; chỉ có quyền chạy job `crawl-daily` |

Vì sao Cloud Run Job + Cloud Scheduler: pipeline là một lệnh chạy theo lô mỗi ngày một lần, không
cần server bật cả ngày và chưa cần Airflow (ADR-003). Đánh đổi: không có giao diện xem phụ thuộc
giữa các bước; ba bước nằm trong một tiến trình, bước nào lỗi thì cả lượt báo đỏ.

### Chuẩn bị (một lần)

1. Cài [Google Cloud CLI](https://cloud.google.com/sdk/docs/install), rồi `gcloud auth login`.
2. Project GCP đã bật billing. Tài khoản deploy cần vai trò Owner của project (script gán quyền
   IAM cho secret và job, vai trò Editor không làm được).
3. Chuỗi kết nối Supabase loại **Session pooler** (Dashboard → Connect): host
   `aws-…pooler.supabase.com`, cổng 5432, user `postgres.<ref>`. Không dùng "Direct connection"
   (`db.<ref>.supabase.co`): địa chỉ đó chỉ có IPv6, Cloud Run không kết nối được.
4. Có `models/jev_local_v1.joblib` trên máy deploy (file không nằm trên git; xin người đã train
   hoặc chạy `scripts/train_tier2.py`). Thiếu file thì script dừng, xem mục "Model Tầng 2".

### Deploy

Từ gốc repo, bằng Git Bash (Windows) hoặc bash:

    PROJECT_ID=<project> DATABASE_URL='postgresql://postgres.<ref>:<mật khẩu>@aws-…pooler.supabase.com:5432/postgres' \
      bash scripts/deploy_crawl_job.sh

Script chạy lại được nhiều lần: API, kho image, service account, secret đã có thì giữ; mỗi lần chỉ
build image mới (tag = mã commit) và cập nhật job + lịch. Những lần sau không cần `DATABASE_URL`.

Xem trước các lệnh mà không gọi GCP: `DRY_RUN=1 PROJECT_ID=demo ALLOW_NO_MODEL=1 DATABASE_URL=x bash scripts/deploy_crawl_job.sh`.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `CRAWL_SOURCES` | `itviec` | Các nguồn, cách nhau bằng dấu cách |
| `CRAWL_MAX_JOBS` | `150` | Số tin tối đa mỗi nguồn mỗi đêm |
| `SCHEDULE`, `TIME_ZONE` | `0 2 * * *`, `Asia/Ho_Chi_Minh` | Lịch chạy |
| `TASK_TIMEOUT`, `MEMORY` | `3600s`, `1Gi` | Tăng khi nâng `CRAWL_MAX_JOBS` hoặc thêm nguồn |
| `UPDATE_SECRET=1` | | Ghi phiên bản mới cho secret từ `DATABASE_URL` (đổi mật khẩu DB) |
| `RAW_BUCKET` | | Bucket GCS gắn vào `/app/data/raw` để giữ HTML gốc |
| `REGION`, `JOB_NAME`, `SCHEDULER_NAME`, `SECRET_NAME`, `AR_REPO`, `TAG` | | Đổi tên / vùng |

### Nghiệm thu

DoD: *Cloud Run Job chạy thành công trên GCP; lịch tự động 02:00 được kích hoạt.*

    # 1. Chạy thử ngay, chờ kết quả (thoát mã 0 = thành công)
    gcloud run jobs execute crawl-daily --region asia-southeast1 --wait

    # 2. Các lượt gần nhất và trạng thái. Log chi tiết: Console → Cloud Run → Jobs → crawl-daily
    #    → Logs, mỗi nguồn có dòng "KẾT QUẢ <nguồn>: success ..."
    gcloud run jobs executions list --job crawl-daily --region asia-southeast1 --limit 3

    # 3. Lịch đang bật: in ra "ENABLED  0 2 * * *  Asia/Ho_Chi_Minh"
    gcloud scheduler jobs describe crawl-daily-0200 --location asia-southeast1 \
      --format 'value(state,schedule,timeZone)'

    # 4. Thử đúng đường Scheduler → job (không cần chờ tới 02:00)
    gcloud scheduler jobs run crawl-daily-0200 --location asia-southeast1

Trên DB, lượt chạy tự động có `run_type = 'daily'`:

    select id, source_id, run_type, status, started_at, finished_at,
           items_seen, items_new, items_updated, items_closed, error_sample
      from ops.crawl_runs order by id desc limit 5;

Bằng chứng cho PR / tab AC: ảnh hoặc log của bước 1, kết quả bước 3, và sáng hôm sau một dòng
`ops.crawl_runs` có `run_type = 'daily'`, `started_at` quanh 19:00 UTC (= 02:00 giờ Việt Nam).

### Lưu ý riêng của GCP

- **Model Tầng 2**: phiên bản gắn kỹ năng gồm cả tên model. Image không có model thì phiên bản là
  `…+no-model`, mỗi đêm job gắn lại bằng luật và ghi đè các tin đã gắn bằng model ở máy. Vì vậy
  script không cho deploy khi thiếu file, trừ khi thêm `ALLOW_NO_MODEL=1`.
- **HTML gốc**: mặc định ghi vào đĩa tạm của container và mất sau mỗi lượt;
  `raw.job_snapshots` vẫn giữ JSON-LD gốc. Cần giữ HTML thì tạo bucket và deploy với `RAW_BUCKET`.
- **Đổi lịch / tạm dừng**: `gcloud scheduler jobs pause|resume crawl-daily-0200 --location asia-southeast1`.
- **Lỗi quyền ngay sau khi tạo service account** (`… does not exist`): IAM cần vài giây để nhận
  tài khoản mới, chạy lại script là qua.
