"""PDF: văn bản bằng pypdfium2, bảng bằng pdfplumber.

- Văn bản theo thứ tự content stream của PDFium: PDF xuất từ Word/Canva để mỗi cột là một
  khung chữ nên CV 2 cột không bị trộn dòng. pdfplumber.extract_text() sắp theo tọa độ y nên
  trộn 2 cột, vì vậy chỉ dùng pdfplumber cho bảng.
- PDFium không an toàn khi gọi từ nhiều luồng: mọi lời gọi đi qua _LOCK. Chạy song song thì
  dùng nhiều tiến trình (cvparser.extract.batch), không dùng thread.
- Không lấy metadata Author/Subject/Keywords (thường là tên thật).
"""

import io
import re
import threading

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from cvparser.extract.errors import ErrorCode, ExtractionError
from cvparser.extract.models import ExtractOptions, RawBlock, RawDocument, Table, Warning_

_LOCK = threading.Lock()
MIN_CHARS_PER_PAGE = 20  # ít hơn → trang không có lớp chữ (scan)
_PASSWORD_ERROR = 4  # FPDF_ERR_PASSWORD


class PdfExtractor:
    kind = "pdf"
    version = "pdf-3"  # pdf-2: dựng lại khoảng trắng chữ giãn cách; pdf-3: footer kèm số trang

    def extract(self, data: bytes, options: ExtractOptions) -> RawDocument:
        with _LOCK:
            pages, page_count, scan_pages, metadata = self._text(data, options)
        warnings = []
        if page_count > options.max_pages:
            warnings.append(Warning_(code="truncated_pages"))
        n = len(pages)
        if n and len(scan_pages) * 2 >= n and sum(len(t.strip()) for _, t in pages) < 20 * n:
            raise ExtractionError(ErrorCode.OCR_REQUIRED, f"{len(scan_pages)}/{n} trang là ảnh")
        warnings += [Warning_(code="pages_without_text", page=p) for p in scan_pages]

        blocks = _blocks(pages)
        tables: list[Table] = []
        if options.extract_tables:
            try:
                tables = _tables(data, min(page_count, options.max_pages))
            except Exception:  # bảng chỉ là phần thêm: lỗi ở đây không làm hỏng văn bản
                warnings.append(Warning_(code="tables_failed"))
        return RawDocument(
            blocks=blocks, tables=tables, page_count=page_count, metadata=metadata,
            warnings=warnings,
        )  # fmt: skip

    @staticmethod
    def _text(data: bytes, options: ExtractOptions):
        try:
            pdf = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as e:
            if getattr(e, "err_code", None) == _PASSWORD_ERROR:
                raise ExtractionError(ErrorCode.ENCRYPTED, "pdf") from None
            raise ExtractionError(ErrorCode.CORRUPT_FILE, "pdf_open") from None
        try:
            page_count = len(pdf)
            if page_count == 0:
                raise ExtractionError(ErrorCode.CORRUPT_FILE, "no_pages")
            meta = pdf.get_metadata_dict(skip_empty=True)
            metadata = {k.lower(): v for k, v in meta.items() if k in ("Producer", "Creator")}
            metadata["pdf_version"] = str(pdf.get_version() or "")
            pages, scan_pages = [], []
            for i in range(min(page_count, options.max_pages)):
                page = pdf[i]
                try:
                    textpage = page.get_textpage()
                    try:
                        text = _page_text(textpage)
                    finally:
                        textpage.close()
                    if len(text.strip()) < MIN_CHARS_PER_PAGE and _has_image(page):
                        scan_pages.append(i + 1)
                finally:
                    page.close()
                pages.append((i + 1, text))
            return pages, page_count, scan_pages, metadata
        except pdfium.PdfiumError:
            raise ExtractionError(ErrorCode.CORRUPT_FILE, "pdf_read") from None
        finally:
            pdf.close()


# Chữ giãn cách (letter-spacing, hay gặp ở tiêu đề mẫu Canva): PDFium chèn khoảng trắng "tự sinh"
# giữa mọi chữ, nên "LIÊN HỆ" ra "L I Ê N H Ệ" và không còn biết đâu là ranh giới từ. Dòng như vậy
# được dựng lại theo tọa độ: khe giữa hai chữ trong một từ ≈ độ giãn (gần như đều nhau), khe giữa
# hai từ = độ giãn + bề rộng dấu cách. Dòng thường giữ nguyên văn bản PDFium trả về.
_SPACED_RATIO = 0.6  # ≥ 60% khe giữa hai chữ liền nhau có khoảng trắng tự sinh → dòng giãn cách
_WORD_GAP_EM = 0.15  # khe lớn hơn khe phổ biến của dòng ít nhất 0,15 cỡ chữ → ranh giới từ


def _page_text(textpage) -> str:
    n = textpage.count_chars()
    if n <= 0:
        return ""
    text = textpage.get_text_range(0, n)
    if len(text) != n:  # không khớp 1-1 ký tự ↔ chỉ số: không dựng lại được, giữ nguyên
        return text
    out, line = [], []
    for i, ch in enumerate(text):
        if ch in "\r\n":
            out.append(_line_text(textpage, line))
            line = []
            out.append(ch)
        else:
            line.append(i)
    out.append(_line_text(textpage, line))
    return "".join(out)


