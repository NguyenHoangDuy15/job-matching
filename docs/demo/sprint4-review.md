# Sprint 4 Review (Demo 1): checklist AC và kịch bản demo (S4-H06)

- **Thời gian:** thứ 5, 26/11/2026 · code freeze 12:00 · review 14:00 · retro 15:15
- **Người dẫn demo:** Thịnh (Duy trình bày công thức điểm, Tùng trình bày trang Admin)
- **Link production:** https://jobmatch-web.dtt-jobmatch.workers.dev
- **Done khi:** checklist AC mục 1 đạt trên production; giảng viên tự chọn bộ lọc, đọc được cách tính
  điểm và lưu được một việc.

> Không ghi mật khẩu vào file này. Mật khẩu tài khoản demo để ở chỗ an toàn của nhóm.

Mục tiêu Sprint 4: người tìm việc nhận **Top N việc phù hợp với CV**, mỗi việc có **điểm 0–100 giải
thích được bằng 4 thành phần** (Từ khóa, Kỹ năng, Ngữ nghĩa, Kinh nghiệm), **lưu việc** và xem lại
**lịch sử gợi ý**; admin theo dõi **sức khỏe hệ thống** (crawl, thời gian phản hồi, chất lượng dữ liệu).

---

## 0. Chuẩn bị (xong trước giờ review 30 phút)

