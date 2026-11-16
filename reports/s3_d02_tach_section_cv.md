# S3-D02: Tách section CV tiếng Việt/Anh trên 10 CV mẫu

Ngày 17/11/2026 · Duy · Issue #467 (US-12 #403) · `cvparser.sections`, từ điển `cv-sections-1`

Bộ mẫu là CV **giả** (`tests/fixtures/cv/`). Nhãn chuẩn gán tay trong `scripts/make_cv_samples.py`
(`SECTION_GOLD`: tên mục → section), không lấy từ bộ tách. Báo cáo chỉ ghi chỉ số.

## Kết quả: 10/10 CV đúng section

```
$ uv run pytest tests/unit/test_cv_sections.py
```

| CV | Loại | Tên mục đúng | Dòng mốc đúng mục | Section tách được |
|---|---|---|---|---|
| cv01 | PDF 1 cột, Việt | 5/5 | 21/21 | header, summary, experience, **projects**, education, skills |
| cv02 | PDF 1 cột, Anh | 6/6 | 19/19 | header, summary, experience, **projects**, education, skills, activities |
| cv03 | PDF 2 cột | 7/7 | 21/21 | header, header (Liên hệ), skills, languages, summary, experience, **projects**, education |
| cv04 | PDF có bảng, tên mục đánh số I.–V. | 5/5 | 7/7 | header, summary, experience, skills, certifications, other |
| cv05 | PDF 2 trang, Anh | 6/6 | 70/70 | header, summary, experience, **projects**, certifications, skills, languages |
| cv06 | PDF kiểu Google Docs | 4/4 | 9/9 | header, summary, experience, education, skills |
| cv07 | PDF kiểu Canva 2 cột | 5/5 | 12/12 | header (Liên hệ), skills, summary, experience, education |
| cv08 | DOCX style Heading | 5/5 | 18/18 | header, summary, experience, **projects**, education, skills |
| cv09 | DOCX bảng bố cục 2 cột, **tên mục lạ** | 5/5 | 17/17 | header, skills, certifications, summary, **experience (đoán)**, education |
| cv10 | DOCX text box | 4/4 | 12/12 | header, summary, experience, education, skills |
| **Tổng** | | **52/52** | **206/206** | |

"Dòng mốc" = mọi dòng nội dung của CV (tên, liên hệ, từng dòng kinh nghiệm, dự án, học vấn,
kỹ năng...) có nhãn section đúng; dòng trùng nhau (chức danh lặp ở đầu CV và trong Kinh nghiệm)
không chấm vì không xác định được vị trí. Tiêu chí test: 100% tên mục đúng và đúng thứ tự,
≥ 95% dòng đúng mục, và 100% ở 3 mục D04 cần (Kinh nghiệm, Dự án, Kỹ năng).

### Các ca khó có trong bộ mẫu

| Ca | Ở đâu | Kết quả |
|---|---|---|
| Tên mục lạ không có trong từ điển: "CHẶNG ĐƯỜNG ĐÃ QUA" | cv09 | Đoán đúng **experience** từ khoảng thời gian và từ "Công ty", "Chuyên viên" |
| Dòng bẫy trong Kỹ năng: "Kinh nghiệm làm việc với Docker và Kubernetes trên môi trường production" | cv01 | Ở lại **skills**, không mở mục Kinh nghiệm |
| Mục con trong Kinh nghiệm: "Dự án: Cổng thanh toán nội bộ", "Công nghệ: Java, Spring Boot, Kafka" | cv01 | Ở lại **experience** (cùng mức bằng chứng strong ở D04) |
| Tên mục ghép / biến thể: "HỌC VẤN & BẰNG CẤP", "PROFESSIONAL EXPERIENCE", "TECHNICAL SKILLS", "ACTIVITIES & AWARDS", "Kỹ năng chuyên môn", "Dự án tiêu biểu" | cv01, cv02, cv08 | Đúng |
| Tên mục đánh số "I. MỤC TIÊU…", "II. KINH NGHIỆM…" | cv04 | Đúng |
| Dòng tiêu đề bảng "Kỹ năng \| Mức độ" trong mục Kỹ năng | cv04 | Không thành mục mới |
| Kỹ năng IN HOA một dòng ("BPMN", "SQL") | cv09 | Không bị đoán là tên mục |

Ngoài 10 CV: `tests/unit/test_cv_sections.py` có 38 cách viết tên mục (Việt có/không dấu, IN HOA,
tiếng Anh, số thứ tự, icon, dấu ":"), 8 dòng bẫy, tên mục kèm nội dung cùng dòng, CV không có tên
mục nào (`fallback`), `section_at` theo offset.

Thời gian: khoảng 1 ms/CV (cv05, 2 trang), không đáng kể so với bước trích văn bản.

## Giới hạn đã biết

- **CV 2 cột mà tên/chức danh nằm đầu cột phải**: dòng tên rơi vào mục cuối của cột trái (cv07:
  "Trịnh Gia Bảo", "Thiết kế UI/UX" → skills; cv03: chức danh → languages). Văn bản trích không
  còn vị trí cột để tách. Ảnh hưởng: S3-D04 có thể thấy chức danh như một dòng kỹ năng (mức
  `listed`, không phải `strong`); tên người không phải kỹ năng nên không thành thẻ. Hướng sửa nếu
  CV thật ở S3-D06 gặp nhiều: D01 giữ tọa độ khối PDF, D02 coi khối có cỡ chữ lớn nhất ở đầu
  trang là header.
- Tên mục lạ chỉ được đoán khi có ≥ 2 tín hiệu nội dung rõ ràng; không chắc thì không mở mục mới
  (dòng ở lại mục trước). CV thật ở S3-D06 sẽ cho biết cần thêm tên mục nào vào
  `config/cv_headings.yaml`.

## Dùng ở các task sau

```python
from cvparser.extract import extract_document
from cvparser.sections import split_sections

result = extract_document(data, filename=name)
secs = split_sections(result.text, result.blocks)
secs.section_at(
    offset
)  # S3-D04: kỹ năng ở offset này → experience/projects = strong, skills = listed
secs.by_name("experience")  # S3-D04: khoảng thời gian chỉ lấy trong Kinh nghiệm để tính số năm
secs.to_jsonb()  # S3-D05: app.cvs.parsed_sections
```

S3-D05 nên gọi `split_sections` trên văn bản **đã che PII** (S3-D03): tên mục không chứa PII nên
kết quả như nhau, và offset khớp `app.cvs.text_redacted`.