def _line_text(textpage, idx: list[int]) -> str:
    raw = textpage.raw
    chars = [(i, textpage.get_text_range(i, 1), pdfium_c.FPDFText_IsGenerated(raw, i)) for i in idx]
    plain = "".join(ch for _, ch, _ in chars)
    glyphs = [(i, ch) for i, ch, gen in chars if not ch.isspace()]
    if len(glyphs) < 4:
        return plain
    # Khe giữa hai glyph liền nhau: có khoảng trắng thật (trong PDF) / tự sinh / không có gì.
    seps: list[str | None] = []
    pending, seen = None, False
    for _, ch, gen in chars:
        if ch.isspace():
            pending = "gen" if gen and pending is None else "real" if not gen else pending
        else:
            if seen:
                seps.append(pending)
            seen, pending = True, None
    if sum(s == "gen" for s in seps) < _SPACED_RATIO * len(seps):
        return plain
    boxes = [textpage.get_charbox(i, loose=True) for i, _ in glyphs]
    gaps = [boxes[k + 1][0] - boxes[k][2] for k in range(len(boxes) - 1)]
    typical = sorted(gaps)[len(gaps) // 2]
    parts = [glyphs[0][1]]
    for k, (gap, sep) in enumerate(zip(gaps, seps, strict=True)):
        size = pdfium_c.FPDFText_GetFontSize(raw, glyphs[k][0]) or 10.0
        if sep == "real" or gap > typical + _WORD_GAP_EM * size:
            parts.append(" ")
        parts.append(glyphs[k + 1][1])
    return "".join(parts)


_EDGE_LINES = 3  # header/footer nằm trong vài dòng đầu/cuối của trang
_PAGE_NO = re.compile(r"^(?:(?:page|trang)\s*)?#(?:\s*(?:/|of|trên)\s*#)?$", re.I)
# Số trang ở CUỐI một dòng footer/header: "CV – Lan (Bilingual) Page 2 of 3", "… Trang 1/2".
_PAGE_TAIL = re.compile(r"\s*[-–—|·]?\s*(?:page|trang)\s*\d+(?:\s*(?:/|of|trên)\s*\d+)?\s*$", re.I)


def _blocks(pages: list[tuple[int, str]]) -> list[RawBlock]:
    """Dòng thành khối. PDF ≥ 2 trang: dòng lặp ở mép trang (header/footer) gom một lần thành
    khối header ở đầu văn bản, số trang bị bỏ, để không chen vào giữa nội dung vắt trang."""
    per_page = [
        (page, [x for x in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")])
        for page, text in pages
    ]

    def key(line: str) -> str:
        return " ".join(_PAGE_TAIL.sub("", line).split()).lower()

    def page_no(line: str) -> bool:
        return bool(_PAGE_NO.match(re.sub(r"\d+", "#", " ".join(line.split()).lower())))

    multi = len(per_page) >= 2
    edges: list[set[str]] = []
    for _, lines in per_page:
        edge = [x for x in lines if x.strip()]
        edges.append({key(x) for x in edge[:_EDGE_LINES] + edge[-_EDGE_LINES:]})
    # Header/footer: cùng nguyên văn, ở mép trang, trên ≥ 2 trang và ≥ một nửa số trang.
    count: dict[str, int] = {}
    for edge in edges:
        for k in edge:
            count[k] = count.get(k, 0) + 1
    need = max(2, (len(per_page) + 1) // 2)
    repeated = {k for k, n in count.items() if k and n >= need} if multi else set()

    header: list[RawBlock] = []
    body: list[RawBlock] = []
    emitted: set[str] = set()
    for (page, lines), edge in zip(per_page, edges, strict=True):
        for line in lines:
            k = key(line)
            if multi and page_no(line) and (k in edge or not k):
                continue  # "Page 2", "Trang 1/3", "2"
            if k in repeated:
                if k not in emitted:
                    emitted.add(k)
                    text = _PAGE_TAIL.sub("", line).rstrip()  # bỏ "Page 1 of 3" của lần đầu
                    header.append(RawBlock(text=text, page=page, source="header"))
                continue
            body.append(RawBlock(text=line, page=page))
    return header + body


def _has_image(page) -> bool:
    return any(True for _ in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=2))


def _tables(data: bytes, max_pages: int) -> list[Table]:
    import pdfplumber  # import muộn: chậm, chỉ cần khi có bảng

    out = []
    with pdfplumber.open(io.BytesIO(data), pages=list(range(1, max_pages + 1))) as pdf:
        for page in pdf.pages:
            for t in page.find_tables():
                rows = [[(c or "").strip() for c in row] for row in t.extract()]
                rows = [r for r in rows if any(r)]
                if len(rows) >= 2:
                    out.append(Table(page=page.page_number, bbox=tuple(t.bbox), rows=rows))
            page.close()
    return out
