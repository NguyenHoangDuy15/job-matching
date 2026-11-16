# S3-D04: Hồ sơ CV (mức bằng chứng, câu trích, số năm kinh nghiệm) trên 10 CV mẫu

Ngày 18/11/2026 · Duy · Issue #473 (US-12 #403) · `cvparser.profile`, `cvparser.dates`, cấu hình `cv-profile-1`

Bộ mẫu là CV **giả** (`tests/fixtures/cv/`). Nhãn chuẩn `tests/fixtures/cv/profile/gold.yaml` soạn
từ nội dung giả của từng CV, tính tại `as_of = 2026-11-18`.

## Kết quả: hồ sơ JSON đúng 10/10 CV

```
$ uv run pytest tests/unit/test_cv_profile.py      # 39 passed
```

| CV | Chức danh mong muốn (nguồn) | Số năm | Strong | Listed | Lỗi từ điển ghi riêng | Kết quả |
|---|---|---|---|---|---|---|
| cv01 | Lập trình viên Backend (đầu CV) | 5,4 | 13 | 3 | 1 | đạt |
| cv02 | Data Analyst (đầu CV) | 6,5 | 8 | 4 | 1 | đạt |
| cv03 | Lập trình viên Frontend (việc gần nhất) | 6,3 | 6 | 4 | 1 | đạt |
| cv04 | Kiểm thử phần mềm (đầu CV) | 6,5 | 3 | 5 | 0 | đạt |
| cv05 | DevOps Engineer (đầu CV) | 7,9 | 11 | 5 | 1 | đạt |
| cv06 | Kỹ sư Dữ liệu (đầu CV) | 4,8 | 5 | 4 | 0 | đạt |
| cv07 | UI/UX Designer (việc gần nhất) | 4,9 | 3 | 3 | 1 | đạt |
| cv08 | Lập trình viên Mobile (đầu CV) | 6,2 | 6 | 4 | 0 | đạt |
| cv09 | Chuyên viên Phân tích nghiệp vụ (đầu CV) | 7,4 | 2 | 5 | 0 | đạt |
| cv10 | Kỹ sư An toàn thông tin (đầu CV) | 4,8 | 3 | 2 | 0 | đạt |

**Một CV đạt khi:**
- chức danh đúng;
- số năm lệch ≤ 0,1 năm;
- tập kỹ năng strong và listed khớp chính xác;
- câu trích của các kỹ năng được kiểm nằm đúng mục và đúng công ty/dự án;
- mọi câu trích chứa đúng tên kỹ năng (vị trí in đậm đúng), ≤ 200 ký tự, không có PII;
- JSON hợp lệ theo schema `CvProfile`.

Ví dụ câu trích (cv01, đúng như wireframe):
*"Triển khai **Docker** và Kubernetes cho 12 dịch vụ"* — Kinh nghiệm · Công ty Cổ phần Công nghệ Sao Mai.
Docker dùng 3,8 năm (chỉ ở Sao Mai); Java 5,4 năm (cả hai công ty).

### Lỗi của từ điển kỹ năng (không phải luật D04), chuyển S3-D06

Tách riêng trong `dictionary_issues` của nhãn chuẩn, không tính vào phép so sánh:

| CV | Kỹ năng | Vấn đề | Sửa |
|---|---|---|---|
| cv01 | technical_writing | "đọc hiểu tài liệu kỹ thuật" là đọc, không phải viết tài liệu | Bỏ alias "tài liệu kỹ thuật" hoặc thêm luật loại |
| cv02 | ab_testing | Kinh nghiệm ghi "A/B tests", từ điển chỉ có "A/B testing" → lẽ ra strong, đang thành listed | Thêm alias "a/b tests", "a/b test" |
| cv03 | github | Chỉ là tên miền link dự án `github.com/[LINK]` | Không nhận kỹ năng từ URL |
| cv05 | cloud_computing | Bắt từ tên công ty "Blue Lotus Cloud" | Không nhận "cloud" đứng riêng trong tên tổ chức |
| cv07 | software_testing | "kiểm thử người dùng" (user testing) bị nhận thành kiểm thử phần mềm | Loại "kiểm thử người dùng" / thêm kỹ năng User Testing |

