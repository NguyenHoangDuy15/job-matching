# API đọc CV `POST /cv/parse` (S3-D05, US-12)

Người dùng tải CV lên Storage (S3-H01) → web gọi API này → API đọc CV, che PII, tách section,
gán kỹ năng + mức bằng chứng, ghi `app.cvs` / `app.cv_skills` → trả hồ sơ JSON cho màn xác nhận
(S3-H02).

```
Trình duyệt ──(JWT người dùng)──► API (Render, Docker image từ GHCR)
                                    ├─ xác thực JWT ES256 qua JWKS của Supabase
                                    ├─ api.claim_cv_parse      ┐
                                    ├─ tải file từ Storage      │ đều bằng JWT người dùng:
                                    ├─ đọc CV (tiến trình riêng, timeout 10 giây)
                                    └─ api.save_cv_profile     ┘ RLS chặn CV người khác
```

**API không giữ khóa bí mật nào**: không có `service_role`, không có mật khẩu DB. Biến môi trường
chỉ gồm thông tin công khai.

## Chạy ở đâu: Render (miễn phí)

| Nơi | Vì sao không / có |
|---|---|
| Cloud Run (backlog) | Bắt buộc project GCP gắn thẻ thanh toán (lý do pipeline crawl chuyển sang GitHub Actions, xem `crawl-job.md`) |
| Hugging Face Spaces | Từ 7/2026 tài khoản miễn phí **không tạo được Docker Space** nữa (chỉ còn Static) |
| GitHub Actions | Không chạy được dịch vụ web thường trực |
| **Render, gói Free** | Chạy thẳng image GHCR có sẵn, 512 MB RAM / 0,1 CPU, 750 giờ/tháng (đủ chạy liên tục 1 dịch vụ), ngủ sau 15 phút không có request |

Đo trên máy dev (11/2026): API sau khi nạp mô hình dùng ~260 MB RAM; một CV mẫu tốn tối đa 0,35 giây
CPU → ở 0,1 CPU cỡ 3–4 giây, dưới mức 15 giây của US-12. Khởi động lạnh (nạp spaCy/Presidio) ở 0,1 CPU
mất vài phút, nên workflow `cv-api-keepwarm` ping `/health` 10 phút một lần để dịch vụ không ngủ.

Image giữ **tương thích Cloud Run** (cổng lấy từ `$PORT`, không ghi đĩa). Khi có thẻ:

```bash
gcloud run deploy cv-api --image ghcr.io/nguyenhoangduy15/job-matching-api:latest \
  --region asia-southeast1 --allow-unauthenticated --cpu 2 --memory 2Gi --min-instances 0 \
  --set-env-vars SUPABASE_URL=...,SUPABASE_PUBLISHABLE_KEY=...,CORS_ORIGINS=...
```

Render có khi đòi thêm thẻ để "xác minh tài khoản" dù chọn gói Free; gói Free không bị trừ tiền.
Không ai có thẻ thì: chạy image trên máy trong nhóm + Cloudflare Tunnel để demo (URL đổi mỗi lần
chạy lại). Koyeb (đã về Mistral từ 2/2026) và Fly.io đều bắt buộc thẻ; Back4App Free chỉ 256 MB RAM,
không đủ cho API (~260 MB khi rảnh).

## Cài đặt (một lần)

| # | Việc | Ai |
|---|---|---|
| 1 | Áp `db/migrations/0009_cv_parse.sql` rồi `0010_cv_profile_confirm.sql` lên Supabase (SQL Editor). Chạy lại 0010 nếu lỡ chạy 0009 sau nó | Tùng |
| 2 | Merge PR lên `main` → workflow `cv-api-image` build image `ghcr.io/nguyenhoangduy15/job-matching-api` | tự động |
| 3 | GitHub → trang cá nhân → Packages → `job-matching-api` → Package settings → **Change visibility: Public** (để Render kéo được image không cần đăng nhập) | Duy (chủ repo) |
| 4 | render.com → đăng nhập bằng GitHub → **New → Web Service → Existing Image** → `ghcr.io/nguyenhoangduy15/job-matching-api:latest` | Tùng |
| 5 | Name `jobmatch-cv-api`, Region **Singapore**, Instance type **Free**. Environment Variables (đều là giá trị công khai): `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `CORS_ORIGINS` = domain web + `http://localhost:3000`, cách nhau dấu phẩy. Advanced → Health Check Path `/health` | Tùng |
| 6 | Deploy xong: mở `https://jobmatch-cv-api.onrender.com/health` (tên có thể thêm hậu tố nếu trùng), phải thấy `{"status":"ok","warm":true}` (lần đầu đợi vài phút) | Tùng |
| 7 | Render → service → Settings → **Deploy Hook** → copy URL | Tùng |
| 8 | GitHub repo → Settings → Secrets and variables → Actions: secret `RENDER_DEPLOY_HOOK` = URL bước 7; variable `CV_API_URL` = URL bước 6 (không có `/health`) | Tùng / Duy |
| 9 | Web: biến `NEXT_PUBLIC_CV_API_URL` = URL ở bước 6 (Cloudflare + `.env.local`) | Thịnh |

