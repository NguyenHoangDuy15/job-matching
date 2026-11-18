# S4-D05 · Hiệu năng `POST /match/jobs`: p95 với 2.000 tin và 5 CV

Ngày 17/11/2026 · Duy · Issue S4-D05 (US-16 #408) · Script: `scripts/perf_match.py`

> **Kết quả:** sau tối ưu, **p95 ≤ 3 s đạt ở mọi kịch bản với 0,5 CPU** (p95 xấu nhất 2,1 s, lượt
> đầu phải vector hóa CV; lượt thường 0,3 s; 5 người đồng thời 0,5 s). Với **0,1 CPU (Render
> Free)**, một người dùng tuần tự đạt (p95 0,9 s) nhưng lượt đầu (3,8 s) và 5 người đồng thời
> (7,4 s) **không đạt**: giới hạn của phần cứng, cần chốt gói máy chủ.

## 1. Cách đo

- Endpoint thật (`api.match`, FastAPI TestClient): kho tin thật qua role `matcher_ro`, nhân lên
  **2.000 tin / 8.505 đoạn**; **5 CV mẫu** (Backend, Data Analyst, Tester, Kỹ sư dữ liệu, BA),
  vector hóa thật bằng Workers AI; kiểm tin còn mở bằng SQL thật.
- Supabase (PostgREST, JWT người dùng) giả lập với độ trễ đo thật từ máy dev: **80 ms mỗi RPC**
  (RTT 44 ms + thời gian chạy hàm), **60 ms mỗi lần mở kết nối HTTPS** (Render và Supabase cùng
  Singapore; từ máy dev ở Việt Nam là 366 ms).
- Kịch bản: lượt đầu (CV chưa có vector), lượt thường (N = 5/10/20/50, có / không bộ lọc), 5
  người gọi đồng thời.
- Cấu hình: máy dev, và Docker giới hạn **0,1 CPU / 512 MB** (Render Free) và **0,5 CPU / 512 MB**
  (Render Starter).

## 2. Kết quả

| Kịch bản · p95 | Máy dev trước | Máy dev sau | 0,1 CPU trước | **0,1 CPU sau** | **0,5 CPU sau** |
|---|---|---|---|---|---|
| Lượt đầu (vector hóa CV) | 2.278 ms | 2.119 ms | 9.002 ms | 3.797 ms | **2.117 ms** |
| Lượt thường, tuần tự | 572 ms | 293 ms | 1.404 ms | **902 ms** | **295 ms** |
| 5 người đồng thời | 465 ms | 410 ms | 15.095 ms | 7.403 ms | **532 ms** |
| Nạp kho tin lúc khởi động | 16 s | 16 s | 174 s | 182 s | 21 s |

Thời gian từng bước, lượt thường, 0,5 CPU (header `Server-Timing`): đọc CV 88 ms · `rank()` 15 ms ·
kiểm tin còn mở 68 ms · ghi lịch sử 89 ms. Ba bước mạng chiếm khoảng 90% thời gian.

## 3. Điểm nghẽn tìm được và cách sửa

| # | Điểm nghẽn (số đo) | Sửa | Tác động |
|---|---|---|---|
| 1 | **BLAS nhiều luồng dưới hạn mức CPU**: nhân ma trận 8.505 × 1024 chậm ~400 lần trên 0,1 CPU (1.009 ms, máy dev 2,3 ms) | `OMP_NUM_THREADS=1` (và OpenBLAS, MKL) trong `Dockerfile` | 1.009 → 360 ms |
| 2 | **Tokenizer bge-m3 ~400 MB RAM**, chỉ để đếm token khi cắt đoạn CV: container 512 MB bị OOM | API đếm bằng ước lượng dư `approx_tokens` (5 CV mẫu: số đoạn không đổi, đoạn lớn nhất 132 token thật) | RAM phần so khớp 289 MB, hết OOM |
| 3 | K, E tính trên toàn kho ở mỗi lượt, kể cả khi chỉ đổi N / bộ lọc | `SignalsCache`: nhớ K, E theo snapshot + nội dung CV | Đổi N / bộ lọc không nhân ma trận lại |
| 4 | Lượt đầu nạp lười từ điển, FlashText, cây kỹ năng, numpy: `rank()` 6,5 s trên 0,1 CPU | `warm_rank()` chạy thử một lượt trước khi API báo sẵn sàng | Lượt đầu 0,1 CPU 9,0 → 3,8 s |
| 5 | M duyệt lại cây kỹ năng ở mỗi kỹ năng, mỗi tin, mỗi lượt | Nhớ quan hệ cây kỹ năng (`_candidates`) | `rank()` máy dev 11,2 → 10,0 ms |
| 6 | Mỗi lượt mở kết nối HTTPS mới tới Supabase (TLS 60–366 ms) | Một `httpx.Client` dùng chung | Bớt 1 lần bắt tay TLS mỗi lượt |
| 7 | Hai RPC nối tiếp `get_cv_for_match` + `get_cv_chunks` | Migration 0014 `api.get_cv_match_input` (thiếu thì tự dùng 2 RPC cũ) | Bớt 1 vòng mạng (~85 ms) |
| 8 | Lượt đầu mở kết nối `matcher_ro` (504 ms) | `MatcherDB.warm()` lúc khởi động | Bớt ~0,5 s lượt đầu |

Thêm header `Server-Timing` (từng bước, ms) để web hiện thời gian phản hồi (S4-H04) và để đo.

## 4. RAM của API đầy đủ (đọc CV + so khớp) trong 512 MB

Chạy đúng image API (uvicorn, `PARSE_WORKERS=1`, mô hình đọc CV nạp sẵn, `MATCHER_DATABASE_URL`)
trong Docker **0,5 CPU / 512 MB**: `/health` báo `warm: true`, `matcher.ready: true` (1.435 tin,
nạp 13,2 s); **RAM 325 MB / 512 MB**, không OOM.

Trước khi bỏ tokenizer bge-m3, phần so khớp (chưa tính đọc CV) đã vượt 512 MB. Lúc làm mới kho
tin mỗi giờ, bản cũ và bản mới cùng nằm trong RAM khoảng vài giây (thêm ~70–140 MB): vẫn dưới
512 MB nhưng không còn nhiều chỗ khi kho tăng lên nhiều lần. **Không cần tách dịch vụ hay nâng RAM
ở quy mô hiện tại**; điều cần chốt là CPU.

## 5. Kết luận, việc cần chốt

- AC p95 ≤ 3 s **đạt với 0,5 CPU**. Với 0,1 CPU chỉ đạt khi một người dùng tuần tự.
- **Đề xuất:** chạy API trên gói có ≥ 0,5 CPU (Render Starter) trong tuần demo, hoặc nghiệm thu
  S4-D05 bằng số đo 0,5 CPU và ghi rõ giới hạn của gói Free.
- Chưa đo trên Render thật (tầng B): cần tài khoản seeker thử có 5 CV và API đã deploy.
- Nạp kho tin lúc khởi động: 21 s (0,5 CPU), 3 phút (0,1 CPU). Trong lúc đó API trả
  `503 engine_warming`; keepwarm giữ máy không ngủ.
