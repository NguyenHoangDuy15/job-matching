# Sprint 3 Review: checklist AC và kịch bản demo (S3-H07)

- **Thời gian:** thứ 5, 19/11/2026 · giờ review theo lịch nhóm
- **Người dẫn demo:** Thịnh
- **Link production:** https://jobmatch-web.dtt-jobmatch.workers.dev
- **Done khi:** checklist AC mục 1 đạt trên production; giảng viên tự tải CV và xác nhận hồ sơ được.

> Không ghi mật khẩu vào file này. Mật khẩu tài khoản demo để ở chỗ an toàn của nhóm.

Mục tiêu Sprint 3: người tìm việc **tải CV** (có đồng ý xử lý), hệ thống **đọc CV và che thông tin
cá nhân**, người dùng **xác nhận hồ sơ kỹ năng có dẫn chứng**, quản lý **tối đa 5 CV**; tin đăng trên
nhiều trang được **gộp lại**.

---

## 0. Chuẩn bị (xong trước giờ review 30 phút)

- [ ] Cloudflare → Workers → jobmatch-web → Deployments: bản mới nhất của `main` **Ready** (sau #676).
- [ ] Đánh thức API đọc CV: mở https://jobmatch-cv-api.onrender.com/health, đợi tới khi thấy
      `"warm":true` (lúc ngủ mất khoảng 1–2 phút). Mở lại lần nữa ngay trước khi demo.
- [ ] Tài khoản **seeker demo** sạch: đăng nhập → **Hồ sơ CV** → xóa hết CV, thấy "Bạn chưa tải CV nào".
- [ ] Tài khoản **seeker thứ 2** cho giảng viên tự thao tác (cũng 0 CV).
- [ ] Mở sẵn thư mục CV mẫu giả: `tests/fixtures/cv/samples/` (cv01.pdf, cv02.pdf, cv03.pdf, cv08.docx,
      cv09.docx) và `tests/fixtures/cv/edge/scan_image_only.pdf`. Chuẩn bị thêm 1 ảnh `.png` và 1 tệp
      ảnh đổi đuôi thành `.pdf` để demo từ chối định dạng.
- [ ] Mở lại 2 tin gộp ở mục 2 (dữ liệu đổi theo crawler; tin đóng thì lấy tin khác theo mục 3).
- [ ] Tùng chạy smoke test production (S3-T08) xong, báo đạt.
- [ ] Dự phòng: `npm run dev` ở `apps/web` chạy được trên máy, `.env.local` có `NEXT_PUBLIC_CV_API_URL`.

---

## 1. Checklist AC trên production

Đánh dấu khi bấm thử đạt trên production (không phải localhost).

### US-11 · Tải CV (S3-H01, S3-T01, S3-T02)
- [ ] Chỉ nhận PDF, DOCX ≤ 5 MB; `.png` báo "Chỉ nhận PDF hoặc DOCX."
- [ ] Ảnh đổi đuôi thành `.pdf` báo "Nội dung tệp không phải PDF (có thể đã bị đổi đuôi)."
- [ ] Tệp > 5 MB báo "Tệp quá lớn (tối đa 5 MB)."
- [ ] Ô đồng ý **không tick sẵn**, có phiên bản điều khoản; chưa tick thì nút Tải lên bị khóa.
- [ ] Thanh tiến trình % khi tải lên; các bước Kiểm tra tệp → Tải lên → Lưu CV → Phân tích kỹ năng.
- [ ] Tải lại đúng tệp đã có báo "CV này bạn đã tải trước đó."
- [ ] Đủ 5 CV: vùng kéo thả khóa, báo "Bạn đã có 5 CV" (DB cũng chặn, mã 53400).
- [ ] Seeker A không đọc, sửa, xóa được CV của seeker B (rls_test trong CI, 93 PASS).

### US-12 · Đọc CV và xác nhận hồ sơ (S3-D01→D05, S3-H02, S3-H03)
- [ ] Phân tích xong ≤ 15 giây rồi tự sang màn xác nhận.
- [ ] Kỹ năng chia 3 nhóm: **Có bằng chứng** (kèm câu trích, tên kỹ năng in đậm), **Chỉ được liệt kê**, **Tự thêm**.
- [ ] Câu trích đã che họ tên, email, SĐT, địa chỉ (hiện `[ĐÃ CHE]` nếu có).
- [ ] Thêm kỹ năng có gợi ý từ từ điển, gõ không dấu được; kỹ năng thêm vào có nhãn **"Tự thêm"**.
- [ ] Xóa kỹ năng, khôi phục được kỹ năng vừa xóa.
- [ ] Sửa chức danh mong muốn và số năm kinh nghiệm (0–60, nhận "1,5"); nhập 61 bị báo lỗi.
- [ ] Bấm **Lưu hồ sơ**, **F5** vẫn thấy đúng dữ liệu đã lưu, có "Đã lưu lúc …".
- [ ] CV ảnh scan: báo "Chưa phân tích được CV" kèm lý do, CV vẫn được giữ, có nút Phân tích lại.

### US-13 · Hồ sơ của tôi (S3-H04)
- [ ] `/ho-so` hiện từng CV: tên tệp, chức danh · số năm, trạng thái, số kỹ năng theo mức, hạn lưu (+30 ngày).
- [ ] CV đầu tiên tự thành **CV chính**; chỉ có 1 CV chính.
- [ ] **Đặt làm CV chính** chuyển nhãn ★ sang CV khác.
- [ ] **Xóa** có hộp thoại "Xóa vĩnh viễn"; xóa xong mất cả tệp trong Storage.
- [ ] Xóa CV chính → CV mới nhất còn lại thành CV chính.
- [ ] Hiện x/5 CV; chưa có CV thì hiện "Bạn chưa tải CV nào".

### US-14 · Tin đăng trên nhiều trang (S3-T03→T05, S3-H05)
- [ ] Tin gộp hiện **"Có trên N trang"**, bấm ra danh sách link tới từng trang gốc.
- [ ] Link cũ của tin đã bị gộp tự chuyển sang tin được giữ lại.

### Phân quyền
- [ ] Khách mở `/ho-so` → chuyển sang đăng nhập, đăng nhập xong quay lại.
- [ ] HR hoặc Admin mở `/ho-so` → trang 403.

---

## 2. Kịch bản demo (~15 phút)

| Phút | Ai làm | Nội dung | Nói gì |
|---|---|---|---|
| 0–1 | Thịnh | Mở đầu | Sprint 3: từ "tìm việc" sang "**hiểu người tìm việc**": tải CV, máy đọc ra kỹ năng có dẫn chứng, người dùng kiểm lại. Đây là đầu vào cho Việc phù hợp ở Sprint 4. |
| 1–3 | Thịnh (Duy, Tùng bổ sung) | Kiến trúc | Trình duyệt tải thẳng lên Supabase Storage (bucket `cvs` riêng tư, RLS theo người dùng) → ghi `app.cvs` kèm phiên bản điều khoản → gọi API đọc CV (FastAPI trên Render, xác thực JWT, không giữ khóa bí mật) → trích văn bản, **che PII bằng Presidio + regex tiếng Việt**, tách section, gán kỹ năng + mức bằng chứng → ghi `app.cv_skills` qua RLS. |
| 3–5 | Thịnh | Tải CV, các ràng buộc | Hồ sơ CV → Tải CV mới. Kéo `.png` → bị từ chối. Kéo ảnh đổi đuôi `.pdf` → bị từ chối (kiểm byte đầu tệp, không tin đuôi). Chỉ ô đồng ý chưa tick, nút khóa. Kéo **cv01.pdf**, tick, Tải lên → chỉ thanh %, các bước, tự sang màn xác nhận. |
| 5–8 | Thịnh | Xác nhận hồ sơ | Chỉ chức danh "Lập trình viên Backend", 5,4 năm (tính từ 2 mốc thời gian). Nhóm **Có bằng chứng**: câu trích in đậm "Docker", "Kafka". Nhóm **Chỉ liệt kê**: Git, Tiếng Anh. Xóa Git → khôi phục. Gõ "fig" thêm **Figma** → nhãn Tự thêm. Sửa số năm 5,5 → Lưu hồ sơ → **F5** vẫn giữ. Nói: "Có bằng chứng" sẽ được tính nặng hơn khi chấm việc phù hợp. |
| 8–10 | **Giảng viên** | Tự thao tác | Đưa máy (tài khoản seeker thứ 2): giảng viên tải **cv02.pdf** (tiếng Anh) hoặc CV DOCX → xem kỹ năng → thêm 1 kỹ năng → Lưu. |
| 10–12 | Thịnh | Hồ sơ của tôi | Tải nhanh thêm cv03, cv08, cv09 (đã tải sẵn lúc chuẩn bị nếu thiếu thời gian) → `/ho-so`: 5/5 CV, CV chính ★, trạng thái, số kỹ năng, hạn lưu. Đặt cv03 làm CV chính. Xóa CV chính → CV mới nhất thành CV chính. Mở `/ho-so/tai-cv` khi đủ 5 → bị khóa. |
| 12–13 | Thịnh | CV lỗi | Tải `scan_image_only.pdf` → "Không đọc được chữ… xuất lại PDF từ Word". Ở `/ho-so`: Lỗi phân tích + nút Phân tích lại. |
| 13–14 | Thịnh (Tùng giải thích) | Tin gộp | Mở **Nutanix Software Engineer** → "Có trên 2 trang" → TopCV, VietnamWorks. Tùng: khử trùng chính xác (URL chuẩn hóa, hash nội dung) + gần trùng MinHash/LSH, precision 1,000 trên 100 cặp. |
| 14–15 | Thịnh | Còn thiếu & Sprint 4 | Nêu mục 4, giới thiệu Sprint 4: **Việc phù hợp** (BM25 + vector + khớp kỹ năng, API `/match/jobs` đã có ở S4-D04). |

### Tin dùng để demo (kiểm lại trước giờ review)
- **Nutanix Software Engineer** · FPT Software · TopCV + VietnamWorks · hạn 02/12:
  https://jobmatch-web.dtt-jobmatch.workers.dev/viec-lam/d00e8759-e0bb-415f-b8dc-dd82dde56e1a
- Dự phòng: **Senior Fullstack Java Developer** · LG CNS Việt Nam · TopCV + VietnamWorks · hạn 29/11:
  https://jobmatch-web.dtt-jobmatch.workers.dev/viec-lam/95840fd7-9455-4fe7-a104-5772f3567185

Số liệu lúc soạn (19/11): 1.392 tin đang mở, 9 tin gộp từ 2 nguồn, 2 tin gộp từ 2 trang khác nhau.

---

## 3. Nếu có sự cố

| Sự cố | Cách xử lý |
|---|---|
| Bước "Phân tích kỹ năng" quay lâu (> 15 giây) | API Render đang ngủ. Nói rõ lý do (gói miễn phí ngủ sau 15 phút), mở `/health` ở tab khác, đợi `warm:true`, rồi bấm **Phân tích lại** ở `/ho-so`. CV đã được lưu, không mất. |
| Báo "Không kết nối được dịch vụ đọc CV" | Kiểm tra `/health`; nếu API chết, demo phần xác nhận bằng CV đã phân tích sẵn lúc chuẩn bị. |
| Báo "CV này bạn đã tải trước đó" khi demo | Tài khoản chưa sạch: dùng CV mẫu khác (cv04, cv05, cv10) hoặc xóa CV cũ ở `/ho-so`. |
| Tin gộp đã đóng | Lấy tin khác: SQL `select j.public_id, count(*) from core.job_sources s join core.jobs j on j.id = s.job_id where j.status = 'open' and s.is_active group by 1 having count(*) > 1;` |
| Production lỗi | Chạy `npm run dev` trên máy, demo ở `http://localhost:3000` (cùng Supabase, cùng API). |

---

## 4. Nói trước những điểm còn thiếu

- **Hạn lưu 30 ngày mới hiển thị, chưa tự xóa** CV người tìm việc khi quá hạn: cần thêm bước xóa
  tệp trong Storage trước (0015 ghi rõ).
- **API đọc CV trên Render gói miễn phí** có thể ngủ; workflow `cv-api-keepwarm` ping 10 phút một
  lần để giữ thức, cần theo dõi thêm (lần chuẩn bị S3-H06 gặp API ngủ, `/health` mất 99 giây).
- **Tên tệp gốc** chỉ có với CV tải sau migration 0010; CV cũ hiện "CV PDF".
- **Việc phù hợp** (Top N việc theo CV chính) là Sprint 4; hôm nay hồ sơ kỹ năng mới là đầu vào.

---

## 5. Câu hỏi giảng viên có thể hỏi

| Câu hỏi | Trả lời ngắn |
|---|---|
| Vì sao tải thẳng từ trình duyệt lên Storage, không qua server Next.js? | Server Action mặc định chỉ nhận body ≤ 1 MB và không báo được % tiến trình. Quyền vẫn do RLS của bucket `cvs` kiểm bằng JWT (đường dẫn `u/<uid>/…`). |
| Làm sao biết tệp là PDF thật? | Kiểm đuôi, dung lượng và byte đầu tệp (`%PDF-` trong 1024 byte đầu, DOCX là gói zip), không tin `file.type`. Bucket cũng giới hạn MIME và 5 MB. |
| Thông tin cá nhân trong CV xử lý thế nào? | API che họ tên, email, SĐT, địa chỉ (Presidio + regex tiếng Việt, 20/20 mẫu không lộ) **trước** khi phân tích; chỉ lưu văn bản đã che. Người dùng xóa CV là xóa tệp + cascade dữ liệu. |
| "Có bằng chứng" và "Chỉ liệt kê" khác nhau thế nào? | Có bằng chứng: kỹ năng xuất hiện trong Kinh nghiệm/Dự án, có câu trích. Chỉ liệt kê: chỉ nằm ở mục Kỹ năng. Khi chấm việc phù hợp, có bằng chứng tính nặng hơn. |
| Người dùng sửa hồ sơ rồi đọc lại CV thì sao? | Kỹ năng đã xác nhận / tự thêm và số năm, chức danh đã lưu được giữ nguyên (0010). |
| Vì sao API chạy trên Render, không phải Cloud Run? | Cloud Run cần thẻ thanh toán; image vẫn tương thích Cloud Run để chuyển sau. |
| Gộp tin trùng có gộp nhầm không? | Đo trên 100 cặp gán tay: precision 1,000 với ngưỡng đã chỉnh (S3-T05); cặp nghi trùng 0,70–0,85 vào hàng chờ admin duyệt. |

---

## 6. Góp ý trong buổi review (cho S3-H08)

| # | Góp ý | Phần | Người xử lý | Trạng thái |
|---|---|---|---|---|
| | | | | |
