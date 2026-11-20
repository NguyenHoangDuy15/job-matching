# S3-T08 · Smoke test production trước review Sprint 3 (US-11)

Điều kiện xong: **checklist đạt**. Người chạy: Tùng. Ngày: 19/11/2026, 10:30–11:00 (giờ VN).

**Kết luận:** web, API đọc CV và dữ liệu trên production đều **đạt** (24/24 mục). Có 2 điểm cần
báo ở buổi review: pipeline crawl tự động **chưa chạy theo lịch** (mục 4, V1–V2). Hai điểm này
không làm hỏng chức năng đang có, nhưng dữ liệu đang đứng ở lượt nạp 17/11 và S3-T07 chưa làm được.

## 1. Môi trường

| Thành phần | Giá trị |
| --- | --- |
| Code | `main` tại `cd49572` (#676). Code web và API không đổi từ #675, bản S3-H06 đã test hôm qua |
| Web | https://jobmatch-web.dtt-jobmatch.workers.dev (Cloudflare Workers) |
| API đọc CV | https://jobmatch-cv-api.onrender.com (Render Free) |
| Database | Supabase dùng chung, Postgres 17.11, migration 0001 → 0015 |
| Cách kiểm | `curl` (HTTP code, thời gian, nội dung), trình duyệt (chuyển hướng phía client), SQL **chỉ đọc** (`read_only`), trang GitHub Actions công khai |

Không ghi gì vào production khi chạy smoke test. Không dùng tài khoản thật.

## 2. Checklist

### Web (khách, chưa đăng nhập)

| # | Kiểm | Mong đợi | Thực tế | Đạt |
| --- | --- | --- | --- | --- |
| W1 | Mở `/` | 200, tiêu đề JobMatch | 200, 0,56 s, "JobMatch – Việc làm IT có giải thích" | Đạt |
| W2 | Tìm `/viec-lam?q=java` | 200, có danh sách tin | 200, 1,60 s, 20 link tin trên trang 1 | Đạt |
| W3 | Lọc theo tỉnh `/viec-lam?tinh=79` | 200, không lỗi | 200, 0,49 s | Đạt |
| W4 | Chi tiết một tin đang mở | 200, đúng chức danh, có thẻ kỹ năng | 200, 0,36 s, "Nhân Viên Thiết Kế Đồ Họa · Công ty CP Kids Plaza", có nhãn "Ưu tiên" | Đạt |
| W5 | Link tin đã gộp (S3-H05), `/viec-lam/589d54f1-…` | Sang tin được giữ lại | Trình duyệt chuyển sang `/viec-lam/6ce616bc-…` (tin giữ lại) | Đạt (xem V3) |
| W6 | Tin không tồn tại | Trang "Không tìm thấy việc làm" | Đúng trang, nhưng HTTP 200 (xem V3) | Đạt |
| W7 | `/dang-nhap`, `/dang-ky` | 200 | 200, 0,26 s cả hai | Đạt |
| W8 | Khách mở `/ho-so`, `/admin`, `/hr` | 307 sang `/dang-nhap?next=…` | 307 đúng `next` cho cả ba | Đạt |

### API đọc CV

| # | Kiểm | Mong đợi | Thực tế | Đạt |
| --- | --- | --- | --- | --- |
| A1 | `GET /health` | 200, `warm: true` | 200, 0,29 s, `{"status":"ok","warm":true,"matcher":null}` | Đạt |
| A2 | `POST /cv/parse` không có JWT | 401 | 401 `{"error":"unauthorized"}` | Đạt |
| A3 | `POST /match/jobs` không có JWT | 401 | 401 | Đạt |
| A4 | CORS preflight từ domain web | `access-control-allow-origin` = domain web | Đúng domain web | Đạt |

### Dữ liệu và quyền (SQL chỉ đọc, REST bằng publishable key)

| # | Kiểm | Mong đợi | Thực tế | Đạt |
| --- | --- | --- | --- | --- |
| D1 | Số tin web thấy (`api.v_open_jobs`) | > 0 | 1.392 | Đạt |
| D2 | Tin đang mở có thẻ kỹ năng | ≥ 90% (S2-D06) | 97,1% | Đạt |
| D3 | Tin đang mở có vector (`core.job_chunks`) | 100% (S3-D07) | 100% | Đạt |
| D4 | Trùng chính xác còn lại (URL + dedup hash) | 0 (S3-T03) | 0 | Đạt |
| D5 | Cặp gần trùng đủ điều kiện gộp mà chưa gộp | 0 (S3-T04/T05) | 0 (tính lại bằng `find_near_duplicates` trên 1.431 tin mở) | Đạt |
| D6 | Bất biến gộp: chuỗi gộp / tin gộp chưa đóng / tin gộp còn nguồn | 0 / 0 / 0 | 0 / 0 / 0 | Đạt |
| D7 | `url_norm` còn trống | 0 | 0 / 1.984 nguồn | Đạt |
| D8 | Khách gọi `api.job_redirect` qua REST | Trả public_id tin giữ lại | 200, đúng `6ce616bc-…` | Đạt |
| D9 | Khách đọc `api.v_my_cvs` | Bị chặn | 401 `permission denied` | Đạt |
| D10 | Khách đọc schema `app` | Không lộ ra REST | 406 `Invalid schema: app` | Đạt |

### Vận hành

| # | Kiểm | Mong đợi | Thực tế | Đạt |
| --- | --- | --- | --- | --- |
| O1 | CI | Xanh | Lượt CI gần nhất (#182) xanh | Đạt |
| O2 | `post-ingest` theo lịch | Chạy và xanh | Lượt theo lịch 19/11 09:45 VN xanh (5/6 lượt xanh) | Đạt |

### Luồng đã đăng nhập

Luồng tải CV → xác nhận hồ sơ → Hồ sơ của tôi (CV chính, xóa, giới hạn 5 CV, đăng xuất) đã test
đủ trên production ngày 18/11 ở `docs/qa/s3_h06_e2e_cv.md` (11/11 TC đạt). Từ đó tới nay chỉ có
#676 (tài liệu), web và API không đổi, nên lần này **không chạy lại**. Cần chạy lại nếu có PR web /
API nào merge trước buổi review.

## 3. Lệnh đã chạy

```bash
W=https://jobmatch-web.dtt-jobmatch.workers.dev; A=https://jobmatch-cv-api.onrender.com
curl -s -o /dev/null -w "%{http_code} %{time_total}s %{redirect_url}\n" "$W/viec-lam?q=java"
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$A/cv/parse"
curl -s -D - -o /dev/null -X OPTIONS -H "Origin: $W" -H "Access-Control-Request-Method: POST" "$A/cv/parse"
```

D4 cùng cách tính với `REMAINING_SQL` trong `src/ingestion/dedup_pg.py`. D5: `ingestion.near_dedup.find_near_duplicates`
trên `ingestion.dedup_pg.load_open_docs`, kết nối `read_only`. D6, D7:

```sql
-- D6: chuỗi gộp; tin đã gộp chưa đóng hoặc còn giữ nguồn (cả ba phải bằng 0)
select count(*) from core.jobs d join core.jobs k on k.id = d.duplicate_of
 where k.duplicate_of is not null;
select count(*) from core.jobs where duplicate_of is not null and status <> 'closed';
select count(*) from core.jobs d
 where d.duplicate_of is not null
   and exists (select 1 from core.job_sources s where s.job_id = d.id);
-- D7: nguồn chưa có url_norm
select count(*) from core.job_sources where url_norm is null;
```

## 4. Vấn đề phát hiện

| # | Mức | Vấn đề | Bằng chứng | Đề xuất |
| --- | --- | --- | --- | --- |
| V1 | **Cần báo ở review** | `crawl-daily` (02:00) **chưa từng chạy theo lịch**. Workflow có trên `main` từ 11/11, nhưng trang Actions chỉ có 2 lượt, đều là chạy tay 11/11 và đều lỗi (ITviec trả 403). `ops.crawl_runs` không có dòng `run_type = 'daily'` nào. Lượt nạp gần nhất là TopCV chạy tay 17/11 10:24 | Actions → crawl-daily: "2 workflow runs"; `select … from ops.crawl_runs order by id desc` | Duy (chủ repo) xem trang workflow có bị tắt không, tắt rồi bật lại workflow. Đổi nguồn mặc định khỏi `itviec` (đang bị 403) sang nguồn còn crawl được. Khi chưa có crawl, bước gần trùng cũng không tự chạy |
| V2 | **Cần báo ở review** | `topcv-self-hosted`: mọi lượt theo lịch đều **skipped** (31 lượt, gần nhất 19/11 05:35 VN) vì chưa bật `vars.TOPCV_SCHEDULE_ENABLED`. Không có crawl hằng giờ nào, nên **S3-T07 (theo dõi 24 giờ crawl hằng giờ) chưa làm được** | Actions → topcv-self-hosted; `ops.crawl_runs` không có dòng `hourly` | Bật variable sau khi runner self-hosted sẵn sàng, rồi mới bắt đầu tính 24 giờ cho S3-T07 |
| V3 | Nhỏ | Link tin đã gộp trả **HTTP 200** rồi chuyển trang bằng JavaScript (`NEXT_REDIRECT` trong luồng RSC), không phải 307. Người dùng vẫn đến đúng tin; công cụ không chạy JS (bot, `curl`, xem trước link) thì thấy "Không tìm thấy". Trang tin không tồn tại cũng trả 200 thay vì 404. Nguyên nhân có thể là `viec-lam/[id]/loading.tsx` làm trang stream trước khi kịp đổi status | `curl -D -` trả `HTTP/2 200`, thân trang có `NEXT_REDIRECT;replace;/viec-lam/6ce616bc-…;307` | Không chặn review. Mở issue cho web (Thịnh) |
| V4 | Thông tin | `/match/jobs` trên Render chưa bật: `/health` có `"matcher": null` vì chưa đặt `MATCHER_DATABASE_URL` | `src/api/main.py` (`setup_matcher`) | Việc của S4, không thuộc review Sprint 3 |
| V5 | Thông tin | 17 cặp nghi trùng đang chờ admin, web chưa có màn duyệt | `core.dedup_candidates` | Cần màn duyệt cho admin: `api.admin_resolve_dedup` đòi JWT vai trò admin nên không gọi được từ SQL Editor. Luật xử lý trùng: `docs/runbook/dedup.md` |