Render tự đặt `$PORT`; image đọc biến này nên không cần cấu hình cổng. Biến môi trường khác (mặc
định đã ổn): `PARSE_WORKERS` (1), `PARSE_TIMEOUT_S` (10), `RATE_LIMIT_PER_MINUTE` (10).
Không đặt `PARSE_WORKERS` > 1 trên gói Free: mỗi tiến trình đọc tốn ~190 MB RAM.

## Gọi từ web (S3-H01 / S3-H02)

Sau `api.register_cv` thành công:

```ts
const { data: { session } } = await supabase.auth.getSession();
const res = await fetch(`${process.env.NEXT_PUBLIC_CV_API_URL}/cv/parse`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${session!.access_token}` },
  body: JSON.stringify({ cv_id: cvId }),
});
const body = await res.json();
if (res.ok) router.push(`/ho-so/${cvId}/xac-nhan`);   // body.profile: hồ sơ JSON (S3-D04)
else showError(CV_PARSE_ERRORS[body.error] ?? body.message_vi ?? "Có lỗi khi đọc CV, hãy thử lại.");
```

| HTTP | `error` | Câu cho người dùng |
|---|---|---|
| 401 | `unauthorized` | Phiên đăng nhập đã hết hạn, hãy đăng nhập lại. |
| 403 | `forbidden` | Tài khoản đang bị khóa hoặc chờ duyệt. |
| 404 | `cv_not_found`, `file_not_found` | Không tìm thấy CV, hãy tải lại. |
| 409 | `parse_in_progress` | CV đang được đọc, đợi vài giây rồi tải lại trang. |
| 422 | `ocr_required`, `encrypted`, `corrupt_file`, `unsupported_type`, `unreadable_text`... | Dùng `message_vi` trong body (tiếng Việt, lấy từ bộ trích văn bản) |
| 429 | `rate_limited` | Bạn thao tác quá nhanh, thử lại sau 1 phút. |
| 504 | `timeout` | File quá phức tạp, hãy xuất lại PDF rồi tải lên. |
| 500/502 | `internal_error`, `supabase_error`, `save_failed`, `worker_unavailable` | Có lỗi hệ thống khi đọc CV, hãy thử lại. |

Khi lỗi, `app.cvs.parse_status = 'failed'` và `parse_error` = mã lỗi, nên trang "Hồ sơ CV" hiện
được trạng thái mà không cần gọi lại API.

Phản hồi thành công:

```json
{
  "cv_id": "…", "status": "parsed", "skills_saved": 16,
  "profile": {"target_title": "…", "years_exp": 5.4, "years_ranges": [["2021-07", "present"]],
              "internship_months": 0, "entries": [...],
              "skills": [{"skill_id": "docker", "name": "Docker", "evidence_level": "strong",
                          "evidence": "Triển khai Docker và …", "highlight": [11, 17],
                          "section": "experience", "context": "Công ty …", "years": 3.8}]},
  "warnings": [], "timings_ms": {"extract": 95, "redact": 30, "profile": 8, "total": 1400}
}
```

## Kiểm tra sau khi triển khai

```bash
API_URL=https://jobmatch-cv-api.onrender.com CV_TOKEN=<JWT tài khoản thử> \
  uv run python scripts/bench_cv_api.py url <cv_id_1> <cv_id_2> ...
```

`CV_TOKEN`: đăng nhập web bằng tài khoản thử → DevTools → Application → Cookies/Local Storage →
`access_token`. Không commit token. Mỗi CV trả HTTP 200 và ≤ 15 giây.
