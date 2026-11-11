# Pipeline crawl chạy tự động trên GCP (S2-T05, US-07)

Mỗi đêm 02:00 (giờ Việt Nam) Cloud Scheduler gọi Cloud Run Job `crawl-daily`. Job chạy đúng lệnh
vẫn chạy ở máy, với `--run-type daily`:

    python scripts/crawl.py run --source=itviec --run-type=daily --max-jobs=150

tức ① cập nhật tỷ giá → ② crawl + chuẩn hóa + upsert Supabase → đóng tin hết hạn / bị gỡ (S2-T06)
→ ③ gắn kỹ năng + mức. Mỗi lượt ghi một dòng `ops.crawl_runs` cho từng nguồn.

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

## Chuẩn bị (một lần)

1. Cài [Google Cloud CLI](https://cloud.google.com/sdk/docs/install), rồi `gcloud auth login`.
2. Project GCP đã bật billing. Tài khoản deploy cần vai trò Owner của project (script gán quyền
   IAM cho secret và job, vai trò Editor không làm được).
3. Chuỗi kết nối Supabase loại **Session pooler** (Dashboard → Connect): host
   `aws-…pooler.supabase.com`, cổng 5432, user `postgres.<ref>`. Không dùng "Direct connection"
   (`db.<ref>.supabase.co`): địa chỉ đó chỉ có IPv6, Cloud Run không kết nối được.
4. Có `models/jev_local_v1.joblib` trên máy deploy (file không nằm trên git; xin người đã train
   hoặc chạy `scripts/train_tier2.py`). Thiếu file thì script dừng, xem mục "Model Tầng 2".

## Deploy

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

## Nghiệm thu

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

## Lưu ý vận hành

- **Một nguồn lỗi là cả lượt báo đỏ** (mã thoát 1), các nguồn khác vẫn chạy và vẫn ghi DB.
  Ngày 11/11/2026 trang danh sách VietnamWorks trả 0 link tin
  (`scripts/crawl.py probe --source vietnamworks`), nên mặc định job chỉ chạy `itviec`. Sửa xong
  `config/sources.yaml` thì deploy lại với `CRAWL_SOURCES="itviec vietnamworks"`.
- **Bị chặn (403/429)**: IP của Cloud Run là IP trung tâm dữ liệu, nguồn có thể chặn dù ở máy cá
  nhân vẫn chạy được. Crawler sẽ dừng nguồn đó, không tìm cách vượt (`docs/data_sources.md`).
  Khi gặp, báo nhóm để liên hệ lại nguồn.
- **Model Tầng 2**: phiên bản gắn kỹ năng gồm cả tên model. Image không có model thì phiên bản là
  `…+no-model`, mỗi đêm job gắn lại bằng luật và ghi đè các tin đã gắn bằng model ở máy. Vì vậy
  script không cho deploy khi thiếu file, trừ khi thêm `ALLOW_NO_MODEL=1`.
- **HTML gốc**: mặc định ghi vào đĩa tạm của container và mất sau mỗi lượt;
  `raw.job_snapshots` vẫn giữ JSON-LD gốc. Cần giữ HTML thì tạo bucket và deploy với `RAW_BUCKET`.
- **Đếm "vắng mặt 3 lượt" (S2-T06)** chỉ chạy khi lượt đó đi hết trang danh sách của nguồn.
  Danh sách dài hơn `CRAWL_MAX_JOBS` hoặc `listing.max_pages` thì đêm đó chỉ đóng tin quá hạn và
  tin 404/410.
- **Đổi lịch / tạm dừng**: `gcloud scheduler jobs pause|resume crawl-daily-0200 --location asia-southeast1`.
- **Lỗi quyền ngay sau khi tạo service account** (`… does not exist`): IAM cần vài giây để nhận
  tài khoản mới, chạy lại script là qua.
