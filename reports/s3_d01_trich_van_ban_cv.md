# S3-D01: Trích văn bản CV (PDF, DOCX) trên 10 CV mẫu

Ngày 17/11/2026 · Duy · Issue #463 (US-12 #403) · Bộ trích `cvparser-1/pdf-2`, `cvparser-1/docx-1`

Bộ mẫu là CV **giả** (`tests/fixtures/cv/`, xem README ở đó). Báo cáo chỉ ghi chỉ số.
Máy đo: Apple M1 Pro, 8 nhân · pypdfium2 5.15.2 · pdfplumber 0.11.10 · python-docx 1.2.0.

## Kết quả: 10/10 CV ra văn bản đọc được

```
$ uv run python scripts/extract_cv.py run tests/fixtures/cv/samples tests/fixtures/cv/edge
```

| CV | Loại | Kết quả | Trang | Ký tự | Rác | Từ có dấu | Bảng | ms |
|---|---|---|---|---|---|---|---|---|
| cv01 | PDF 1 cột, Việt | ok | 1 | 707 | 0 | 71% | 0 | 122 |
| cv02 | PDF 1 cột, Anh | ok | 1 | 686 | 0 | – | 0 | 98 |
| cv03 | PDF 2 cột | ok | 1 | 506 | 0 | 69% | 0 | 87 |
| cv04 | PDF có bảng | ok | 1 | 377 | 0 | 67% | 2 | 93 |
| cv05 | PDF 2 trang, header lặp | ok | 2 | 2990 | 0 | – | 0 | 137 |
| cv06 | PDF kiểu Google Docs | ok | 1 | 366 | 0 | 61% | 0 | 65 |
| cv07 | PDF kiểu Canva 2 cột, icon, chữ giãn | ok | 1 | 341 | 0 | 69% | 0 | 67 |
| cv08 | DOCX style Heading, đánh số | ok | – | 506 | 0 | 69% | 0 | 8 |
| cv09 | DOCX bảng bố cục 2 cột, header | ok | – | 453 | 0 | 71% | 0 | 6 |
| cv10 | DOCX text box, footer | ok | – | 377 | 0 | 63% | 0 | 7 |
| `edge/encrypted_userpw.pdf` | PDF có mật khẩu | **failed: `encrypted`** (đúng kỳ vọng) | | | | | | 0,2 |
| `edge/scan_image_only.pdf` | PDF ảnh scan | **failed: `ocr_required`** (đúng kỳ vọng) | | | | | | 0,6 |

ms đo khi chạy lần đầu trong tiến trình (gồm nạp thư viện); chạy lô nhanh hơn nhiều (bên dưới).

### Kiểm tự động (`tests/unit/test_cv_samples.py`, 10/10 PASSED)

Mỗi CV phải: không failed; `quality.readable` (≥ 300 ký tự, ký tự rác ≤ 1%, còn dấu tiếng Việt);
≥ 95% cụm mốc (tên, chức danh, công ty, mốc thời gian, kỹ năng, hàng bảng) có nguyên vẹn; heading
đúng thứ tự trong từng cột; các nhóm dòng liền nhau (cột trái của CV 2 cột, gạch đầu dòng của
cùng một việc); không có `(cid:` hay U+FFFD; đủ số bảng.

### Kiểm tay

Đọc văn bản trích của cả 10 CV cạnh file gốc theo 5 tiêu chí (chữ và dấu, thứ tự đọc, đủ nội dung,
cấu trúc, bảng). Không CV nào có điểm 0. Ghi nhận:

- cv03, cv07 (2 cột): hết cột trái rồi mới sang cột phải, không trộn dòng.
- cv05: header lặp ở 2 trang chỉ giữ một lần ở đầu (`source="header"`), bỏ "Page 1/2"; trước khi
  sửa, header chen vào giữa danh sách vắt trang.
- cv07: tiêu đề giãn chữ kiểu Canva dựng lại đúng ranh giới từ ("LIÊN HỆ", không ra "LIÊNHỆ").
- cv04: văn bản chính giữ chữ của bảng theo dòng PDF (ô nhiều dòng bị xuống dòng); bảng đầy đủ
  từng hàng nằm trong `tables[]`. S3-D04 đọc kinh nghiệm dạng bảng từ `tables[]`.
- cv09, cv10: header/footer và text box xuất hiện đúng một lần.

## Chạy nhiều CV cùng lúc

```
$ uv run python scripts/extract_cv.py run tests/fixtures/cv/samples --repeat 5
50 file · 50 đọc được · 0 lỗi · 0.51 giây · 97.9 file/giây · workers=auto (8)
```

`extract_many()` chạy nhiều tiến trình (spawn, `max_tasks_per_child=50`); `--workers 1` chậm hơn
khoảng 2 lần. Mục tiêu S6 "50 CV ≤ 60 giây" (kể cả embedding) còn dư nhiều cho phần trích văn bản.
`tests/unit/test_cv_batch_privacy.py` kiểm: file hỏng/rỗng trong lô không làm dừng lô, và kết quả
chạy song song giống hệt chạy tuần tự.

## Còn để sau

| Hạng mục | Khi nào |
|---|---|
| Timeout cứng từng file (kill tiến trình) | S3-D05 (API) / S6-D03 (worker) |
| OCR cho PDF scan, đọc `.doc` | Chờ quyết định; hiện trả `ocr_required` / `unsupported_type` kèm hướng dẫn |
| Nhận bảng mã TCVN3/VNI | Khi gặp ở CV thật (S3-D06) |
| Gợi ý heading từ cỡ chữ/đậm trong PDF | S3-D02 nếu luật theo chữ không đủ |
