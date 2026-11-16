"""S3-D01: extract_document() cho PDF và DOCX, kể cả file hỏng (không bao giờ ném lỗi)."""

import io
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from docx import Document
from docx.oxml import parse_xml

from cvparser.extract import extract_document
from cvparser.extract.models import ExtractOptions

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "cv"
SAMPLES = FIX / "samples"


def _read(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


# ----------------------------------------------------------------------------- PDF


def test_pdf_basic_and_metadata_has_no_author():
    r = extract_document(_read("cv01.pdf"), filename="cv01.pdf")
    assert r.status == "ok" and r.file.kind == "pdf" and r.file.page_count == 1
    assert "KINH NGHIỆM LÀM VIỆC" in r.text and "Spring Boot" in r.text
    assert "author" not in r.metadata
    assert r.parser_version == "cvparser-1/pdf-2"
    assert len(r.file.sha256) == 64


def test_pdf_two_columns_not_interleaved():
    text = extract_document(_read("cv03.pdf")).text
    lines = text.split("\n")
    skills = ["ReactJS", "TypeScript", "Next.js", "Tailwind CSS", "Redux", "Jest"]
    start = lines.index("ReactJS")
    assert lines[start : start + len(skills)] == skills  # cột trái liền mạch
    assert text.index("NGOẠI NGỮ") < text.index("KINH NGHIỆM")


def test_pdf_tables_kept_as_rows():
    r = extract_document(_read("cv04.pdf"))
    assert len(r.tables) == 2
    skills = next(t for t in r.tables if t.rows[0] == ["Kỹ năng", "Mức độ"])
    assert ["Postman", "Tốt"] in skills.rows and skills.page == 1
    no_tables = extract_document(_read("cv04.pdf"), options=ExtractOptions(extract_tables=False))
    assert no_tables.tables == [] and no_tables.text == r.text


def test_pdf_repeated_header_once_and_page_numbers_dropped():
    r = extract_document(_read("cv05.pdf"))
    assert r.file.page_count == 2
    assert r.blocks[0].source == "header"
    assert r.text.count("Hoang Quoc Viet – DevOps Engineer – viet.hoang@example.com") == 1
    assert "Page 1" not in r.text and "Page 2" not in r.text
    terraform = [x for x in r.text.split("\n") if "Terraform module" in x]
    assert len(terraform) == 25  # các dòng giống nhau trừ con số không bị coi là header


def test_pdf_truncated_pages_is_partial():
    r = extract_document(_read("cv05.pdf"), options=ExtractOptions(max_pages=1))
    assert r.status == "partial" and "truncated_pages" in [w.code for w in r.warnings]
    assert r.file.page_count == 2


@pytest.mark.parametrize(
    ("name", "code"),
    [("encrypted_userpw.pdf", "encrypted"), ("scan_image_only.pdf", "ocr_required")],
)
def test_pdf_edge_files(name, code):
    r = extract_document((FIX / "edge" / name).read_bytes())
    assert r.status == "failed" and r.error.code == code and r.error.message_vi
    assert r.text == ""


def test_pdf_truncated_file_is_corrupt_not_exception():
    data = _read("cv01.pdf")
    r = extract_document(data[: len(data) // 3])
    assert r.status == "failed" and r.error.code in ("corrupt_file", "ocr_required")


def test_pdf_blank_page_without_image_is_ocr_required():
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(595, 842)
    buf = io.BytesIO()
    pdf.save(buf)
    r = extract_document(buf.getvalue())
    assert r.error.code == "ocr_required"


def _letter_spaced_pdf() -> bytes:
    """Đặt từng chữ một tại tọa độ riêng, như Chrome/Canva in chữ có letter-spacing."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 14)
    for y, text, spacing in [
        (780, "WORK EXPERIENCE", 4),  # tiêu đề giãn chữ kiểu Canva
        (750, "UI/UX Designer at Acme", 3),
    ]:
        x = 60.0
        for ch in text:
            if ch != " ":
                c.drawString(x, y, ch)
            x += stringWidth(ch, "Helvetica", 14) + spacing
    c.drawString(60, 720, "Built design systems in Figma and Sketch for 3 products")
    c.save()
    return buf.getvalue()


def test_pdf_letter_spaced_lines_keep_word_boundaries():
    lines = extract_document(_letter_spaced_pdf()).text.split("\n")
    assert lines == [
        "WORK EXPERIENCE",
        "UI/UX Designer at Acme",
        "Built design systems in Figma and Sketch for 3 products",
    ]


def test_pdf_letter_spaced_canva_sample():
    lines = extract_document(_read("cv07.pdf")).text.split("\n")
    for want in ("LIÊN HỆ", "KỸ NĂNG", "Thiết kế UI/UX", "GIỚI THIỆU", "0912 000 107"):
        assert want in lines


def test_extension_mismatch_warning():
    r = extract_document(_read("cv08.docx"), filename="cv.pdf")
    assert r.file.kind == "docx" and "extension_mismatch" in [w.code for w in r.warnings]


# ----------------------------------------------------------------------------- DOCX


def _docx(doc: Document) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_headings_lists_and_offsets():
    r = extract_document(_read("cv08.docx"))
    assert r.status == "ok"
    headings = [b.text for b in r.blocks if b.kind == "heading"]
    assert headings[:3] == ["Đỗ Thanh Tùng", "Mục tiêu nghề nghiệp", "Kinh nghiệm làm việc"]
    item = next(b for b in r.blocks if b.kind == "list_item")
    assert item.text.startswith("- ")
    for b in r.blocks:  # offset khớp văn bản: S3-D04 cắt đoạn trích bằng offset
        assert r.text[b.start : b.end] == b.text


def test_docx_layout_table_reads_left_column_first_and_header():
    r = extract_document(_read("cv09.docx"))
    assert r.blocks[0].source == "header" and r.blocks[0].text == "Vũ Hải Yến"
    assert r.text.index("Scrum Master PSM I") < r.text.index("TÓM TẮT")
    assert r.tables == []  # bảng bố cục không phải bảng dữ liệu


def test_docx_data_table_rows_and_merged_cells():
    doc = Document()
    t = doc.add_table(rows=3, cols=3)
    for i, row in enumerate([["Thời gian", "Công ty", "Vị trí"], ["2022", "Sao Mai", "Dev"]]):
        for j, v in enumerate(row):
            t.cell(i, j).text = v
    merged = t.cell(2, 0).merge(t.cell(2, 2))
    merged.text = "Ghi chú gộp"
    doc.add_paragraph("Đoạn sau bảng")
    r = extract_document(_docx(doc))
    assert r.tables[0].rows[:2] == [["Thời gian", "Công ty", "Vị trí"], ["2022", "Sao Mai", "Dev"]]
    assert r.text.count("Ghi chú gộp") == 1  # ô gộp không bị lặp
    assert r.text.index("2022 | Sao Mai | Dev") < r.text.index("Đoạn sau bảng")


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
MC = 'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
WPS = 'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"'


def test_docx_textbox_once_and_track_changes():
    doc = Document()
    p = doc.add_paragraph("Trước")
    box = (
        f'<w:r {W} {MC} {WPS}><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing>'
        "<wps:txbx><w:txbxContent><w:p><w:r><w:t>hung@example.com</w:t></w:r></w:p>"
        "</w:txbxContent></wps:txbx></w:drawing></mc:Choice><mc:Fallback><w:pict>"
        "<w:txbxContent><w:p><w:r><w:t>hung@example.com</w:t></w:r></w:p></w:txbxContent>"
        "</w:pict></mc:Fallback></mc:AlternateContent></w:r>"
    )
    p._p.append(parse_xml(box))
    tracked = doc.add_paragraph("Kỹ năng: ")
    tracked._p.append(parse_xml(f"<w:ins {W}><w:r><w:t>Java</w:t></w:r></w:ins>"))
    tracked._p.append(parse_xml(f"<w:del {W}><w:r><w:delText>PHP</w:delText></w:r></w:del>"))
    r = extract_document(_docx(doc))
    assert r.text.count("hung@example.com") == 1
    assert any(b.source == "textbox" for b in r.blocks)
    assert "Kỹ năng: Java" in r.text and "PHP" not in r.text


def test_docx_header_footer_dedup():
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = "Tên Giả"
    doc.sections[0].footer.paragraphs[0].text = "Trang CV"
    doc.add_paragraph("Nội dung " * 50)
    doc.add_section()
    r = extract_document(_docx(doc))
    assert r.text.startswith("Tên Giả") and r.text.endswith("Trang CV")
    assert r.text.count("Tên Giả") == 1


def test_docx_corrupt_content_is_failed():
    from tests.unit.test_cv_sniff_normalize import _CT, _zip

    data = _zip({"[Content_Types].xml": _CT.format("wordprocessingml.document.main+xml").encode()})
    r = extract_document(data)
    assert r.status == "failed" and r.error.code == "corrupt_file"


def test_never_raises_on_random_bytes():
    import random

    rnd = random.Random(1)
    for prefix in (b"%PDF-1.4\n", b"PK\x03\x04", b""):
        data = prefix + bytes(rnd.getrandbits(8) for _ in range(2000))
        assert extract_document(data).status == "failed"
