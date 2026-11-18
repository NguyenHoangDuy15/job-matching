# S4-D04 · API `POST /match/jobs`: Top N việc phù hợp

Ngày 17/11/2026 · Duy · Issue #498 (US-16 #408) · Contract: `docs/api/match-jobs.md`

> **Kết quả:** API trả Top N đúng schema `MatchResponse` (AC #498), 14 test API + 10 test
> `rank()` + 12 test RLS mới. Đo đầu cuối trên kho thật qua role `matcher_ro` (1.435 tin) với
> 10 CV mẫu: p50 0,4 s, chậm nhất 1,8 s (lần đầu mở kết nối + vector hóa CV).

## 1. Luồng

1. Đọc hồ sơ CV bằng JWT người dùng: `api.get_cv_for_match` (migration 0013, RLS chủ CV; CV đã
   xác nhận chỉ lấy kỹ năng người dùng giữ lại).
2. Vector CV: đọc `api.get_cv_chunks`; đoạn đổi (sửa hồ sơ) hoặc chưa có thì vector hóa
   (Workers AI) rồi lưu `api.save_cv_chunks`. Lỗi model: E = null, vẫn trả kết quả.
3. `ranking.rank` trên snapshot kho tin trong RAM (`ranking.engine`, nạp qua `matcher_ro` trong
   một giao dịch REPEATABLE READ, làm mới mỗi giờ ở luồng nền):
   lọc cứng (tỉnh, tin remote / không ghi tỉnh luôn qua; hình thức; còn hạn) → top 100 BM25 ∪
   top 100 vector → K, E phân vị toàn kho, M, X → H (chia lại trọng số) → sắp, giải thích ngắn.
4. Kiểm lại Top N + 20 tin dự phòng còn mở NGAY LÚC NÀY (snapshot có thể cũ ≤ 1 giờ), bù tin
   vừa đóng.
5. `api.save_match` ghi `app.match_requests` + `app.match_results` (lỗi: `request_id = null`).

## 2. Đo trên kho thật (`scripts/match_bench.py`, không ghi DB)

| Bước | Thời gian |
|---|---|
| Nạp snapshot (1.435 tin, 6.105 đoạn) | 10,9 s, ở luồng nền lúc khởi động |
| Vector hóa CV lần đầu | 0,25–1,2 s (lần sau đọc từ DB) |
| `rank()` | 14–27 ms (134–158 ứng viên) |
| Kiểm tin còn mở | 73–82 ms (lần đầu 0,6 s: mở kết nối) |
| Tổng | p50 0,4 s · max 1,8 s |

| RAM (tiến trình riêng) | MB |
|---|---|
| Thư viện + từ điển | 82 |
| Sau khi nạp snapshot | 222 (snapshot khoảng 140) |
| Lúc làm mới (bản cũ + bản mới) | đỉnh khoảng 300 |

API hiện tại khoảng 260 MB + tiến trình đọc CV khoảng 190 MB; thêm snapshot khoảng 140–210 MB thì
**vượt 512 MB của Render gói Free**. Cần chọn cách chạy trước khi bật trên Render (PR mục "Cần chốt").

Top 1 của 10 CV mẫu: Backend → Lập Trình Viên Fullstack (87,0); Data Analyst → Trưởng Nhóm Data
Analyst (96,9); Frontend → Lập Trình Viên Angular (80,4); Tester → Nhân Viên Kiểm Thử Phần Mềm
(98,6); DevOps → Cloud Operation/Platform Engineer (85,9); Kỹ sư Dữ liệu → Senior Data Business
Analyst (83,5); UI/UX → Nhân Viên Thiết Kế Đồ Họa (96,8); Mobile → Android Developer Lead (87,0);
BA → Chuyên Viên Business Analyst (86,1); An toàn thông tin → Trưởng Phòng Quản Trị Mạng Và An Ninh
Thông Tin (85,8).

## 3. Hạn chế

- **Tin không có kỹ năng bắt buộc / ưu tiên (M = null) dễ lên đầu**: chia lại trọng số dồn sang
  K, E, mà ứng viên đều có K, E gần 1 (vì được chọn từ top K, top E). Ví dụ "Trưởng Nhóm Data
  Analyst" 96,9 cho CV Data Analyst. Đúng công thức proposal; cần chốt có thêm cổng / phạt nhẹ
  hay không khi có bộ nhãn (US-21).
- Trong tập ứng viên K, E thường 0,9–1,0 nên M quyết định thứ tự; trọng số chưa tinh chỉnh.
- Chưa đo p95 với nhiều người dùng đồng thời (S4-D05).
