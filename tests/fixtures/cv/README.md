# Bộ CV mẫu GIẢ (S3-D01)

Mọi nội dung là hồ sơ giả viết mới, **không phải CV thật đã sửa tên**. Email chỉ dùng
`@example.com` / `@example.vn`, số điện thoại chỉ lấy trong [fake_pii.yaml](fake_pii.yaml), metadata
tác giả để trống. `tests/unit/test_cv_batch_privacy.py` chặn trong CI mọi email/SĐT ngoài danh sách
giả, nên lỡ thêm CV có thông tin thật thì CI đỏ.

CV thật (S3-D06) để ở `data/cv_real/` (không lên git). Báo cáo chỉ ghi chỉ số.

| File | Loại | Tạo bằng | Kiểm điều gì |
|---|---|---|---|
| cv01.pdf | PDF 1 cột, tiếng Việt, Backend | script | Dấu tiếng Việt, heading, gạch đầu dòng |
| cv02.pdf | PDF 1 cột, tiếng Anh, Data | script | CV tiếng Anh |
| cv03.pdf | PDF 2 cột (khung trái/phải) | script | Thứ tự đọc 2 cột |
| cv04.pdf | PDF có 2 bảng kẻ khung | script | Bảng giữ nguyên hàng (`tables`) |
| cv05.pdf | PDF 2 trang, header + số trang lặp | script | Header gom một lần, bỏ số trang |
| cv06.pdf | PDF xuất từ Word/Google Docs | **làm tay** | PDF "đời thật": font subset, ligature |
| cv07.pdf | PDF từ mẫu Canva 2 cột có icon | **làm tay** | Khó nhất: icon font, cột, chữ giãn cách |
| cv08.docx | DOCX style Heading, danh sách đánh số | script | Style heading, list |
| cv09.docx | DOCX bảng bố cục 2 cột, header, ô gộp | script | Đọc hết cột trái rồi cột phải |
| cv10.docx | DOCX có Text Box, footer | **làm tay** | Text box không lặp |

`edge/`: `scan_image_only.pdf` (→ `ocr_required`), `encrypted_userpw.pdf` (→ `encrypted`).
`expected/cvXX.yaml`: cụm mốc phải có, thứ tự heading, nhóm dòng phải liền nhau, số bảng.

## Sinh lại

```bash
uv run python scripts/make_cv_samples.py   # cần font TTF có tiếng Việt (Arial/DejaVu) hoặc --font
uv run pytest tests/unit/test_cv_samples.py
```

Chạy lại ra cùng nội dung (không cần cùng byte). Sửa nội dung trong `PERSONAS` của script.

## Làm tay cv06, cv07, cv10

Nội dung giả nằm ở `manual/cv06.md`, `manual/cv07.md`, `manual/cv10.md`. Gõ/dán **nguyên văn**
(test so từng cụm), rồi:

1. **cv06**: Word hoặc Google Docs, 1 cột, tiêu đề in đậm → *File → Download/Save as → PDF*.
2. **cv07**: Canva, chọn một mẫu CV **2 cột có icon** → thay nội dung bằng `manual/cv07.md`
   (cột trái: LIÊN HỆ, KỸ NĂNG; cột phải: phần còn lại) → *Share → Download → PDF Standard*.
3. **cv10**: Word, khối liên hệ đặt trong *Insert → Text Box*, thêm footer có chữ "CV – Mai Anh
   Tuấn" → lưu `.docx`.
4. Xóa tên tác giả: Word *File → Info → Inspect Document → Document Properties and Personal
   Information → Remove All*. Google Docs/Canva thường không ghi tác giả; test sẽ báo nếu còn.
5. Lưu vào `samples/cv06.pdf`, `samples/cv07.pdf`, `samples/cv10.docx` rồi chạy
   `uv run pytest tests/unit/test_cv_samples.py tests/unit/test_cv_batch_privacy.py`.
