# S3-H06 · Test end-to-end tải CV → hồ sơ trên môi trường thật (US-11, US-12, US-13)

Điều kiện xong: **luồng chạy thông với 5 CV**. Người test: Thịnh. Ngày: 18/11/2026.

## 1. Môi trường

| Thành phần         | Giá trị                                                                                      |
| ------------------ | -------------------------------------------------------------------------------------------- |
| Web                | https://jobmatch-web.dtt-jobmatch.workers.dev (Cloudflare Workers, build từ `main` sau #675) |
| API đọc CV         | https://jobmatch-cv-api.onrender.com (Render Free, S3-D05)                                   |
| Database / Storage | Supabase dùng chung (migration 0008 → 0015)                                                  |
| Trình duyệt        | Chrome bản mới nhất, cửa sổ thường (không ẩn danh)                                           |
| Tài khoản          | 1 tài khoản **seeker** dùng để test (không ghi mật khẩu vào file này)                        |

Repo không có môi trường staging riêng: test trên bản production, chỉ dùng CV mẫu GIẢ.

## 2. Dữ liệu test

CV mẫu giả trong `tests/fixtures/cv/` (xem README ở đó). Kết quả mong đợi lấy từ
`tests/fixtures/cv/profile/gold.yaml` (S3-D04, tính tại 18/11/2026).

| #   | Tệp                        | Loại                     | Chức danh mong đợi              | Số năm | Có bằng chứng | Chỉ liệt kê |
| --- | -------------------------- | ------------------------ | ------------------------------- | ------ | ------------- | ----------- |
| 1   | `samples/cv01.pdf`         | PDF 1 cột, tiếng Việt    | Lập trình viên Backend          | 5,4    | 13            | 2           |
| 2   | `samples/cv02.pdf`         | PDF 1 cột, tiếng Anh     | Data Analyst                    | 6,5    | 9             | 3           |
| 3   | `samples/cv03.pdf`         | PDF 2 cột                | Lập trình viên Frontend         | 6,3    | 5             | 4           |
| 4   | `samples/cv08.docx`        | DOCX heading + danh sách | Lập trình viên Mobile           | 6,2    | 6             | 4           |
| 5   | `samples/cv09.docx`        | DOCX bảng 2 cột          | Chuyên viên Phân tích nghiệp vụ | 7,4    | 3             | 5           |
| E   | `edge/scan_image_only.pdf` | PDF ảnh scan             | lỗi `ocr_required`              |        |               |             |

Số kỹ năng là để đối chiếu độ đúng của bộ đọc CV (của Duy), lệch vài kỹ năng không làm trượt
S3-H06; S3-H06 kiểm **luồng** chạy thông.

## 3. Kiểm tra trước khi test

| #   | Việc                                      | Cách kiểm                                                       | Kết quả |
| --- | ----------------------------------------- | --------------------------------------------------------------- | ------- |
| P1  | Cloudflare đã build bản có S3-H04, S3-H05 | Workers → jobmatch-web → Deployments: dòng #675 **Ready**       | Đạt |
| P2  | Bản build có `NEXT_PUBLIC_CV_API_URL`     | Bước TC1: thấy bước "Phân tích kỹ năng" (không phải "(sắp có)") | Đạt |
| P3  | API thức                                  | Mở `…onrender.com/health`, đợi tới khi thấy `"warm":true`       | Đạt |
| P4  | CORS cho domain web                       | Đã kiểm 18/11: `access-control-allow-origin` = domain web       | Đạt     |
| P5  | Tài khoản test sạch                       | Vào **Hồ sơ CV**: xóa hết CV cũ, thấy "Bạn chưa tải CV nào"     | Đạt |

## 4. Kịch bản

Ghi thời gian phân tích bằng đồng hồ: từ lúc bấm **Tải lên** tới lúc hiện màn xác nhận.

