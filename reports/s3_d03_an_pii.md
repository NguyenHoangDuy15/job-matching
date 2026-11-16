# S3-D03: Che thông tin cá nhân (PII) trong CV, 20 mẫu

Ngày 17/11/2026 · Duy · Issue #468 (US-12 #403, AC4) · `cvparser.redact`, cấu hình `pii-1`

Mọi mẫu là thông tin **giả** (email @example.com/.vn, SĐT 0912 000 1xx). Báo cáo chỉ ghi số liệu.

## Kết quả: 20/20 mẫu không lộ PII

```
$ uv run pytest tests/unit/test_cv_redact.py      # 40 passed
```

| Bộ | Mẫu | Lộ PII | Che thừa |
|---|---|---|---|
| 10 CV mẫu (`tests/fixtures/cv/samples`, PDF/DOCX qua D01) | 10 | **0** | **0**: tập kỹ năng D04 bắt được trên văn bản đã che **bằng đúng** văn bản gốc |
| 10 mẫu khó (`tests/fixtures/pii/samples.yaml`) | 10 | **0** | **0**: mọi chuỗi phải giữ (kỹ năng, công ty, trường, khoảng thời gian, tỉnh) còn nguyên |

**"Lộ"** được kiểm khắt khe: so không dấu, không phân biệt hoa/thường, gộp khoảng trắng. SĐT và số
giấy tờ so theo dãy số, nên "0912.000.101" còn sót dưới dạng "0912000101" vẫn bị bắt.

### 10 mẫu khó

| Mẫu | Ca khó | Kết quả |
|---|---|---|
| p01 | Tên IN HOA không dấu "NGUYEN VAN HUNG", SĐT `(+84) 912-000-111` | Che hết |
| p02 | Tên kiểu Anh "Hung Nguyen", email viết lách `hung [at] example [dot] com` | Che hết |
| p03 | Một dòng nhiều nhãn: Họ và tên · Ngày sinh · Giới tính; CCCD; SĐT `0912.000.113` | Che giá trị, **giữ nhãn** |
| p04 | Địa chỉ HCM viết tắt không nhãn `123/4 Nguyễn Trãi, P.5, Q.3, TP.HCM` (tên đường trùng tên người) | Che cụm địa chỉ, **giữ "TP.HCM"** |
| p05 | Link Facebook / LinkedIn / GitHub | Che tài khoản, **giữ tên miền** (`github.com/[LINK]`) |
| p06 | Tên lặp trong thân CV ("Tôi là Hà"), người tham chiếu có nhãn kèm chức vụ | Che cả hai tên, **giữ "Trưởng phòng CNTT"** |
| p07 | SĐT dính chữ `Tel:0912000117`, cạnh lương `15.000.000 – 20.000.000`, năm `2019 – 2024`, mã số 10 chữ số | Chỉ che SĐT |
| p08 | Địa chỉ có nhãn đầy đủ, dòng "Kinh nghiệm làm việc với Firebase…" | Che địa chỉ, **giữ "Hà Nội"** |
| p09 | CV tiếng Anh, tên nước ngoài 3 chữ, địa chỉ quận 1 | Che hết, giữ "Ho Chi Minh City" |
| p10 | Không có tên ở đầu CV (tên ở cuối, sau lời xác nhận), ngày sinh, quê quán | Che hết, giữ "Phú Yên" |

## Cách làm

- **Presidio** làm khung (`AnalyzerEngine`, `AnonymizerEngine`). **Không** dùng bộ nhận diện mặc
  định: `DATE_TIME` sẽ che khoảng thời gian làm việc mà S3-D04 cần để tính số năm.
- **Bộ nhận diện riêng cho tiếng Việt** (`config/pii.yaml`):
  - SĐT Việt Nam: đầu số 02/03/05/07/08/09, +84/84, độ dài 10–11 số.
  - Email, kể cả dạng `[at]`/`[dot]`.
  - Nhãn: Họ tên, Địa chỉ, Ngày sinh, CCCD/CMND/Hộ chiếu, Giới tính, Hôn nhân…
  - Địa chỉ không nhãn ở phần đầu CV: từ mạnh (ngõ, hẻm, phường…) và từ yếu chỉ tính khi đi kèm
    số/tên riêng ("đường Láng", "quận 3"), để "nền tảng", "đường ống" không bị coi là địa chỉ.
  - Tên: dòng có họ Việt + 1–3 chữ viết hoa; dòng tên ở đầu CV; spaCy `en_core_web_sm` cho tên
    tiếng Anh (chỉ nhận ở phần đầu CV / mục khác); tên tài khoản (`known_names`).
  - **Tên tìm thấy một lần được che ở mọi chỗ** (viết hoa, không dấu, đảo thứ tự, "Tôi là Hà"),
    nhưng chỉ khi chữ gốc viết hoa đầu mỗi từ ("Cổng thanh toán" không bị che).
- **Giữ lại**: tỉnh/thành ở cuối địa chỉ (trả thêm `province_codes`), tên miền của link, chữ nhãn.
- **Kiểm lần cuối**: quét lại email/SĐT trên văn bản đã che; còn thì che tiếp và ghi cảnh báo.
- `RedactionResult` chỉ giữ loại + vị trí PII, không giữ giá trị (có test kiểm).

## Hiệu năng

Nạp Presidio + spaCy: khoảng 0,8–1,2 giây, một lần mỗi tiến trình (`warm_up()` khi khởi động
API/worker). Che: **khoảng 27 ms/CV** (trung bình 10 CV mẫu), nằm trong ngân sách 15 giây của
US-12 và 50 CV ≤ 60 giây của S6. Image tăng khoảng 50 MB (spaCy + model sm + Presidio).

## Lỗi tìm ra và đã sửa trong lúc làm

- Danh sách từ khóa nối bằng `|` thiếu nhóm `(?:…)`: "ba" (Business Analyst) khớp giữa chữ
  "Bảo", làm sót tên "Trịnh Gia Bảo".
- spaCy nhận "Thành Công" (tên phường) là tên người, rồi bước lan tên che nhầm "Cổng thanh toán"
  trong Kinh nghiệm. Sửa: bỏ tên spaCy nằm trong địa chỉ; lan tên chỉ khớp chữ viết hoa.
- Che cả link GitHub làm mất kỹ năng "GitHub": giờ giữ tên miền.

## Giới hạn / để sau

- Tên người Việt **không có họ phổ biến** và không ở đầu CV / sau nhãn sẽ có thể bị sót. Bù bằng
  `known_names` (S3-D05 truyền tên tài khoản) và kiểm trên CV thật ở S3-D06.
- Không che PII trong ảnh, chữ ký.
- JD vẫn dùng `ingestion.jsonld.mask_contacts` (email/SĐT); chuyển sang `redact` là ticket riêng.

## Dùng ở S3-D05

```python
from cvparser.extract import extract_document
from cvparser.redact import redact
from cvparser.sections import split_sections

result = extract_document(data, filename=name)  # văn bản gốc: chỉ trong bộ nhớ
red = redact(result.text, known_names=[profile.full_name])
secs = split_sections(red.text)  # tách section trên văn bản ĐÃ che
# lưu app.cvs.text_redacted = red.text; mọi lời gọi LLM/embedding chỉ nhận red.text
```
