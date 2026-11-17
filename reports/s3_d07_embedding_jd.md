# S3-D07: Vector hóa JD theo đoạn ≤ 300 token → core.job_chunks

Ngày 20/11/2026 · Duy · Issue #484 (EN-03 #407) · Model: ADR-004 (bge-m3, Workers AI)

> **Trạng thái:** xong. Đã ghi vector lên production ngày 17/11/2026: 1.441/1.441 tin đang mở
> (100%), 6.130 đoạn, model `cf/baai/bge-m3`. Truy vấn top-10 mất 118 ms (p50).

## 1. Cách làm

| Bước | Ở đâu | Làm gì |
|---|---|---|
| Cắt đoạn | `src/embedding/chunker.py` | summary (tiêu đề · công ty · cấp bậc · hình thức · thẻ kỹ năng D04) + mô tả / yêu cầu / ưu tiên cắt theo dòng, gộp ≤ 300 token (đếm bằng tokenizer bge-m3, tính cả tiền tố "Tiêu đề — Mục:"), chồng lấn 1 dòng; dòng quá dài cắt theo câu rồi theo từ. Bỏ quyền lợi |
| Tính vector | `src/embedding/embedder.py` | `WorkersAIEmbedder` (lô 50, thử lại 429/5xx), `LocalEmbedder` (dự phòng), `FakeEmbedder` (test); 1024 chiều, chuẩn hóa L2 |
| Ghi DB | `src/embedding/store.py` | Chỉ làm tin có tập đoạn (md5 nội dung) hoặc model khác đang lưu, nên không tốn quota cho tin không đổi; mỗi nhóm 20 tin một giao dịch (xóa đoạn cũ → chèn mới); dọn đoạn của tin đóng quá 30 ngày; báo cáo độ phủ + dung lượng |
| Chạy | `scripts/embed_jobs.py` | `--report`, chạy thử, `--apply --prune`, `--knn "câu truy vấn"` (top-10 + thời gian DB) |
| Sau crawl | `ingestion/crawl.py` bước ④ | Sau gắn kỹ năng ③: làm tin mới / đổi + mọi tin mở còn thiếu (bảo đảm 100%); chưa cấu hình token thì bỏ qua; hết quota / lỗi mạng → dừng gọn, lượt sau làm tiếp. Workflow `crawl-daily` truyền `CF_ACCOUNT_ID`, `CF_API_TOKEN`, cache tokenizer |

## 2. Số liệu trên dữ liệu thật (Supabase, chỉ đọc, 20/11/2026)

| Chỉ số | Giá trị |
|---|---|
| Tin đang mở | 1.451 |
| Đoạn cần làm | 6.173 (trung bình 4,3/tin): summary 1.451 · mô tả 2.054 · yêu cầu 1.602 · ưu tiên 1.066 |
| Token | tổng 834.387 · trung vị 112/đoạn · **lớn nhất 300 · vượt 300: 0** |
| Thời gian cắt đoạn toàn kho | 5,7 giây |
| Ước tính quota Workers AI | khoảng 900 neurons (miễn phí 10.000/ngày) |
| Dung lượng ước tính | 6.173 × (2 KB vector + nội dung) + HNSW ≈ 30–40 MB |

Spike chọn model: bge-m3 xếp đúng 9/10 cặp truy vấn Việt ↔ đoạn Anh cùng ý (ADR-004).

## 3. Kiểm tra "xong" (production, 17/11/2026)

| AC | Cách đo | Kết quả |
|---|---|---|
| 100% tin đang mở có vector (#484) | `embed_jobs.py --report` | **1.441/1.441 (100%)** · 6.130 đoạn · bảng 36,9 MB ✓ |
| Tin mới có vector ngay lượt chạy kế tiếp (EN-03 AC2) | bước ④ của `crawl-daily` (secret `CF_ACCOUNT_ID`, `CF_API_TOKEN` đã thêm) + chạy lại không có gì cần làm (`can_lam: 0`) | ✓ (theo dõi log lượt crawl đầu sau merge) |
| Top-10 theo vector ≤ 200 ms (EN-03 AC3) | `embed_jobs.py --knn "…"` (p50 của 5 lần, máy Duy → Supabase Singapore) | **118–119 ms** ✓ |

Lần ghi đầu: 1.438 tin, mất 8 phút 40 giây, phần lớn là thời gian chờ mạng.

Kết quả top-10 thật (trích):

| Truy vấn | Kết quả đầu (cosine) | Nhận xét |
|---|---|---|
| xây dựng pipeline dữ liệu | Data Engineer (Data Pipeline/ Big Data) 0,693 · Senior Data Engineer 0,671 · Data Engineer 0,660 | 9/10 là Data Engineer / Data; 1 tin DevOps |
| kiểm thử tự động | Kỹ Sư Auto Test 0,643 · Trưởng Nhóm Kiểm Thử Tự Động 0,635 · Automation Tester Leader 0,633 | 10/10 là kiểm thử tự động, cả tiêu đề tiếng Anh |
| lập trình backend Java | Backend Developer (Java) 0,711 · Nhân Viên Backend 0,695 · Tech Lead Backend (Java) 0,695 | 10/10 là backend Java |

## Nơi lưu khóa Workers AI

| Nơi chạy | Lưu ở đâu |
|---|---|
| Máy dev | `.env` ở gốc repo (đã gitignore): `CF_ACCOUNT_ID=…`, `CF_API_TOKEN=…`. `scripts/embed_jobs.py` và `ingestion.crawl` tự đọc qua `load_env_file()` |
| GitHub Actions (`crawl-daily`) | Repository secret `CF_ACCOUNT_ID`, `CF_API_TOKEN` |
| API CV trên HF Space (S6-D03) | Space → Settings → Variables and secrets, cùng tên |

Biến môi trường luôn được ưu tiên hơn `.env`. Token chỉ có quyền Workers AI; muốn thu hồi thì xóa ở
Cloudflare → My Profile → API Tokens.

## 4. Kiểm thử

- `tests/unit/test_embedding.py` (12): mọi đoạn ≤ giới hạn, đúng section và số thứ tự, chồng lấn 1
  dòng, không mất dòng nào, dòng siêu dài, summary bỏ giá trị `unknown`, JD chưa tách section; Workers
  AI chia lô + thử lại khi 429 + chuẩn hóa, lỗi 401 / sai số chiều / sai dạng; cấu hình qua biến môi
  trường.
- `tests/integration/test_embedding_pg.py` (pgvector thật): lần đầu ghi 2 tin, độ phủ 100%; chạy lại
  không làm gì; sửa nội dung một tin → chỉ tin đó làm lại; truy vấn `<=>` (HNSW); dọn tin đóng 40
  ngày.
- Lỗi thật tìm ra: toán tử cosine của pgvector nằm trong schema `extensions`, chỉ chạy được khi
  `search_path` có `extensions` (Supabase có, DB khác không) → mọi truy vấn ghi rõ
  `OPERATOR(extensions.<=>)`.
