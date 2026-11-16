# Plan S3-D01: trích văn bản CV (PDF, DOCX) và bộ 10 CV mẫu ẩn danh

- Task: [#463](https://github.com/NguyenHoangDuy15/job-matching/issues/463) · Story US-12 ([#403](https://github.com/NguyenHoangDuy15/job-matching/issues/403)) · Thứ 2 16/11/2026 · Duy · 4h
- Kiểm tra "xong": 10/10 CV ra văn bản đọc được
- Trạng thái: **đã duyệt 16/11** (7 file sinh bằng script + 3 làm tay; commit mẫu; không OCR, không `.doc`; 5 MB / 10 trang / 10 giây; thêm `extract_many` chạy lô ngay ở D01; cắt TCVN3, CER, lexicon khỏi D01)

## 0. Tóm tắt

Viết một module thuần (bytes vào, kết quả có cấu trúc ra) trong `src/cvparser/`. Module này không biết gì về DB, Storage, FastAPI hay hàng đợi. Nhờ vậy:

- S3-D05 (`POST /cv/parse`) gọi trực tiếp cho 1 CV.
- S6-D03 (worker đọc lô qua pgmq) gọi y như vậy cho từng file, việc lô nằm ở lớp runner bên ngoài.
- US-20/US-23 (người dùng/HR tải JD dạng PDF/DOCX) dùng lại được, vì không có logic riêng của CV ở tầng trích văn bản.

S3-D01 chỉ làm phần trích văn bản, đo chất lượng, bộ mẫu và test. Hàng đợi, worker, OCR, `.doc` để sau. Ngay bây giờ chỉ chốt interface để làm các phần đó không phải sửa nơi gọi.

## 1. Bối cảnh trong repo (đã đọc)

| Điều | Ở đâu | Ảnh hưởng tới plan |
|---|---|---|
| `src/cvparser/` đã có, docstring "F4 – đọc CV, ẩn PII. Chủ sở hữu: Duy" | `src/cvparser/__init__.py` | Đặt code ở đây, không tạo gói mới |
| `app.cvs` chỉ nhận `application/pdf` và DOCX, `size_bytes <= 5 MB`, `parse_status in (queued, parsing, parsed, failed)`, `parse_error text`, `file_sha256` + unique index chống trùng | `db/migrations/0001_schema_v2.sql:370` | Giới hạn 5 MB, mã lỗi ghi vào `parse_error`, dùng sha256 cho idempotency |
| DB chỉ giữ `text_redacted`, không giữ văn bản thô | cùng file, và kế hoạch dự án ("DB chỉ giữ văn bản đã che PII") | Văn bản thô chỉ sống trong bộ nhớ, không log, không lưu DB |
| Bucket `cvs` private, `allowed_mime_types` chỉ PDF/DOCX | `0001_schema_v2.sql:1497` | `.doc`, ảnh bị chặn ngay từ upload, parser vẫn phải tự kiểm tra vì không tin đuôi file |
| `.gitignore` chặn `data/*`, `*.pdf`, `*.docx`, `*.doc`, `*.zip` trên toàn repo | `.gitignore` | Muốn commit CV mẫu phải mở ngoại lệ riêng cho `tests/fixtures/cv/` |
| Model dữ liệu dùng pydantic v2 `frozen` | `src/ingestion/models.py` | Kết quả trích cũng dùng pydantic: ra JSON cho API và hàng đợi dễ |
| Script đặt ở `scripts/*.py`, chạy `uv run python scripts/x.py <lệnh>`, đầu ra nội dung vào `data/`, chỉ số vào `reports/` | `scripts/evaluate_extraction.py` | CLI `scripts/extract_cv.py` theo cùng mẫu |
| CI chạy `ruff check`, `ruff format --check`, `pytest -q`, gitleaks | `.github/workflows/ci.yml` | Fixture nhị phân phải nhỏ, test không cần font hay phần mềm ngoài |
| `skillkit.matcher.prepare()` chuẩn hóa NFC + gộp khoảng trắng | `src/skillkit/matcher.py` | Văn bản ra phải NFC, nếu không thì FlashText trượt chữ có dấu |
| `skillkit.sections` tách section JD theo heading trên **từng dòng** | `src/skillkit/sections.py` | Văn bản CV phải giữ heading trên dòng riêng, S3-D02 làm tương tự với `config/cv_headings.yaml` |
| Kế hoạch dự án chọn `pypdfium2/pdfplumber, python-docx, Presidio`; Docker image `python3.11-bookworm-slim` | docx kế hoạch, `Dockerfile` | Không thêm phần mềm hệ thống (Tesseract, LibreOffice) ở S3-D01 |

Các task sau dùng kết quả này:

| Task | Ngày | Cần gì từ S3-D01 |
|---|---|---|
| S3-D02 Tách section CV | 17/11 | Heading nằm trên dòng riêng, đúng thứ tự đọc (CV 2 cột không bị trộn dòng), gợi ý heading (style DOCX, cỡ chữ/đậm PDF nếu kịp) |
| S3-D03 Ẩn PII (Presidio + regex) | 17/11 | Lấy được cả header/footer và text box, nơi hay chứa tên, email, SĐT. Bộ mẫu có PII **giả** đủ dạng để test |
| S3-D04 Mức bằng chứng + đoạn trích + số năm | 18/11 | Offset của từng khối trong `text` để cắt đoạn trích; bảng kinh nghiệm giữ đúng hàng (công ty, thời gian) |
| S3-D05 `POST /cv/parse` ≤ 15 giây | 18/11 | Mã lỗi rõ ràng + thông điệp tiếng Việt cho UI; có giới hạn trang/thời gian |
| S3-D06 Thử 10 CV thật | 19/11 | CLI chạy cả thư mục, báo cáo chỉ số không lộ nội dung |
| S6-T02 / S6-D03 Worker lô pgmq, 50 CV ≤ 60 giây | 08/12 | Hàm thuần, không ném lỗi vì file xấu, có version để idempotent, chạy được trong process riêng |

## 2. Phân tích yêu cầu

"Văn bản đọc được" nghĩa là đọc được **cho máy ở bước sau**, không chỉ cho người:

1. Đủ chữ, đúng dấu tiếng Việt (NFC), không có ký tự rác.
2. Đúng thứ tự đọc: với CV 2 cột, hết cột này mới sang cột kia, không trộn từng dòng của 2 cột.
3. Giữ cấu trúc: heading trên dòng riêng, khối cách nhau bằng dòng trống, gạch đầu dòng còn, hàng của bảng không bị vỡ.
4. Không mất phần nằm ngoài thân văn bản: bảng, text box, header/footer.
5. File không đọc được thì trả lý do rõ ràng, không làm sập cả lô.

## 3. Rủi ro và cách xử lý

### 3.1 PDF

| Rủi ro | Dấu hiệu | Xử lý ở S3-D01 | Để sau |
|---|---|---|---|
| PDF scan, không có lớp chữ | Gần như không có ký tự, trang có ảnh lớn | Phát hiện: < 20 ký tự/trang trên ≥ 50% số trang và có ảnh → lỗi `ocr_required` | OCR (Tesseract + `vie`, hoặc LLM vision) nếu nhóm quyết làm |
| CV 2 cột (Canva, TopCV, mẫu Word) | Dòng 2 cột xen kẽ nhau | Dùng thứ tự content stream của pypdfium2. Các file xuất từ Canva/Word thường để mỗi cột là một khung chữ, nên thứ tự này đúng. pdfplumber `extract_text()` sắp theo tọa độ y nên dễ trộn 2 cột, vì vậy không dùng nó cho văn bản chính | Nếu cv03/cv07 trượt kiểm thứ tự: dựng lại theo cột từ `extract_words()` (tìm khe trống theo trục x), ghi cảnh báo `reordered_columns` |
| Bảng | Nội dung bảng bị dàn phẳng | Văn bản chính vẫn lấy từ pypdfium2 (không lặp). Bảng lấy thêm bằng `pdfplumber.find_tables()` thành `tables[]` có trang + bbox + hàng/ô | Bảng không kẻ khung (`text` strategy) nếu cần |
| Font lỗi (thiếu ToUnicode, subset) | `(cid:123)`, U+FFFD, ký tự vùng riêng (PUA) | Đo `garbled_ratio`, quá ngưỡng → lỗi `unreadable_text` | Thử lại bằng engine thứ hai (pdfminer) cho trang lỗi |
| Bảng mã tiếng Việt cũ (TCVN3/.VnTime, VNI) | "Kinh nghiÖm", "§¹i häc" | Phát hiện bằng tần suất ký tự đặc trưng → cảnh báo `legacy_vn_encoding` | Bảng chuyển TCVN3/VNI → Unicode |
| Dấu tiếng Việt tách rời | Dấu kết hợp đứng riêng, có dấu cách trước dấu | NFC + bỏ dấu cách đứng trước dấu kết hợp | |
| Chữ giãn cách ở heading | "K I N H  N G H I Ệ M" | Gộp khi có ≥ 4 chữ cái đơn liền nhau, test kỹ để không gộp nhầm "C C++" | |
| Icon font (Font Awesome cho điện thoại, email) | Ký tự PUA trước dòng liên hệ | Bỏ PUA đơn lẻ ở đầu dòng, không tính vào garbled | |
| Chữ trắng/ẩn để nhồi từ khóa | Kỹ năng "ảo" khi matching | Chưa xử lý | Cờ `hidden_text_suspected` (màu chữ trùng nền) |
| Mã hóa | Có user password | Có owner password, user password rỗng: PDFium tự mở, không báo lỗi. Có user password: lỗi `encrypted` | |
| Hỏng/cắt cụt | `PdfiumError` | Lỗi `corrupt_file` | |
| File quá lớn, quá nhiều trang, PDF "bom" | Tốn RAM/CPU | ≤ 5 MB; chỉ xử lý `max_pages` trang đầu (đề xuất 10), cảnh báo `truncated_pages`; trần `max_chars` | Timeout cứng bằng process riêng (xem 5.3) |
| PDFium không an toàn khi chạy đa luồng | Crash ngẫu nhiên khi FastAPI chạy endpoint sync trong threadpool | Ghi trong docstring: một process một tài liệu; trong process dùng một lock quanh lời gọi pypdfium2 | Worker lô dùng process, không dùng thread |
| Metadata lộ PII | `/Author` là tên thật | Không đưa Author/Subject/Keywords vào kết quả, chỉ giữ producer/creator/số trang | |

### 3.2 DOCX

| Rủi ro | Xử lý |
|---|---|
| `document.paragraphs` bỏ sót bảng, text box, content control (`w:sdt`) và đảo thứ tự | Tự duyệt `body` theo thứ tự XML: `w:p`, `w:tbl`, `w:sdt` |
| Text box (`w:txbxContent`) xuất hiện 2 lần trong `mc:AlternateContent` (Choice và Fallback VML) | Chỉ lấy nhánh `mc:Choice`, bỏ `mc:Fallback` |
| Ô gộp (`gridSpan`, `vMerge`) làm `row.cells` trả trùng ô | Khử trùng theo đối tượng `_tc` |
| Bảng dùng làm bố cục 2 cột (rất hay gặp ở mẫu CV Word) | Bảng ≤ 2 cột và ô chứa nhiều đoạn → `kind="layout"`: xuất từng ô thành khối, hết cột trái rồi sang cột phải. Bảng còn lại → `kind="data"`: mỗi hàng một dòng `ô1 \| ô2 \| ô3` |
| Header/footer có tên, liên hệ | Lấy thành khối `source="header"/"footer"`, đặt đầu/cuối văn bản; khử trùng header lặp giữa các section |
| Track changes, field code | Lấy `w:t` trong `w:ins`, bỏ `w:del`/`w:delText`, bỏ `w:instrText` (python-docx `paragraph.text` bỏ sót run nằm trong `w:ins`) |
| Danh sách đánh số (`w:numPr`) | Thêm tiền tố `- ` để giữ dấu hiệu gạch đầu dòng |
| Heading theo style (`Heading 1`, `Title`) | `Block.kind="heading"` + `style`: S3-D02 dùng làm gợi ý mạnh |
| SmartArt, ảnh chứa chữ | Không lấy được; cảnh báo `smartart_ignored`; CV toàn ảnh → `ocr_required` |
| Zip bomb, XML khổng lồ | Kiểm tra tổng kích thước giải nén và tỷ lệ nén trước khi mở (đề xuất ≤ 50 MB, tỷ lệ ≤ 100) → `too_large` |
| `.docm`, `.dotx`, `.xlsx`, `.pptx`, `.odt` cùng chữ ký ZIP | Đọc `[Content_Types].xml`, chỉ nhận main part `wordprocessingml.document.main+xml`; còn lại `unsupported_type` |

### 3.3 `.doc` và ảnh

- `.doc` (Word 97–2003, chữ ký OLE `D0 CF 11 E0`): không có thư viện Python thuần đáng tin; muốn đọc phải có antiword (GPL) hoặc LibreOffice headless (image nặng thêm vài trăm MB). DOCX có đặt mật khẩu cũng nằm trong vỏ OLE này. **Đề xuất:** nhận diện rồi trả `unsupported_type` (chi tiết `legacy_doc`) kèm thông điệp "Hãy lưu lại dưới dạng .docx hoặc PDF". Cách này khớp ràng buộc mime trong `app.cvs` và AC của US-11.
- Ảnh JPG/PNG/HEIC: nhận diện theo magic bytes rồi trả `unsupported_type` (chi tiết `image`). Gộp chung với quyết định OCR.

## 4. Kiến trúc module

### 4.1 Luồng

```
bytes (+ filename tùy chọn, chỉ để cảnh báo lệch đuôi)
  │
  ├─ limits: rỗng? > max_bytes?                      → empty_file / too_large
  ├─ sniff (magic bytes)  → FileKind                 → unsupported_type
  │     %PDF- trong 1024 byte đầu → pdf
  │     PK\x03\x04 + [Content_Types].xml có word main → docx
  │     D0CF11E0 → ole (legacy_doc / encrypted office)
  │     FFD8FF / 89PNG / GIF8 / RIFF…WEBP / ftypheic → image
  ├─ registry[FileKind] → Extractor.extract()        → encrypted / corrupt_file / …
  │     trả RawDocument: pages[blocks], tables, metadata, warnings
  ├─ normalize: NFC, dấu tách rời, zero-width, soft hyphen, ligature, PUA, CRLF, giãn cách
  ├─ assemble: nối khối → text (khối cách "\n\n", dòng cách "\n"), ghi offset start/end
  └─ quality: chỉ số + readable                      → ocr_required / unreadable_text
        → ExtractionResult (status ok | partial | failed)
```

`extract_document()` **không ném lỗi vì file xấu**. Mọi lỗi của file thành `status="failed"` + `error.code`. Lỗi lập trình bất ngờ trong extractor bị bắt thành `internal_error`, chỉ ghi tên lớp exception (message có thể chứa nội dung file nên không ghi). Đây là tầng cô lập lỗi thứ nhất. Tầng thứ hai (process riêng, timeout) nằm ở runner lô.

### 4.2 Interface

```python
# src/cvparser/extract/registry.py
class Extractor(Protocol):
    kind: FileKind  # "pdf" | "docx"
    version: str  # "pdf-1", tăng khi đổi logic → kết quả cũ hết hiệu lực

    def extract(self, data: bytes, options: ExtractOptions) -> RawDocument: ...


_REGISTRY: dict[FileKind, Extractor] = {}


def register(extractor: Extractor) -> None: ...
def get_extractor(kind: FileKind) -> Extractor | None: ...
```

Thêm định dạng mới (`.doc` qua LibreOffice, ảnh qua OCR) = viết một lớp Extractor mới rồi `register()`, không sửa `extract_document()` hay nơi gọi.

```python
# src/cvparser/extract/__init__.py — API công khai
def extract_document(
    data: bytes,
    *,
    filename: str | None = None,
    options: ExtractOptions | None = None,
) -> ExtractionResult: ...
```

### 4.3 Kết quả có cấu trúc (pydantic v2, `frozen`)

```python
class ExtractOptions(BaseModel):
    max_bytes: int = 5 * 1024 * 1024  # khớp app.cvs và bucket
    max_pages: int = 10
    max_chars: int = 100_000
    extract_tables: bool = True
    max_unzipped_bytes: int = 50 * 1024 * 1024


class Block(BaseModel):
    kind: Literal["heading", "paragraph", "list_item", "table_row", "table_cell"]
    source: Literal["body", "header", "footer", "textbox", "table"]
    text: str
    page: int | None  # PDF: số trang; DOCX: None
    bbox: tuple[float, float, float, float] | None
    style: str | None = None  # DOCX: tên style
    font_size: float | None = None  # PDF: nếu kịp (gợi ý heading cho S3-D02)
    bold: bool | None = None
    start: int  # offset trong ExtractionResult.text
    end: int


class Table(BaseModel):
    page: int | None
    bbox: tuple[float, float, float, float] | None
    kind: Literal["data", "layout"]
    rows: list[list[str]]


class Quality(BaseModel):
    char_count: int
    word_count: int
    pages_total: int
    pages_without_text: int
    letter_ratio: float  # chữ cái / ký tự không trắng
    garbled_ratio: float  # (cid:n), U+FFFD, PUA, ký tự điều khiển / tổng
    vi_diacritic_ratio: float  # từ có dấu tiếng Việt / tổng từ (để biết dấu còn hay mất)
    lexicon_hit_ratio: float  # tỷ lệ từ thuộc danh sách từ phổ biến Việt + Anh
    readable: bool
    reasons: list[str]  # vì sao readable=False


class ErrorInfo(BaseModel):
    code: ErrorCode
    detail: str | None  # không chứa nội dung file
    message_vi: str  # cho UI S3-H01/S3-H02


class Warning_(BaseModel):
    code: str  # truncated_pages, extension_mismatch, legacy_vn_encoding, ...
    page: int | None = None


class ExtractionResult(BaseModel):
    schema_version: Literal[1] = 1
    parser_version: str  # "cvparser-1/pdf-1"
    status: Literal["ok", "partial", "failed"]
    error: ErrorInfo | None
    file: FileInfo  # sha256, size_bytes, kind, mime, declared_ext, page_count
    text: str
    blocks: list[Block]
    tables: list[Table]
    metadata: dict[str, str]  # chỉ trường kỹ thuật: producer, creator, pdf_version
    warnings: list[Warning_]
    quality: Quality | None
    timings_ms: dict[str, float]  # sniff, extract, tables, normalize, quality
```

- `partial`: có văn bản dùng được nhưng có cảnh báo nặng (cắt trang, một số trang không có chữ). Pipeline vẫn đi tiếp và lưu cảnh báo.
- `text` là thứ S3-D02 dùng. `blocks` cho phần cần nhiều thông tin hơn: style heading, offset để cắt đoạn trích (S3-D04), nguồn header/footer (S3-D03).
- Lưu ý cho S3-D04: `skillkit.matcher.prepare()` gộp khoảng trắng nên offset khớp kỹ năng không còn trùng offset trong `text`. S3-D04 cần ánh xạ ngược, hoặc chạy matcher theo từng khối. Ghi lại ở đây để khỏi bất ngờ.

### 4.4 Mã lỗi

| `code` | Khi nào | `message_vi` (gợi ý) | Thử lại? |
|---|---|---|---|
| `empty_file` | 0 byte | File rỗng | Không |
| `too_large` | > 5 MB, hoặc DOCX giải nén quá lớn | File vượt 5 MB | Không |
| `unsupported_type` (`legacy_doc`, `image`, `zip`, `other`) | Magic bytes không phải PDF/DOCX | Chỉ nhận PDF hoặc DOCX. File .doc hãy lưu lại thành .docx | Không |
| `encrypted` | PDF có user password, OOXML có mật khẩu | File đang đặt mật khẩu, hãy gỡ mật khẩu rồi tải lại | Không |
| `corrupt_file` | Thư viện không mở được | File bị hỏng hoặc tải lên chưa đủ | Không |
| `ocr_required` | Không có lớp chữ | CV có vẻ là ảnh scan, hãy tải bản xuất trực tiếp từ Word/Canva | Không (cho tới khi có OCR) |
| `unreadable_text` | Có chữ nhưng rác (font lỗi) | Không đọc được chữ trong file, hãy xuất lại PDF | Không |
| `timeout` | Runner giết process quá hạn | Xử lý quá lâu | 1 lần |
| `internal_error` | Exception không lường trước | Lỗi hệ thống | 1 lần |

`parse_error` trong `app.cvs` lưu `code` (và `detail` nếu có). UI tra `message_vi`.

## 5. Hướng mở rộng cho xử lý hàng loạt

### 5.1 Luồng đích (S6, Tùng làm hàng đợi, Duy nối parser)

```
HR tải ≤ 50 file / .zip (S6-T01)
  → Storage o/{org}/{job}/{cv_id}.pdf + app.cvs(parse_status='queued', file_sha256)
       unique (job_id, file_sha256): tải trùng file thì không tạo bản ghi mới
  → pgmq.send('cv_parse', {cv_id, file_sha256, pipeline_version})
Worker Cloud Run Job (S6-T02), mỗi vòng pgmq.read(vt=60s, qty=k):
  → UPDATE app.cvs SET parse_status='parsing' WHERE id=$1 AND parse_status IN ('queued','parsing')
  → tải file → kiểm tra sha256 khớp
  → extract_document() trong process con, timeout cứng   ← S3-D01 cung cấp
  → redact (S3-D03) → sections (S3-D02) → skills/evidence (S3-D04) → embedding (S6-D03)
  → một transaction: ghi text_redacted, parsed_sections, cv_skills, cv_chunks, parse_status='parsed'
  → pgmq.delete(msg)
Lỗi:
  vĩnh viễn (bảng 4.4, "Không") → parse_status='failed', parse_error=code, delete msg
  tạm thời (mạng, DB, timeout lần 1) → để msg hiện lại sau vt
  read_ct > 3 → failed 'retry_exhausted', pgmq.archive (không thành poison message)
Tiến độ (S6-T03): đếm parse_status theo job_id, Supabase Realtime trên app.cvs
```

### 5.2 Idempotency

- Khóa: `(file_sha256, parser_version)`. Cùng file, cùng version thì kết quả trích giống hệt (hàm thuần, không phụ thuộc thời gian/thứ tự). Tăng `version` của extractor là cách duy nhất để buộc đọc lại.
- pgmq giao ít nhất một lần, nên mọi bước ghi phải chạy lại được: UPDATE có điều kiện theo trạng thái, `INSERT … ON CONFLICT` cho `cv_skills`/`cv_chunks`, xóa chunk cũ của `cv_id` trước khi ghi.
- Không dùng cache kết quả theo sha256 **giữa các tenant** (hai công ty có cùng file vẫn đọc riêng), vì cache chung làm lộ việc "file này đã có người khác tải".

### 5.3 Giới hạn và cô lập lỗi

| Lớp | Cơ chế | Làm ở |
|---|---|---|
| Trong hàm | Không ném lỗi vì file xấu; trần bytes/pages/chars/unzip | **S3-D01** |
| Mỗi file | Process con + timeout cứng (đề xuất 10 giây/file, nằm trong ngân sách 15 giây của US-12). PDFium là thư viện C, `signal.alarm`/thread không ngắt được, chỉ kill process mới chắc | S3-D05 (API 1 file) và S6-D03 (lô) |
| Song song | Số process = số vCPU; không dùng thread cho pypdfium2; tái tạo process sau N file để chặn rò bộ nhớ | S6-D03 |
| Bộ nhớ | ≤ 5 MB/file, ≤ 10 trang; đóng `page`/`textpage`/`pdf`, `pdfplumber` dùng `with` | **S3-D01** |
| Đo | `timings_ms` từng bước; benchmark 10 CV mẫu (pytest-benchmark đã có trong repo) | **S3-D01** (đo), S6-D06 (tối ưu) |

Ngân sách thời gian: 50 CV ≤ 60 giây kể cả embedding, tức phần trích văn bản nên ≤ ~0,3 giây/CV. pypdfium2 cỡ vài ms/trang. pdfplumber (pdfminer viết bằng Python thuần) cỡ 0,1–0,3 giây/trang nên là phần đắt nhất: giữ `max_pages`, có cờ `extract_tables` để tắt khi cần.

### 5.4 Phân định phạm vi

| Hạng mục | S3-D01 | Sau |
|---|---|---|
| Interface Extractor + registry + sniff magic bytes | ✅ | |
| PDF (pypdfium2 văn bản, pdfplumber bảng), DOCX (python-docx, tự duyệt XML) | ✅ | |
| Chuẩn hóa Unicode, chỉ số chất lượng, mã lỗi + thông điệp tiếng Việt | ✅ | |
| Bộ 10 CV mẫu + bộ file lỗi + test + CLI + báo cáo | ✅ | |
| Dựng lại thứ tự cột từ tọa độ | Chỉ khi mẫu 2 cột trượt kiểm thứ tự | S3-D02 nếu cần |
| Gợi ý heading cho PDF (cỡ chữ, đậm) | Nếu còn giờ | S3-D02 |
| Process con + timeout cứng | Chỉ chừa tham số | S3-D05 / S6-D03 |
| pgmq, worker, tiến độ, retry | | S6-T02, S6-D03 |
| OCR, `.doc`, chuyển TCVN3/VNI | | Chờ quyết định (mục 10) |
| Phát hiện chữ ẩn nhồi từ khóa | | Backlog |

## 6. Đo "văn bản đọc được"

### 6.1 Chỉ số tự động (chạy trong pytest và CLI)

Một CV **đạt** khi có đủ:

1. `status != "failed"`.
2. `quality.readable`: `char_count ≥ 300`, `garbled_ratio ≤ 0,01`, `letter_ratio ≥ 0,6`, `lexicon_hit_ratio ≥ 0,3`; với CV tiếng Việt thêm `vi_diacritic_ratio ≥ 0,15` (bắt trường hợp mất dấu).
3. **Độ phủ mốc** ≥ 95%: mỗi CV mẫu có file kỳ vọng liệt kê 15–30 cụm phải xuất hiện nguyên vẹn (so sau NFC + gộp khoảng trắng): heading mục, tên công ty, chức danh, khoảng thời gian, 5–10 kỹ năng, một dòng của bảng. Cụm nhiều từ phải liền nhau, nên bắt được lỗi trộn dòng 2 cột.
4. **Thứ tự mốc**: các heading mục và mốc trong cùng một cột xuất hiện đúng thứ tự (độ dài dãy con tăng dài nhất / số mốc ≥ 0,9).
5. Không có chuỗi cấm: `(cid:`, U+FFFD, chữ giãn cách chưa gộp.
6. Với CV sinh bằng script: có văn bản gốc nên đo thêm **tỷ lệ lỗi ký tự (CER)** giữa văn bản trích và văn bản gốc sau chuẩn hóa, mục tiêu ≤ 2%.

Ngưỡng ở mục 2 là ước lượng ban đầu, chỉnh lại sau khi chạy 10 mẫu và 10 CV thật ở S3-D06.

### 6.2 Kiểm tay

`data/eval/cv_text_review.csv` (không lên git vì chứa văn bản; ở bộ mẫu thì nội dung giả nhưng giữ cùng quy trình với CV thật ở S3-D06). Mỗi CV mở file gốc cạnh `.txt` đã trích, chấm 0/1/2 cho 5 tiêu chí:

| Tiêu chí | 2 | 1 | 0 |
|---|---|---|---|
| Chữ và dấu | Đúng hết | Vài lỗi nhỏ | Mất dấu, rác |
| Thứ tự đọc | Đúng | Lệch vị trí một khối | Trộn dòng 2 cột |
| Đủ nội dung | Đủ | Thiếu chi tiết nhỏ | Thiếu cả mục/bảng/text box |
| Cấu trúc | Heading riêng dòng, gạch đầu dòng còn | Một phần | Thành một khối liền |
| Bảng | Hàng nguyên vẹn | Ô lệch | Vỡ bảng |

**Đạt khi không có điểm 0 nào.** "10/10" = 10 CV đạt cả 6.1 lẫn 6.2. Báo cáo `reports/s3_d01_trich_van_ban_cv.md` chỉ ghi chỉ số (loại file, số trang, số ký tự, garbled, độ phủ mốc, thứ tự, CER, ms, điểm kiểm tay), không chép nội dung CV.

## 7. Bộ 10 CV mẫu ẩn danh

### 7.1 Nguyên tắc riêng tư

- **Không dùng CV thật cho bộ mẫu trên git.** Mọi nội dung là hồ sơ giả viết mới; không "ẩn danh" CV thật bằng cách sửa tên, vì kinh nghiệm, công ty, mốc thời gian vẫn nhận ra người.
- PII giả nhưng **đúng dạng** để S3-D03 test được: tên Việt có dấu, email `@example.com`/`@example.vn`, SĐT dạng 09xx/03xx/+84 (dùng một danh sách số cố định khai báo trong `personas.yaml`), địa chỉ dạng "Số 12 ngõ 34 phố …, phường …, Hà Nội" với tên đường hư cấu.
- Xóa metadata trước khi commit: PDF `/Author`, `/Creator` có tên người; DOCX `docProps/core.xml` (`creator`, `lastModifiedBy`). File xuất từ Word/Canva hay mang tên tài khoản của người làm.
- Test chặn (chạy trong CI): mọi email trong văn bản trích phải thuộc `example.com`/`example.vn`; mọi SĐT phải nằm trong danh sách giả; metadata tác giả rỗng. Thêm CV mới có PII thật thì CI đỏ.
- CV thật (S3-D06, bạn bè đã xin phép) chỉ nằm ở `data/cv_real/` (đã gitignore), báo cáo chỉ ghi chỉ số. CLI không in nội dung ra terminal trừ khi gọi rõ `--print`.

### 7.2 Danh sách 10 CV

| # | File | Cách tạo | Kiểm điều gì |
|---|---|---|---|
| cv01 | PDF 1 cột, tiếng Việt, Backend | Script (reportlab, font Unicode nhúng) | Dấu tiếng Việt, heading, gạch đầu dòng |
| cv02 | PDF 1 cột, tiếng Anh, Data | Script | CV tiếng Anh, ngưỡng lexicon |
| cv03 | PDF 2 cột: cột trái liên hệ + kỹ năng, cột phải kinh nghiệm | Script (2 frame) | Thứ tự đọc 2 cột |
| cv04 | PDF có bảng kẻ khung (kinh nghiệm, kỹ năng/mức) | Script | pdfplumber bảng, hàng không vỡ |
| cv05 | PDF 2 trang, header/footer lặp, số trang | Script | Nhiều trang, header lặp |
| cv06 | PDF xuất từ Word hoặc Google Docs | Làm tay, nội dung giả | Font subset, ligature, PDF "thật" |
| cv07 | PDF xuất từ mẫu Canva 2 cột có icon | Làm tay, nội dung giả | Icon font PUA, chữ giãn cách, khó nhất |
| cv08 | DOCX có style Heading, danh sách đánh số, Việt + Anh | Script (python-docx) | Style heading, numbering |
| cv09 | DOCX dùng bảng làm bố cục 2 cột, header có tên + liên hệ, ô gộp | Script | Bảng bố cục, header, ô gộp |
| cv10 | DOCX có text box, hyperlink, footer | Làm tay trong Word (python-docx không tạo được text box) | Text box không lặp, hyperlink |

Bộ file lỗi (không tính vào 10/10, kỳ vọng thất bại đúng mã):

| File | Tạo | Kỳ vọng |
|---|---|---|
| `scan_image_only.pdf` | Render cv01 thành ảnh bằng pypdfium2, Pillow lưu lại thành PDF | `ocr_required` |
| `encrypted_userpw.pdf` | reportlab `encrypt=` | `encrypted` |
| PDF cắt cụt, file rỗng, PNG, chữ ký OLE (`.doc`), ZIP thường, XLSX, DOCX đổi đuôi `.pdf`, PDF 30 trang, DOCX nén quá mức | Tạo ngay trong test từ bytes, không lưu file | `corrupt_file`, `empty_file`, `unsupported_type`, đọc được + `extension_mismatch`, `truncated_pages`, `too_large` |

### 7.3 Lưu ở đâu

```
tests/fixtures/cv/
  README.md            nguồn gốc từng file, cam kết không có PII thật, cách sinh lại
  personas.yaml        nội dung giả của cv01–cv05, cv08–cv09 (nguồn sự thật cho CER)
  samples/cv01_pdf_1col_vi.pdf … cv10_docx_textbox.docx
  expected/cv01.yaml … cv10.yaml     mốc phải có, thứ tự, số trang, số bảng, ngôn ngữ
  edge/scan_image_only.pdf, edge/encrypted_userpw.pdf
```

- Commit file nhị phân (mỗi file vài chục KB, tổng < 1 MB) để CI không cần reportlab hay font. Thêm vào `.gitignore`:
  ```
  !tests/fixtures/cv/**/*.pdf
  !tests/fixtures/cv/**/*.docx
  ```
- Script sinh: `scripts/make_cv_samples.py` (reportlab chỉ ở nhóm dev). Chạy lại script ra cùng nội dung; không cần ra cùng byte.

## 8. Cấu trúc thư mục và file

```
src/cvparser/
  __init__.py                 giữ docstring F4; re-export extract_document, ExtractionResult
  extract/
    __init__.py               extract_document(): limits → sniff → registry → normalize → quality
    models.py                 ExtractOptions, Block, Table, Quality, ErrorInfo, ExtractionResult, FileInfo
    errors.py                 ErrorCode (StrEnum), ExtractionError, MESSAGES_VI
    sniff.py                  detect_kind(data) -> FileKind + chi tiết; kiểm tra zip an toàn
    registry.py               Extractor Protocol, register(), get_extractor()
    normalize.py              chuẩn hóa Unicode, giữ dòng/khối
    quality.py                chỉ số + readable; danh sách từ phổ biến Việt/Anh nhỏ nằm trong file
    pdf.py                    PdfExtractor (pypdfium2 + pdfplumber), lock PDFium
    docx.py                   DocxExtractor (python-docx + duyệt XML)
scripts/
  extract_cv.py               run <file|dir>… [--out data/interim/cv_text] [--report reports/…] [--print]
  make_cv_samples.py          sinh mẫu từ personas.yaml
tests/
  unit/test_cv_sniff.py
  unit/test_cv_normalize.py
  unit/test_cv_quality.py
  unit/test_cv_pdf.py
  unit/test_cv_docx.py
  unit/test_cv_samples.py     golden 10 CV: đạt mục 6.1
  unit/test_cv_fixtures_privacy.py
  scripts/test_extract_cv.py
  fixtures/cv/…               như mục 7.3
reports/s3_d01_trich_van_ban_cv.md
```

Vì sao có thư mục con `extract/`: S3-D02 (`cvparser/sections.py`), S3-D03 (`cvparser/redact.py`), S3-D04 (`cvparser/profile.py`) sẽ nằm cạnh. Phần trích văn bản không phụ thuộc chúng, nên sau này chuyển nguyên `extract/` sang `packages/` theo đề xuất monorepo (`docs/architecture/monorepo.md`) hoặc dùng cho JD tải lên là được.

Thư viện (`uv add`, khóa version trong `uv.lock`):

| Gói | Nhóm | License | Ghi chú |
|---|---|---|---|
| `pypdfium2` | chính | Apache-2.0 / BSD-3 | Wheel có sẵn PDFium, không cần cài gì vào image |
| `pdfplumber` | chính | MIT | Kéo theo `pdfminer.six` (MIT), Pillow (đã có), pypdfium2 |
| `python-docx` | chính | MIT | `lxml` đã có |
| `reportlab` | dev | BSD | Chỉ để sinh mẫu |

Không dùng PyMuPDF (AGPL), `textract` (kéo nhiều phần mềm hệ thống), `python-magic` (cần libmagic trên máy).

## 9. Kế hoạch test

| File | Nội dung chính |
|---|---|
| `test_cv_sniff.py` | `%PDF-` sau byte rác vẫn nhận PDF; DOCX thật; ZIP thường, XLSX, DOCM → `unsupported_type`; OLE → `legacy_doc`; PNG/JPG → `image`; rỗng; đuôi `.pdf` nhưng nội dung DOCX → đọc DOCX + `extension_mismatch`; zip nén quá mức → `too_large` |
| `test_cv_normalize.py` | NFD → NFC; dấu cách trước dấu kết hợp; zero-width, soft hyphen, ligature `ﬁ`; CRLF; dòng trống giữa khối được giữ; gộp "K I N H  N G H I Ệ M", không gộp "C C++ Go"; icon PUA đầu dòng |
| `test_cv_quality.py` | Văn bản Việt chuẩn đạt; `(cid:12)` dày đặc, U+FFFD, chuỗi TCVN3 "Kinh nghiÖm" → không đạt/có cảnh báo; văn bản bị bỏ dấu → `vi_diacritic_ratio` thấp; rỗng |
| `test_cv_pdf.py` | Số trang, bảng ở cv04 có đúng số hàng; thứ tự 2 cột ở cv03; encrypted, cắt cụt, scan → đúng mã; PDF 30 trang (ghép trang bằng pypdfium2 trong test) → `truncated_pages`; metadata không có Author |
| `test_cv_docx.py` | Tạo DOCX nhỏ ngay trong test bằng python-docx: thứ tự đoạn/bảng; ô gộp không lặp; header/footer; style heading → `kind="heading"`; numbering → `- `; chèn XML `w:ins`/`w:del` và `mc:AlternateContent` để kiểm track changes và text box không lặp |
| `test_cv_samples.py` | Tham số hóa 10 CV: đạt đủ mục 6.1 (readable, phủ mốc ≥ 95%, thứ tự ≥ 0,9, không chuỗi cấm, CER ≤ 2% với CV sinh) |
| `test_cv_fixtures_privacy.py` | Email/SĐT chỉ thuộc danh sách giả; metadata tác giả rỗng |
| `tests/scripts/test_extract_cv.py` | Thư mục có 1 file tốt + 1 file hỏng: cả hai được xử lý, file hỏng không làm dừng; báo cáo không chứa câu nào của CV; exit code ≠ 0 khi có file lỗi |

Cuối cùng chạy `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`.

## 10. Các bước và ước lượng (4h)

| # | Bước | Giờ | Đầu ra |
|---|---|---|---|
| 1 | `uv add` thư viện; khung `models`, `errors`, `sniff`, `registry`; test sniff | 0:35 | `extract_document()` chạy được với lỗi loại file |
| 2 | `PdfExtractor`: văn bản từng trang (pypdfium2), bảng (pdfplumber), encrypted/hỏng/scan, giới hạn trang, metadata | 0:55 | test PDF xanh trên mẫu sinh |
| 3 | `DocxExtractor`: duyệt body theo thứ tự, bảng data/layout, ô gộp, text box, header/footer, track changes | 0:45 | test DOCX xanh |
| 4 | `normalize` + `quality` | 0:25 | test normalize/quality xanh |
| 5 | Bộ mẫu: `personas.yaml` + `make_cv_samples.py` sinh 7 file; tự làm cv06, cv07, cv10; xóa metadata; `expected/*.yaml`; test riêng tư | 0:40 | 10 file + 2 file lỗi |
| 6 | `scripts/extract_cv.py`, chạy 10 CV, kiểm tay theo 6.2, viết báo cáo | 0:25 | `reports/s3_d01_trich_van_ban_cv.md` |
| 7 | ruff, pytest, sửa lỗi, mở PR `Closes #463` | 0:15 | PR |
| | **Tổng** | **4:00** | |

4h là sát, không có dự phòng. Trễ thì cắt theo thứ tự này (ghi vào PR là để sau):

1. Gợi ý heading PDF (cỡ chữ/đậm) → S3-D02.
2. Dựng lại thứ tự cột: chỉ làm nếu cv03/cv07 trượt.
3. Gộp chữ giãn cách → để cảnh báo, S3-D02 xử lý ở tầng heading.
4. CER cho CV sinh → chỉ giữ độ phủ mốc.
5. Bảng layout/data trong DOCX → xuất mọi bảng theo hàng.

Không cắt: sniff magic bytes, mã lỗi, không ném lỗi, 10 mẫu + test riêng tư, chỉ số readable.

## 11. Câu hỏi cần Duy quyết

1. **Nguồn 10 CV mẫu.** (A) Script sinh cả 10: nhanh, tái lập, nhưng "sạch" hơn CV thật. (B) **[đề xuất]** 7 sinh bằng script + 3 tự làm bằng Word/Google Docs/Canva với nội dung giả (cv06, cv07, cv10), thêm khoảng 15 phút nhưng gặp đúng kiểu PDF ngoài đời. (C) CV thật sửa tay cho ẩn danh: không lên git được, và S3-D06 đã dành cho CV thật.
2. **Commit file nhị phân mẫu** vào `tests/fixtures/cv/` (mở ngoại lệ `.gitignore`)? Đề xuất có. Nếu không: chỉ commit script sinh, CI phải cài reportlab và font tiếng Việt.
3. **OCR cho PDF scan/ảnh**: đề xuất ngoài phạm vi S3-D01, chỉ trả `ocr_required` với thông điệp hướng dẫn. Có đưa vào backlog không? Cần Tesseract + gói `vie` trong image (thêm ~100 MB, chậm 1–3 giây/trang), hoặc LLM vision (tốn tiền, phải ẩn PII trên ảnh, khó).
4. **`.doc`**: đề xuất từ chối kèm hướng dẫn lưu lại thành `.docx`, khớp mime của `app.cvs`. Hay muốn chuyển đổi bằng LibreOffice trong worker sau này?
5. **Giới hạn**: 5 MB đã chốt ở DB. Đề xuất thêm tối đa 10 trang (đọc 10 trang đầu, cảnh báo) và timeout 10 giây/file. Có đồng ý không?
6. **Vị trí code**: đề xuất `src/cvparser/extract/` với API không dính tới CV, để dùng lại cho JD tải lên (US-20, US-23) và sau này chuyển sang `packages/`. Hay muốn tách gói riêng ngay (ví dụ `src/doctext/`)?
7. **Văn bản thô**: xác nhận không lưu văn bản chưa che PII ở đâu ngoài bộ nhớ (DB chỉ `text_redacted`, CLI chỉ ghi vào `data/`). Phần trích trong `ExtractionResult` có cần được đưa vào `pgmq` không? Đề xuất **không**: message chỉ chứa `cv_id`, worker tự đọc file.
