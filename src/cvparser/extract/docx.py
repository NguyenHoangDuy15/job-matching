"""DOCX: python-docx để mở file, tự duyệt XML để không sót nội dung.

`document.paragraphs` bỏ sót bảng, text box, content control và đảo thứ tự, nên duyệt body
theo đúng thứ tự XML:
  - w:p (đoạn), w:tbl (bảng), w:sdt (content control: duyệt vào sdtContent).
  - Text box (w:txbxContent) nằm trong mc:AlternateContent hai lần (Choice + Fallback VML):
    chỉ lấy nhánh Choice.
  - Ô gộp ngang (gridSpan) là một w:tc nên không lặp; ô gộp dọc tiếp nối (vMerge) bị bỏ.
  - Bảng ≤ 2 cột có ô nhiều đoạn = bảng dùng làm bố cục 2 cột (mẫu CV Word): đọc hết cột
    trái rồi sang cột phải. Bảng khác: mỗi hàng một dòng "ô1 | ô2 | ô3".
  - Header/footer: khối riêng, khử trùng giữa các section.
  - Track changes: lấy chữ trong w:ins, bỏ w:del; bỏ mã field (w:instrText).
Không lấy docProps/core.xml (creator, lastModifiedBy là tên người).
"""

import io

from docx import Document
from docx.oxml.ns import qn

from cvparser.extract.errors import ErrorCode, ExtractionError
from cvparser.extract.models import ExtractOptions, RawBlock, RawDocument, Table

_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
_SKIP = {qn("w:del"), qn("w:delText"), qn("w:instrText"), _MC + "Fallback", qn("w:txbxContent")}
_SKIP |= {qn("w:rPr"), qn("w:pPr")}  # chứa thuộc tính, không chứa chữ


class DocxExtractor:
    kind = "docx"
    version = "docx-1"

    def extract(self, data: bytes, options: ExtractOptions) -> RawDocument:
        try:
            doc = Document(io.BytesIO(data))
        except Exception:
            raise ExtractionError(ErrorCode.CORRUPT_FILE, "docx_open") from None
        styles = _style_names(doc)
        walker = _Walker(styles)
        header, footer, seen = [], [], set()
        for section in doc.sections:
            for part, target, source in (
                (section.header, header, "header"),
                (section.footer, footer, "footer"),
            ):
                try:
                    if part.is_linked_to_previous and seen:
                        continue
                    blocks = _Walker(styles, source=source).container(part._element)
                except Exception:
                    continue
                for b in blocks:
                    if b.text.strip() and (source, b.text) not in seen:
                        seen.add((source, b.text))
                        target.append(b)
        body = walker.container(doc.element.body)
        return RawDocument(blocks=header + body + footer, tables=walker.tables, page_count=None)


def _style_names(doc) -> dict[str, str]:
    out = {}
    for s in doc.styles:
        try:
            out[s.style_id] = s.name or s.style_id
        except Exception:
            continue
    return out


class _Walker:
    def __init__(self, styles: dict[str, str], source: str = "body") -> None:
        self.styles = styles
        self.source = source
        self.tables: list[Table] = []

    def container(self, el) -> list[RawBlock]:
        out: list[RawBlock] = []
        for child in el.iterchildren():
            if child.tag == qn("w:p"):
                out += self.paragraph(child)
            elif child.tag == qn("w:tbl"):
                out += self.table(child)
            elif child.tag == qn("w:sdt"):
                content = child.find(qn("w:sdtContent"))
                if content is not None:
                    out += self.container(content)
        return out

    def paragraph(self, p, source: str | None = None) -> list[RawBlock]:
        text = "".join(_text(p))
        style_id = p.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
        style = self.styles.get(style_id.get(qn("w:val")), None) if style_id is not None else None
        numbered = p.find(f"{qn('w:pPr')}/{qn('w:numPr')}") is not None
        low = (style or "").lower()
        kind = "paragraph"
        if low.startswith(("heading", "title")) or "tiêu đề" in low:
            kind = "heading"
        elif numbered or low.startswith("list"):
            kind = "list_item"
        out = [RawBlock(kind=kind, source=source or self.source, text=text, style=style)]
        out += self.textboxes(p)
        return out

    def textboxes(self, p) -> list[RawBlock]:
        out = []
        for box in _iter_textboxes(p):
            for child in box.iterchildren():
                if child.tag == qn("w:p"):
                    out += self.paragraph(child, source="textbox")
                elif child.tag == qn("w:tbl"):
                    out += self.table(child)
        return out

    def table(self, tbl) -> list[RawBlock]:
        grid: list[list[list]] = []  # hàng → ô → các w:p
        for tr in tbl.findall(qn("w:tr")):
            row = []
            for tc in tr.findall(qn("w:tc")):
                vmerge = tc.find(f"{qn('w:tcPr')}/{qn('w:vMerge')}")
                if vmerge is not None and vmerge.get(qn("w:val")) in (None, "continue"):
                    continue  # ô tiếp nối của ô gộp dọc: chữ nằm ở ô đầu
                row.append(tc)
            grid.append(row)
        ncols = max((len(r) for r in grid), default=0)
        cell_paras = [[self.container(tc) for tc in row] for row in grid]
        multi = any(len([b for b in c if b.text.strip()]) >= 3 for r in cell_paras for c in r)
        if ncols <= 2 and multi:  # bảng bố cục: chữ đã nằm trong văn bản, không phải bảng dữ liệu
            out = []
            for col in range(ncols):
                for row in cell_paras:
                    if col < len(row):
                        out += row[col]
            return out
        rows = _rows_text(cell_paras)
        self.tables.append(Table(kind="data", rows=rows))
        return [
            RawBlock(kind="table_row", source="table", text=" | ".join(c for c in r if c))
            for r in rows
            if any(r)
        ]


def _rows_text(cell_paras) -> list[list[str]]:
    return [
        [" ".join(b.text.strip() for b in cell if b.text.strip()) for cell in row]
        for row in cell_paras
    ]


def _text(el):
    """Chữ trong một đoạn theo thứ tự, bỏ phần đã xóa, mã field, nhánh Fallback, text box."""
    for child in el.iterchildren():
        tag = child.tag
        if tag in _SKIP:
            continue
        if tag == qn("w:t"):
            yield child.text or ""
        elif tag == qn("w:tab"):
            yield " "
        elif tag in (qn("w:br"), qn("w:cr")):
            yield "\n"
        else:
            yield from _text(child)


def _iter_textboxes(el):
    """w:txbxContent trong đoạn, bỏ nhánh mc:Fallback để không lặp."""
    for child in el.iterchildren():
        if child.tag == _MC + "Fallback":
            continue
        if child.tag == qn("w:txbxContent"):
            yield child
        else:
            yield from _iter_textboxes(child)
