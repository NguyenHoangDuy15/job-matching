# API đọc CV `POST /cv/parse` (S3-D05, US-12)

Người dùng tải CV lên Storage (S3-H01) → web gọi API này → API đọc CV, che PII, tách section,
gán kỹ năng + mức bằng chứng, ghi `app.cvs` / `app.cv_skills` → trả hồ sơ JSON cho màn xác nhận
(S3-H02).

```
Trình duyệt ──(JWT người dùng)──► API (Hugging Face Space, Docker)
                                    ├─ xác thực JWT ES256 qua JWKS của Supabase
                                    ├─ api.claim_cv_parse      ┐
                                    ├─ tải file từ Storage      │ đều bằng JWT người dùng:
                                    ├─ đọc CV (tiến trình riêng, timeout 10 giây)
                                    └─ api.save_cv_profile     ┘ RLS chặn CV người khác
```

**API không giữ khóa bí mật nào**: không có `service_role`, không có mật khẩu DB. Biến môi trường
chỉ gồm thông tin công khai.

## Vì sao Hugging Face Spaces, không phải Cloud Run

Backlog ghi Cloud Run, nhưng Cloud Run bắt buộc project GCP gắn thẻ thanh toán (lý do pipeline
crawl đã chuyển sang GitHub Actions, xem `crawl-job.md`). GitHub Actions không chạy được dịch vụ
web thường trực. Hugging Face Spaces (Docker) miễn phí, không cần thẻ, 2 vCPU / 16 GB RAM, chỉ ngủ
sau 48 giờ không có request (workflow `cv-api-keepwarm` ping 12 giờ một lần).

Image giữ **tương thích Cloud Run** (cổng lấy từ `$PORT`, không ghi đĩa). Khi có thẻ:

```bash
gcloud run deploy cv-api --image ghcr.io/nguyenhoangduy15/job-matching-api:latest \
  --region asia-southeast1 --allow-unauthenticated --cpu 2 --memory 2Gi --min-instances 0 \
  --set-env-vars SUPABASE_URL=...,SUPABASE_PUBLISHABLE_KEY=...,CORS_ORIGINS=...
```

## Cài đặt (một lần)

| # | Việc | Ai |
|---|---|---|
| 1 | Áp `db/migrations/0009_cv_parse.sql` lên Supabase (SQL Editor, hoặc `psql "$DATABASE_URL" -f ...`) | Tùng |
| 2 | Merge PR lên `main` → workflow `cv-api-image` build image `ghcr.io/nguyenhoangduy15/job-matching-api` | tự động |
| 3 | GitHub → trang cá nhân → Packages → `job-matching-api` → Package settings → **Change visibility: Public** (để Space kéo được image) | Duy (chủ repo) |
| 4 | Tạo tài khoản Hugging Face → **New Space** → SDK **Docker** → Blank → **Public**. Đặt tên `jobmatch-cv-api` | Tùng |
| 5 | Đưa 2 file trong `deploy/hf-space/` (`Dockerfile`, `README.md`) vào repo của Space (Files → Add file → Upload) | Tùng |
| 6 | Space → Settings → **Variables** (không phải Secrets, đều là giá trị công khai): `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `CORS_ORIGINS` = domain web + `http://localhost:3000`, cách nhau dấu phẩy | Tùng |
| 7 | Space build xong: mở `https://<tài-khoản>-jobmatch-cv-api.hf.space/health`, phải thấy `{"status":"ok","warm":true}` | Tùng |
| 8 | GitHub repo → Settings → Secrets and variables → Actions: secret `HF_TOKEN` (HF → Settings → Access Tokens, quyền **Write**); variables `HF_SPACE` = `<tài-khoản>/jobmatch-cv-api`, `CV_API_URL` = URL ở bước 7 | Tùng / Duy |
| 9 | Web: biến `NEXT_PUBLIC_CV_API_URL` = URL ở bước 7 (Cloudflare + `.env.local`) | Thịnh |

Biến môi trường khác (mặc định đã ổn): `PARSE_WORKERS` (1), `PARSE_TIMEOUT_S` (10),
`RATE_LIMIT_PER_MINUTE` (10).

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
API_URL=https://<tài-khoản>-jobmatch-cv-api.hf.space CV_TOKEN=<JWT tài khoản thử> \
  uv run python scripts/bench_cv_api.py url <cv_id_1> <cv_id_2> ...
```

`CV_TOKEN`: đăng nhập web bằng tài khoản thử → DevTools → Application → Cookies/Local Storage →
`access_token`. Không commit token. Mỗi CV trả HTTP 200 và ≤ 15 giây.
