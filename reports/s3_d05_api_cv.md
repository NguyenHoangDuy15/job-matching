# S3-D05: API `POST /cv/parse` trả hồ sơ ≤ 15 giây

Ngày 18/11/2026 · Duy · Issue #474 (US-12 #403) · `src/api`, migration `0009_cv_parse.sql`

## Kết quả

### Đo tại máy (API thật + tiến trình đọc CV thật, Supabase giả lập độ trễ tải file 300 ms)

```
$ uv run python scripts/bench_cv_api.py local --rounds 3
khởi động + nạp mô hình (1 tiến trình): 1.07 giây
POST /cv/parse (10 CV × 3 lượt): {"n": 30, "p50_s": 0.372, "p95_s": 0.489, "max_s": 0.498, "under_15s": 30}
```

**30/30 request dưới 15 giây**, p95 = 0,49 giây. Phần lớn thời gian còn lại khi triển khai thật là
mạng tới Supabase (claim → tải file → lưu: 3 lần gọi).

### Image Docker (chạy với user 1000 như Hugging Face Spaces)

| Chỉ số | Giá trị |
|---|---|
| Từ lúc chạy container đến `/health` báo `warm: true` | **2,3 giây** |
| RAM khi đã nạp mô hình (1 tiến trình đọc CV) | khoảng 200 MB |
| Kích thước image | khoảng 2,7 GB (spaCy, Presidio, pdfplumber, pandas, scikit-learn dùng chung với crawl) |

Chạy container đã bắt được một lỗi thật: image thiếu `db/seed/` (bộ che PII đọc bảng 34 tỉnh từ
đó), tiến trình đọc CV chết lúc nạp. Đã sửa Dockerfile và thêm `tests/unit/test_dockerfile.py`.

### Triển khai thật

Chưa đo: cần Tùng áp migration 0009 lên Supabase và tạo Hugging Face Space (`docs/deploy/cv-api.md`).
Sau đó chạy `scripts/bench_cv_api.py url <cv_id>...` với tài khoản thử và cập nhật mục này.

## Kiểm thử

| Bộ | Kết quả |
|---|---|
| `tests/unit/test_api_cv.py` (14) | Trả hồ sơ + gọi đúng thứ tự claim → tải file → lưu, mọi lệnh gọi Supabase mang JWT người dùng; chỉ văn bản đã che PII được gửi đi; token sai/hết hạn/sai `aud`/sai `iss` → 401, tài khoản khóa → 403, không gọi Supabase; CV không thấy → 404; đang đọc → 409; PDF scan → 422 + `message_vi`, CV đánh dấu `failed`; `cv_id` sai định dạng → 422; quá 10 lần/phút → 429; **timeout cứng với tiến trình thật** → 504, tiến trình treo bị kill và thay mới, request sau vẫn chạy |
| `db/tests/rls_test.sql` (71, thêm 8) | Người B không nhận / không ghi được CV của A; hai lần nhận liên tiếp bị từ chối; lưu hồ sơ ghi kỹ năng (slug lạ bị bỏ), số năm, chức danh, `parsed`; đọc lại thay dòng máy tạo nhưng **giữ dòng người dùng tự thêm**; file lỗi ghi `failed` + mã lỗi |
| Toàn bộ `pytest` | 703 passed, 17 skipped |

## Thiết kế

- **Xác thực**: JWT Supabase ký ES256, khóa công khai từ JWKS (`/auth/v1/.well-known/jwks.json`),
  kiểm `exp`, `iss`, `aud = authenticated`, `account_status = active`. Không cần JWT secret.
- **Không giữ bí mật, RLS làm việc phân quyền**: API gọi Supabase (RPC + Storage) bằng chính JWT
  người dùng. 3 RPC `security invoker` trong migration 0009:
  - `claim_cv_parse`: nhận CV, chống hai request chạy song song; lần đọc kẹt quá 2 phút được nhận lại;
  - `save_cv_profile`: một giao dịch, tra `skill_id` theo slug;
  - `fail_cv_parse`.
- **Timeout cứng**: chuỗi đọc CV (D01 → D03 → D02 → D04, `cvparser.pipeline.parse_cv`) chạy trong
  tiến trình riêng đã nạp sẵn mô hình; quá 10 giây thì kill và thay tiến trình (thread không ngắt
  được PDFium).
- **Không lộ dữ liệu**: chỉ văn bản đã che PII được lưu và trả về; log chỉ có `cv_id`, mã lỗi,
  thời gian; kết quả lỗi không chứa nội dung file.
- **Nơi chạy**: Hugging Face Spaces (Docker), vì Cloud Run cần thẻ thanh toán nhóm không có; image
  giữ tương thích Cloud Run (`$PORT`). Workflow `cv-api-image` build và đẩy image lên GHCR rồi
  khởi động lại Space; `cv-api-keepwarm` ping 12 giờ một lần để Space không ngủ.

## Để sau

- Đo trên triển khai thật (mục trên).
- Giới hạn tần suất đang theo từng tiến trình (bộ nhớ); nhiều instance cần bộ đếm chung.
- HR đọc CV ứng viên (cùng RPC, RLS `cvs_hr` đã cho phép) và đọc theo lô: S6-T02 / S6-D03 dùng lại
  `cvparser.pipeline.parse_cv` và `api.worker.ParsePool`.