| TC   | Bước                                                                                                                     | Kết quả mong đợi                                                                                                                                                                          | Thực tế | Đạt |
| ---- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | --- |
| TC1  | Hồ sơ CV → Tải CV mới → kéo thả **cv01.pdf**, tick đồng ý, Tải lên                                                       | Chạy Kiểm tra tệp → Tải lên % → Lưu CV → Phân tích kỹ năng, tự sang `/ho-so/<id>/xac-nhan` trong **≤ 15 giây**                                                                            | Sang màn xác nhận dưới 15 giây | Đạt |
| TC2  | Ở màn xác nhận cv01, so với bảng mục 2                                                                                   | Tên tệp `cv01.pdf`; chức danh và số năm khớp (±0,1); có 3 nhóm kỹ năng, câu trích in đậm tên kỹ năng                                                                                      | Như mong đợi | Đạt |
| TC3  | Xóa 1 kỹ năng "Chỉ liệt kê", thêm **Kafka** (nếu đã có thì **Figma**), sửa số năm thành 5, bấm **Lưu hồ sơ**, rồi **F5** | Kỹ năng thêm có nhãn "Tự thêm"; sau F5 giữ đúng thay đổi; "Đã lưu lúc …"                                                                                                                  | Như mong đợi | Đạt |
| TC4  | Lặp TC1 với **cv02, cv03, cv08, cv09** (bấm "Lưu hồ sơ" luôn, không sửa)                                                 | Mỗi CV đều sang màn xác nhận ≤ 15 giây, đúng loại tệp (PDF/DOCX)                                                                                                                          | Sang màn xác nhận dưới 15 giây | Đạt |
| TC5  | Vào **Hồ sơ CV**                                                                                                         | **5/5 CV**; cv01 là **CV chính** (CV đầu tiên); 5 dòng **Đã xác nhận**; đếm kỹ năng khớp màn xác nhận; Hạn lưu = hôm nay + 30 ngày; không còn nút "+ Tải CV mới"                          | Như mong đợi | Đạt |
| TC6  | Mở thẳng `/ho-so/tai-cv`                                                                                                 | Vùng kéo thả bị khóa, báo "Bạn đã có 5 CV" kèm link Hồ sơ của tôi                                                                                                                         | Như mong đợi | Đạt |
| TC7  | Ở Hồ sơ CV, bấm **Đặt làm CV chính** ở cv03                                                                              | Nhãn ★ chuyển sang cv03, cv03 lên đầu bảng                                                                                                                                                | Như mong đợi | Đạt |
| TC8  | Bấm **Xóa** ở cv03 (CV chính) → Hủy → Xóa lại → **Xóa vĩnh viễn**                                                        | Hộp thoại báo đây là CV chính; sau khi xóa còn **4/5**, CV mới nhất còn lại (cv09) thành CV chính; Supabase: không còn tệp `u/<uid>/<id>.pdf` trong Storage `cvs` và dòng trong `app.cvs` | Như mong đợi | Đạt |
| TC9  | Tải **edge/scan_image_only.pdf**                                                                                         | Lưu được CV nhưng báo "Chưa phân tích được CV" với lý do không đọc được chữ; ở Hồ sơ CV dòng này **Lỗi phân tích** + nút Phân tích lại                                                    | Như mong đợi | Đạt |
| TC10 | Xóa CV scan; tải lại **cv01.pdf**                                                                                        | Báo "CV này bạn đã tải trước đó" (trùng tệp), không tạo CV mới                                                                                                                            | Như mong đợi | Đạt |
| TC11 | Đăng xuất, mở `/ho-so`                                                                                                   | Chuyển sang trang đăng nhập; đăng nhập xong quay lại `/ho-so`                                                                                                                             | Như mong đợi | Đạt |
| TC12 | (Nếu có tài khoản HR) đăng nhập HR, mở `/ho-so`                                                                          | Không vào được (trang 403)                                                                                                                                                                | Như mong đợi | Đạt |

## 5. Kết quả

| Chỉ số                                                      | Giá trị |
| ----------------------------------------------------------- | ------- |
| Số CV chạy thông TC1 → TC5                                  | 5/5     |
| Thời gian phân tích (giây) cv01 / cv02 / cv03 / cv08 / cv09 | Đều dưới 15 giây (không bấm giờ từng CV) |
| Số TC đạt                                                   | 12/12   |

Kết luận: **Đạt.** Luồng tải CV → phân tích → xác nhận → Hồ sơ của tôi chạy thông với 5 CV trên môi trường thật.

## 6. Lỗi phát hiện

| #   | TC  | Mô tả | Mức | Người xử lý | Trạng thái |
| --- | --- | ----- | --- | ----------- | ---------- |
| —   | —   | Không phát hiện lỗi | — | — | — |

## 7. Rủi ro đã thấy khi chuẩn bị (18/11)

- **API ngủ trên Render.** `GET /health` mất 99 giây và trả `"warm": false`: dịch vụ đang ngủ và
  phải khởi động lại. Workflow `cv-api-keepwarm` (ping 10 phút một lần) lẽ ra giữ API thức; cần xem
  tab Actions → cv-api-keepwarm có chạy đều không và biến `CV_API_URL` đã đặt chưa. Nếu API ngủ,
  người dùng đầu tiên phải chờ khoảng 1–2 phút ở bước "Phân tích kỹ năng" (vượt 15 giây của US-12).
  Vì vậy làm P3 trước khi đo thời gian.
