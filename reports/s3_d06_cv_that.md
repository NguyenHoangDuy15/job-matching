# S3-D06: Thử 10 CV thật, đo độ đúng kỹ năng, sửa alias thiếu

Ngày 19/11/2026 · Duy · Issue #480 (US-12 #403) · Quy trình: `docs/labeling/cv_real.md`

> **Trạng thái:** phần 1 (sửa từ điển từ lỗi đã biết + công cụ đo) xong. Phần 2 (số liệu trên 10 CV
> thật) **chờ thu CV** (bạn bè, đã xin phép) và chấm tay. Mục 2 sẽ điền từ `reports/eval_cv_real.json`.

## 1. Alias / luật đã sửa

Từ 5 lỗi từ điển ghi ở S3-D04 (`reports/s3_d04_ho_so_cv.md`) và khi dựng công cụ:

| Vấn đề | Sửa | Ở đâu |
|---|---|---|
| "A/B tests" không nhận | + alias `a/b tests`, `ab tests` → `ab_testing` | `config/skills.yaml` |
| "kiểm thử người dùng" (user testing) thành Kiểm thử phần mềm | + `kiểm thử người dùng`, `kiểm thử khả dụng`, `user testing`, `usability testing` → `ui_ux` (cụm dài thắng "kiểm thử") | `config/skills.yaml` |
| "đọc hiểu tài liệu kỹ thuật" thành Technical Documentation | Bỏ alias chung `tài liệu kỹ thuật`; + `soạn tài liệu kỹ thuật`, `viết tài liệu` | `config/skills.yaml` |
| "Data Analyst" (chức danh) không thành Phân tích dữ liệu | + `data analyst`, `chuyên viên phân tích dữ liệu` → `data_analysis` | `config/skills.yaml` |
| "Spring-Boot" (gạch nối) thành Spring | + `spring-boot` → `spring_boot` | `config/skills.yaml` |
| Kỹ năng lấy từ **tên công ty** ("Blue Lotus **Cloud**", "Lotus Retail **Analytics**", "An ninh **Mạng**…") | Bỏ kỹ năng nằm trong tên công ty ở dòng tiêu đề việc làm | `cvparser/profile.py` |
| Kỹ năng lấy từ **URL** (`github.com/[LINK]`) | Bỏ kỹ năng nằm trong đường dẫn | `cvparser/profile.py` |

`db/seed/seed_skills.sql` sinh lại (379 kỹ năng, 1267 cách viết).

### Không làm tụt chất lượng chỗ khác

| Bộ đo | Trước | Sau |
|---|---|---|
| 10 CV mẫu, hồ sơ JSON (S3-D04) | 10/10, 5 lỗi từ điển phải bỏ qua | **10/10, không còn lỗi từ điển phải bỏ qua** |
| Gắn mức JD (S2-D04, 747 mention) | macro-F1 0,973 | **0,973** |
| Trích kỹ năng JD (S2-D07, 50 JD) | P 0,995 · R 0,660 · F1 0,794 | P 0,987 · R 0,660 · F1 0,791 |

3 "thẻ sai" mới trên 50 JD đều **đúng là kỹ năng**, chỉ nhãn chuẩn S2-D07 (gán khi từ điển chưa nhận
các cụm này) không ghi: vj_004 "viết tài liệu diễn giải…" và vj_016 "viết tài liệu HDSD" → Technical
Documentation; vj_000 "experience in Data Analyst" (tin tuyển Data Analyst) → Phân tích dữ liệu.
Nên bổ sung vào nhãn chuẩn khi đo lần 2.

**Sau khi merge**: từ điển đổi nên phiên bản gắn kỹ năng JD đổi. Cần (Tùng):

```bash
psql "$DATABASE_URL" -f db/seed/seed_skills.sql                       # alias mới vào ref.skill_aliases
uv run python scripts/label_skills.py --apply --stale --only-open     # gắn lại kỹ năng tin đang mở
```

## 2. 10 CV thật

*(chờ số liệu; điền sau khi chạy `scripts/eval_cv_real.py score`)*

| Chỉ số | Giá trị |
|---|---|
| CV đọc được | – / 10 |
| Precision kỹ năng | – |
| Recall kỹ năng | – |
| F1 | – |
| Đúng mức strong/listed | – |
| Sai số số năm (MAE), lệch ≤ 0,5 năm | – |
| Chức danh hợp lý | – |
| Section đúng | – / 10 |
| CV còn lộ PII | – |

Alias mới từ CV thật và kỹ năng ngoài từ điển: *(điền sau)*.