Không sửa `skills.yaml` ở task này: đổi từ điển làm đổi phiên bản gắn kỹ năng JD (S2-D04/D05)
và phải gắn lại toàn kho. Gom các sửa vào S3-D06 cùng các alias tìm ra từ 10 CV thật.

## Cách làm

- **Mức bằng chứng** theo section của D02: Kinh nghiệm/Dự án → `strong`; Kỹ năng, Tóm tắt, Chứng chỉ,
  Ngoại ngữ, Học vấn, Hoạt động → `listed`; phần đầu CV (chức danh "Java Developer") và mục khác bị
  bỏ qua; CV không có tên mục nào → mọi kỹ năng `listed`. Kỹ năng xuất hiện nhiều nơi lấy mức cao
  nhất. Câu trích ưu tiên dòng mô tả công việc hơn dòng liệt kê "Công nghệ: …".
- **Tách việc làm / dự án**:
  - dòng có khoảng thời gian mở một việc mới (công ty | chức danh | thời gian), có xử lý cả trường
    hợp tên công ty nằm ở dòng trước;
  - kinh nghiệm dạng bảng PDF lấy công ty và chức danh từ `tables[]` của D01 (cv04);
  - "Dự án: …", "Công nghệ: …" trong một việc vẫn thuộc việc đó.
- **Số năm** (`cvparser.dates`):
  - đọc được `03/2023 – nay`, `06.2019 – 12.2024`, `2021-03 → 2022-05`, `Tháng 3/2021`, `T3/2021`,
    `Mar 2021`, `present/hiện tại`, `2019 – 2021`;
  - chỉ lấy khoảng trong Kinh nghiệm (không lấy Học vấn, Dự án), gộp khoảng chồng nhau, bỏ khoảng
    ngược hoặc trong tương lai, không tính thực tập (trả `internship_months` để UI ghi chú);
  - không nhầm lương, TOEIC, mã số, số phiên bản (có test).
- **Chức danh mong muốn**: dòng chức danh ở phần đầu CV; không có thì chức danh của việc gần nhất
  (không lấy việc thực tập).
- Chạy trên văn bản **đã che PII** (D03) và section tách trên văn bản đó (D02).

Thời gian: khoảng 0,15 giây/CV cho cả chuỗi trích văn bản → che PII → tách section → hồ sơ.

## Hồ sơ JSON (rút gọn, cv01)

```json
{
  "version": "cv-profile-1", "as_of": "2026-11-18",
  "target_title": "Lập trình viên Backend", "target_title_source": "header",
  "years_exp": 5.4, "years_ranges": [["2021-07", "2023-02"], ["2023-03", "present"]],
  "internship_months": 0,
  "entries": [
    {"section": "experience", "org": "Công ty Cổ phần Công nghệ Sao Mai",
     "title": "Lập trình viên Backend", "start": "2023-03", "end": "present", "months": 45}
  ],
  "skills": [
    {"skill_id": "docker", "name": "Docker", "evidence_level": "strong",
     "evidence": "Triển khai Docker và Kubernetes cho 12 dịch vụ", "highlight": [11, 17],
     "section": "experience", "context": "Công ty Cổ phần Công nghệ Sao Mai",
     "mentions": 3, "years": 3.8}
  ],
  "warnings": []
}
```

`to_db_rows(profile, skill_ids)` trả các cột `app.cvs` (`years_exp`, `target_title`) và các dòng
`app.cv_skills` (`evidence_level`, `evidence`, `years`, `confirmed = false`) cho S3-D05.

## Giới hạn / để sau

- Kỹ năng gộp trong alias dài hơn ("Java Spring Boot" → Spring Boot) không được tính thêm cho Java
  ở dòng đó; Java vẫn strong nhờ dòng khác. Đo trên CV thật ở S3-D06.
- Phủ định trong Kinh nghiệm ("chưa dùng Docker") vẫn tính strong (hiếm).
- Bảng kinh nghiệm DOCX đi qua văn bản ("a | b | c") nên đọc được; bảng PDF không có khoảng thời gian
  trong văn bản thì dùng `tables[]`.