- [x] Cloudflare → Workers → jobmatch-web → Deployments: bản mới nhất của `main` **Ready** (sau #696).
      Lúc soạn (26/11 sáng) production đã có trang `/viec-da-luu`.
- [x] Đánh thức API: mở https://jobmatch-cv-api.onrender.com/health, đợi tới khi thấy `"warm":true` và
      `"matcher":{"ready":true,…}` (nạp kho tin mất khoảng 40 giây sau khi máy chủ thức). Mở lại ngay
      trước khi demo.
- [x] Tài khoản **seeker demo**: có CV **cv01.pdf** đã đọc xong, đã **Lưu hồ sơ**, là CV chính ★.
      Mở `/viec-phu-hop` một lần để chắc có kết quả. Vào **Việc đã lưu** bỏ hết việc đã lưu cũ.
- [x] Tài khoản **seeker thứ 2** cho giảng viên: có CV **cv02.pdf** đã xác nhận.
- [x] Tài khoản **admin** và **HR** để demo phân quyền.
- [x] Tùng xong S4-T06 (≥ 1.500 tin mở, 0 tin hết hạn trong Top N) và S4-T07 (smoke test production).
- [x] Duy xong S4-D07 (1 trang giải thích công thức điểm), mở sẵn ở một tab.
- [x] Dự phòng: `npm run dev` ở `apps/web` chạy được trên máy, `.env.local` có `NEXT_PUBLIC_CV_API_URL`.

---

## 1. Checklist AC trên production

Đánh dấu khi bấm thử đạt trên production (không phải localhost).

### US-16 · Việc phù hợp với tôi (S4-D01→D05, S4-H01→H04)

- [x] Mở `/viec-phu-hop`: mặc định chọn **CV chính ★**, chỉ liệt kê CV đã đọc xong; đổi sang CV khác được.
- [x] Chọn số việc **5 / 10 / 20 / 50**; lọc **tỉnh** (gõ không dấu, chọn nhiều) và **hình thức**.
- [x] Bấm **Tìm việc phù hợp** mới chấm lại; lựa chọn nằm trên URL, **F5** vẫn giữ nguyên.
- [x] Lọc tỉnh: tin **Remote** và tin **không ghi tỉnh** vẫn có trong kết quả.
- [x] Mỗi thẻ có **điểm 0–100** (1 chữ số thập phân), hạng, **4 thanh K / M / E / X**; thành phần không
      xác định hiện nét đứt "không áp dụng", không vẽ thành 0.
- [x] **Điểm tính thế nào?**: công thức có trọng số; khi bỏ một thành phần thì ghi rõ và trọng số còn lại
      cộng bằng 1; các phần nhân lại cộng ra đúng điểm của thẻ.
- [x] **Kỹ năng khớp** (đậm = có bằng chứng, viền nét đứt = chỉ liệt kê, viền chấm = tự thêm,
      "(qua …)" = khớp qua kỹ năng liên quan) và **CV chưa thể hiện** (bắt buộc / ưu tiên).
- [x] Câu **"Điểm là mức phù hợp theo công thức, không phải xác suất trúng tuyển."** luôn hiện.
- [x] Không có tin hết hạn: mọi thẻ có hạn nộp từ hôm nay trở đi (hoặc không ghi hạn).
- [x] Dòng **"trả lời trong … giây (máy chủ chấm … giây)"**; khi API đã thức, mục tiêu ≤ 3 giây (S4-D05).
- [x] **Xem tin** mở đúng tin; **Ứng tuyển ở trang gốc** mở trang tuyển dụng ở tab mới.
- [x] Ít hơn N tin: tiêu đề "Chỉ có X việc phù hợp". Không có tin: khung rỗng + **Bỏ lọc tỉnh /
      Bỏ lọc hình thức**.
- [x] Đang chấm: thẻ xám giữ chỗ, nút Tìm khóa ("Đang chấm…").
- [x] Lỗi (giả lập bằng `?gia-lap=`): `503` → "Hệ thống đang khởi động" + **Thử lại** ra kết quả;
      `429` → nút "Thử lại sau 60 giây" đếm ngược.
- [x] CV chưa xác nhận hồ sơ: hiện nhắc **Xác nhận hồ sơ** để điểm sát hơn.
- [x] Tài khoản chưa có CV đọc xong: "Bạn cần tải CV để nhận việc phù hợp" + nút Tải CV.

### US-17 · Lưu việc và lịch sử gợi ý (S4-H05, migration 0021)

- [x] **☆ Lưu** trên thẻ Việc phù hợp và trên trang chi tiết tin → **★ Đã lưu**; F5 vẫn giữ.
- [x] Menu **Việc đã lưu** (`/viec-da-luu`): mới lưu ở trên, có công ty, ngày lưu, hạn nộp, Sắp hết hạn.
- [x] **Bỏ lưu**: dòng biến mất ngay, F5 không quay lại.
- [x] Tin hết hạn / bị gỡ vẫn giữ, nhãn **Đã đóng**, không có link, nút "Không còn nhận hồ sơ".
- [x] **10 lần gợi ý gần nhất**: giờ chấm, CV, số việc + bộ lọc, điểm cao nhất; mở xem việc của từng lần.
- [x] **Chấm lại** mở Việc phù hợp với đúng CV, số việc và bộ lọc của lần đó.
- [x] Seeker A không thấy việc đã lưu / lịch sử của seeker B (RLS, `db/tests/rls_test.sql` trong CI).

### US-18 · Trang Admin: sức khỏe hệ thống (S4-T01→T04)

- [x] `/admin` có các thẻ số: Tin đang mở, Tin mới 24 giờ, Tin đóng hôm nay, Người tìm việc, Đăng nhập
      hôm nay, **Lượt gợi ý việc hôm nay**, **Thời gian phản hồi p95**, Chi phí LLM hôm nay.
- [x] Số ngày giờ theo giờ Việt Nam; Lượt gợi ý việc hôm nay tăng sau khi demo chấm điểm (S4-T01).
- [x] Mục **Cảnh báo** đỏ khi có vấn đề (crawl lỗi, không có tin mới…).
- [x] Biểu đồ **Tỉ lệ crawl thành công 7 ngày** và **Thời gian phản hồi p95 7 ngày** (có điểm hôm nay).
- [x] `/admin/crawl-runs`: bảng lịch sử crawl (nguồn, trạng thái, thời lượng, cập nhật, đóng, lỗi HTTP),
      mở được **mẫu lỗi** của một lần chạy.

### US-19 · Chất lượng dữ liệu (S4-T05)

- [x] `/admin` có **Chất lượng dữ liệu lần crawl gần nhất** (đầy đủ, hợp lệ, % lương / tỉnh chuẩn hóa,
      sai schema, độ mới).
- [x] `/admin/crawl-runs` mở được **Chi tiết báo cáo chất lượng** của từng lần chạy.

### Phân quyền

- [x] Khách mở `/viec-phu-hop` hoặc `/viec-da-luu` → chuyển sang đăng nhập, đăng nhập xong quay lại.
- [x] HR mở `/viec-phu-hop`, `/viec-da-luu` → trang 403; trang chi tiết tin không có nút Lưu.
- [x] Seeker mở `/admin` → trang 403.

---

## 2. Kịch bản demo (~15 phút)

| Phút  | Ai làm         | Nội dung            | Nói gì / làm gì                                                                                                                                                                                                                                                                                                                       |
| ----- | -------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0–1   | Thịnh          | Mở đầu              | Sprint 3 máy đã "hiểu" CV (kỹ năng có dẫn chứng). Sprint 4 dùng hồ sơ đó để **gợi ý Top N việc đang mở**, mỗi việc có điểm giải thích được, lưu lại được.                                                                                                                                                                             |
| 1–4   | Duy            | Công thức điểm      | Mở trang giải thích (S4-D07). Lọc cứng (tin còn mở, tỉnh, hình thức) → hợp nhất top 100 BM25 + top 100 vector → chấm `H = 100 × (0,25 K + 0,35 M + 0,30 E + 0,10 X)`. K, E tính theo phân vị toàn kho; M: kỹ năng bắt buộc ×2, ưu tiên ×1, có bằng chứng nặng hơn chỉ liệt kê. Thành phần không xác định thì bỏ và chia lại trọng số. |
| 4–7   | Thịnh          | Việc phù hợp        | Seeker demo → **Việc phù hợp**: CV chính ★, 10 việc. Thẻ #1: điểm, 4 thanh, chip kỹ năng. Mở **Điểm tính thế nào?**, giải thích bằng số: "Kỹ năng tối đa 35 điểm, CV đạt 0,80 nên được 28 điểm…", cộng 4 phần ra đúng điểm. Chỉ câu "không phải xác suất trúng tuyển".                                                                |
| 7–8   | Thịnh          | Bộ lọc, thời gian   | Chọn Hà Nội + Remote, 5 việc → Tìm. Chỉ tin Remote vẫn có dù lọc tỉnh, dòng "trả lời trong … giây". F5: lựa chọn vẫn giữ. Thêm `?gia-lap=503` để chỉ trạng thái lỗi + Thử lại.                                                                                                                                                        |
| 8–10  | **Giảng viên** | Tự thao tác         | Đưa máy (seeker thứ 2): giảng viên chọn tỉnh / số việc, bấm Tìm, mở "Điểm tính thế nào?" của một thẻ, bấm **☆ Lưu** một việc.                                                                                                                                                                                                         |
| 10–12 | Thịnh          | Lưu việc, lịch sử   | Lưu thêm 2 việc ở thẻ và ở trang chi tiết tin → **Việc đã lưu**: danh sách, hạn nộp, Bỏ lưu một việc. Kéo xuống **10 lần gợi ý gần nhất**: các lần vừa chấm, mở xem việc, bấm **Chấm lại** → đúng bộ lọc cũ.                                                                                                                          |
| 12–14 | Tùng           | Admin               | Đăng nhập admin → `/admin`: thẻ số (Lượt gợi ý việc hôm nay vừa tăng), p95, crawl 7 ngày, cảnh báo, chất lượng dữ liệu. `/admin/crawl-runs`: mở mẫu lỗi của một lần chạy và báo cáo chất lượng.                                                                                                                                       |
| 14–15 | Thịnh          | Còn thiếu, Sprint 5 | Nêu mục 4. Sprint 5: **chấm độ khớp CV với một tin cụ thể** và bảng kỹ năng còn thiếu (nút "Chấm độ khớp với CV" trên trang tin), phía HR: đăng JD.                                                                                                                                                                                   |

Số liệu lúc soạn (26/11 sáng): 1.466 tin đang mở; API nạp kho 1.466 tin trong 38,9 giây.

---

## 3. Nếu có sự cố

| Sự cố                                             | Cách xử lý                                                                                                                                                         |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| "Chấm điểm lâu hơn bình thường" (quá 30 giây)     | API Render vừa thức, đang nạp kho tin. Mở `/health` ở tab khác, đợi `matcher.ready: true` (khoảng 40 giây), bấm **Thử lại**. Nói rõ: gói miễn phí ngủ sau 15 phút. |
| "Hệ thống đang khởi động" (503 engine_warming)    | Như trên: đợi vài chục giây rồi **Thử lại**.                                                                                                                       |
| "Tính năng chưa bật" (503 matcher_not_configured) | Render thiếu `MATCHER_DATABASE_URL`: báo Duy đặt lại. Trong lúc chờ demo phần Lưu việc / Admin trước.                                                              |
| "Bạn thao tác quá nhanh" (429)                    | Giới hạn 20 lượt / phút / tài khoản. Đợi hết đếm ngược; giảng viên dùng tài khoản thứ 2 nên không chung lượt.                                                      |
| Kết quả rỗng                                      | Bộ lọc quá hẹp: bấm **Bỏ lọc tỉnh** / **Bỏ lọc hình thức**.                                                                                                        |
| Lưu việc báo "Phiên đăng nhập đã hết hạn"         | Đăng xuất, đăng nhập lại.                                                                                                                                          |
| Production lỗi                                    | Chạy `npm run dev` trên máy, demo ở `http://localhost:3000` (cùng Supabase, cùng API).                                                                             |

---

## 4. Nói trước những điểm còn thiếu

- **Kho tin** lúc soạn có 1.466 tin mở, chưa tới mốc 1.500 của S4-T06 (Tùng báo số cuối trước giờ review).
- **Điểm lúc lưu** chưa được lưu trong DB: trang Việc đã lưu hiện điểm gần nhất của tin trong 10 lần
  gợi ý, không có thì "—".
- **API trên Render gói miễn phí** có thể ngủ; lần gọi đầu sau khi thức phải nạp kho tin (~40 giây),
  có thể chạm giới hạn chờ 30 giây của trang và phải bấm Thử lại.
- **Thời gian máy chủ** trên trang lấy từ `latency_ms`; header `Server-Timing` chưa mở qua CORS.
- Ví dụ JSON trong `docs/api/match-jobs.md` ghi `score: 82.4` nhưng thành phần của ví dụ cho ra khoảng
  84,9 (Duy sửa ví dụ).
- **Chấm độ khớp với một tin cụ thể** (nút trên trang chi tiết tin) và **bảng kỹ năng còn thiếu** là
  Sprint 5.

---

## 5. Câu hỏi giảng viên có thể hỏi

| Câu hỏi                                            | Trả lời ngắn                                                                                                                                                                                    |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Điểm 86 có nghĩa là 86% khả năng trúng tuyển?      | Không. Đó là mức khớp theo công thức (từ khóa, kỹ năng, nội dung, kinh nghiệm). Trang luôn ghi rõ câu này.                                                                                      |
| Vì sao bỏ thành phần không xác định thay vì cho 0? | Tin không ghi số năm hay không ghi kỹ năng thì không có gì để so; cho 0 là phạt oan ứng viên. Bỏ phần đó và chia lại trọng số theo tỉ lệ, tổng vẫn bằng 1, popover ghi rõ đã bỏ phần nào.       |
| K và E "theo phân vị toàn kho" là gì?              | Không dùng số thô của BM25 / cosine (khó hiểu, khác nhau theo CV) mà so với mọi tin đang mở: E = 0,89 nghĩa là CV gần tin này hơn 89% tin trong kho. Dòng giải thích dưới thẻ dùng đúng số này. |
| Vì sao kết hợp BM25 và vector?                     | BM25 bắt đúng từ khóa (tên công nghệ), vector bắt nghĩa gần (mô tả khác chữ). Lấy top 100 mỗi bên rồi hợp nhất để không bỏ sót trước khi chấm kỹ.                                               |
| Làm sao chắc không gợi ý tin hết hạn?              | Lọc cứng trước khi chấm, và API kiểm lại Top N với DB ngay lúc trả (tin vừa đóng cũng bị loại). Tùng chạy truy vấn kiểm tra trước demo (S4-T06).                                                |
| Nhanh cỡ nào, chịu tải ra sao?                     | Kho tin nằm trong RAM của API, làm mới mỗi giờ; mục tiêu p95 ≤ 3 giây với 2.000 tin (S4-D05). Giới hạn 20 lượt / phút / người. p95 theo ngày xem ở trang Admin.                                 |
| Lưu việc có an toàn không?                         | Ghi qua RPC `api.save_job` / `unsave_job` chạy bằng quyền người dùng (RLS), nhận `public_id` chứ không phải id nội bộ. Tin bị gộp thì lưu vào tin được giữ lại.                                 |
| Lịch sử gợi ý lưu những gì?                        | Mỗi lần chấm ghi `app.match_requests` (CV, số việc, bộ lọc, trọng số, phiên bản công thức) và `app.match_results` (điểm từng thành phần). Trang hiện 10 lần gần nhất.                           |

---

## 6. Góp ý trong buổi review (cho S4-H07, S4-D09, S4-T08)

Buổi review 26/11 không có góp ý phần giao diện: S4-H07 đóng mà không có thay đổi code.

| #   | Góp ý          | Phần      | Người xử lý | Trạng thái |
| --- | -------------- | --------- | ----------- | ---------- |
| –   | Không có góp ý | Giao diện | Thịnh       | Đóng       |
