# S3-D06: Thử 10 CV thật

Mục tiêu: đo độ đúng kỹ năng của chuỗi đọc CV (D01 → D03 → D02 → D04) trên CV thật, và tìm cách
viết kỹ năng mà từ điển còn thiếu (alias).

## 1. Xin phép (bắt buộc, làm trước khi nhận CV)

Gửi từng người (Zalo/Messenger), lưu lại câu trả lời "đồng ý":

> Mình đang làm đồ án hệ thống gợi ý việc làm, cần thử bộ đọc CV trên 10 CV thật. Bạn cho mình
> mượn CV (PDF/DOCX) được không? Cam kết: CV chỉ nằm trên máy mình, không đưa lên GitHub, không
> gửi cho dịch vụ AI bên ngoài; hệ thống tự che tên, SĐT, email, địa chỉ; báo cáo chỉ ghi số liệu
> (độ đúng, tên kỹ năng), không ghi nội dung CV; xong đồ án mình xóa file. Bạn đồng ý không?

Nên chọn CV đa dạng: ngành (backend, frontend, data, tester, BA, thiết kế…), Việt/Anh, 1 cột/2
cột, PDF xuất từ Word/Canva/TopCV, có ít nhất 1 DOCX.

## 2. Chạy

```bash
mkdir -p data/cv_real              # thư mục data/ không lên git
# chép 10 CV vào data/cv_real/ (tên file tùy ý; script đổi thành cvr01..cvr10)
uv run python scripts/eval_cv_real.py run
```

Tạo ra (đều trong `data/`, không lên git):

| File | Nội dung |
|---|---|
| `data/eval/cv_real/cvrXX.md` | Văn bản CV **đã che PII**, kỹ năng máy tìm (mức, mục, công ty, câu trích), số năm, chức danh |
| `data/eval/cv_real/_map.csv` | Đối chiếu cvrXX ↔ tên file (để bạn mở file gốc khi chấm) |
| `data/eval/cv_real_skills.csv` | Mỗi kỹ năng máy gắn một dòng |
| `data/eval/cv_real_missing.csv` | Kỹ năng máy bỏ sót |
| `data/eval/cv_real_meta.csv` | Mỗi CV một dòng: số năm, chức danh, section, lộ PII |

## 3. Chấm tay (mỗi CV khoảng 10 phút)

Mở **file CV gốc** cạnh `cvrXX.md`:

**`cv_real_skills.csv`**: mỗi dòng là một kỹ năng máy gắn.

| Cột | Điền |
|---|---|
| `dung` | `y` nếu CV đúng là có kỹ năng này; `n` nếu máy nhận nhầm (từ thường, tên công ty, tên trường…) |
| `muc_dung` | Để trống nếu máy đúng mức. Ghi `strong` / `listed` nếu máy sai mức. **strong** = có dùng trong Kinh nghiệm/Dự án; **listed** = chỉ ghi ở mục Kỹ năng/Tóm tắt/Chứng chỉ |
| `note` | Lý do khi `n`, ví dụ "tên công ty", "nghĩa khác" |

**`cv_real_missing.csv`**: kỹ năng có trong CV mà máy **không** gắn. Mỗi kỹ năng một dòng (thêm
dòng, ghi `cv` = cvrXX).

| Cột | Điền |
|---|---|
| `ky_nang` | Tên kỹ năng chuẩn, ví dụ "Spring Boot", "Power BI" |
| `cach_viet` | **Chép đúng chữ trong CV**, ví dụ "SpringBoot 3", "PowerBI", "Ms Excel": dùng để đề xuất alias |
| `muc` | `strong` / `listed` |

Không ghi kỹ năng chung chung (chăm chỉ, chịu áp lực), bằng cấp, số năm kinh nghiệm.

**`cv_real_meta.csv`**: mỗi CV một dòng.

| Cột | Điền |
|---|---|
| `so_nam_dung` | Số năm kinh nghiệm bạn tính tay từ CV (không tính thực tập, gộp việc làm song song) |
| `chuc_danh_dung` | `y` nếu chức danh máy đề xuất hợp lý; không thì ghi chức danh đúng |
| `section_dung` | `y` nếu các mục (Kinh nghiệm, Dự án, Kỹ năng, Học vấn) trong `cvrXX.md` đúng |
| `pii_lo` | `y` nếu văn bản đã che **còn** tên, SĐT, email, địa chỉ của chủ CV (ghi chỗ lộ vào `note`) |

## 4. Chấm điểm và gửi kết quả

```bash
uv run python scripts/eval_cv_real.py score
```

In ra precision / recall / F1 kỹ năng, đúng mức, sai số số năm, chức danh, section, PII lộ, và
**danh sách alias thiếu** (kỹ năng có trong từ điển nhưng thiếu cách viết như trong CV) cùng kỹ năng
ngoài từ điển. Kết quả lưu `reports/eval_cv_real.json` (chỉ số liệu và tên kỹ năng).

Gửi Duy/Claude file JSON này → thêm alias vào `config/skills.yaml`, chạy lại `run --force` để đo
lần 2, viết báo cáo `reports/s3_d06_cv_that.md`.

## 5. Sau khi xong đồ án

Xóa `data/cv_real/` và `data/eval/cv_real*` như đã hứa với chủ CV.
