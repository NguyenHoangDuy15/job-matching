"""Sinh bộ CV mẫu GIẢ cho S3-D01 (tests/fixtures/cv/). Không dùng CV thật.

    uv run python scripts/make_cv_samples.py          # sinh 7 file + expected/*.yaml + edge/
    uv run python scripts/make_cv_samples.py --font /đường/dẫn/font.ttf

Sinh bằng script: cv01–cv05 (PDF, reportlab), cv08–cv09 (DOCX, python-docx).
Làm tay (nội dung trong tests/fixtures/cv/manual/*.md): cv06 Word→PDF, cv07 Canva 2 cột,
cv10 DOCX có text box. Script vẫn sinh expected/cv06,07,10.yaml từ nội dung đó.

PII đều giả: email @example.com/.vn, SĐT trong tests/fixtures/cv/fake_pii.yaml.
Metadata tác giả để trống. reportlab chỉ cần ở nhóm dev; CI dùng file đã commit.
"""

import argparse
import io
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "cv"
FONTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

# --------------------------------------------------------------------------- nội dung giả
PERSONAS: dict[str, dict] = {
    "cv01": {
        "lang": "vi",
        "name": "Nguyễn Văn Hùng",
        "contact": [
            "Email: hung.nguyen@example.com",
            "Điện thoại: 0912 000 101",
            "Địa chỉ: Số 12 ngõ 34 phố Hoa Sữa, phường Thành Công, Hà Nội",
        ],
        "title": "Lập trình viên Backend",
        "sections": [
            (
                "MỤC TIÊU NGHỀ NGHIỆP",
                [
                    "Trở thành kỹ sư backend vững về hệ thống phân tán "
                    "và tối ưu hiệu năng trong 2 năm tới."
                ],
            ),
            (
                "KINH NGHIỆM LÀM VIỆC",
                [
                    "Công ty Cổ phần Công nghệ Sao Mai | 03/2023 – nay",
                    "Lập trình viên Backend",
                    "- Xây dựng API thanh toán bằng Java Spring Boot, 2 triệu yêu cầu mỗi ngày",
                    "- Thiết kế cơ sở dữ liệu PostgreSQL, giảm 40% thời gian truy vấn báo cáo",
                    "- Triển khai Docker và Kubernetes cho 12 dịch vụ",
                    "Công ty TNHH Phần mềm Biển Xanh | 07/2021 – 02/2023",
                    "Thực tập sinh rồi Lập trình viên Java",
                    "- Viết dịch vụ đồng bộ đơn hàng bằng Kafka và Redis",
                ],
            ),
            ("HỌC VẤN", ["Đại học Bách khoa Hà Nội | Kỹ thuật phần mềm | 2017 – 2021"]),
            (
                "KỸ NĂNG",
                [
                    "Java, Spring Boot, PostgreSQL, Redis, Kafka, Docker, Kubernetes, Git",
                    "Tiếng Anh: đọc hiểu tài liệu kỹ thuật (TOEIC 750)",
                ],
            ),
        ],
    },
    "cv02": {
        "lang": "en",
        "name": "Tran Thi Mai",
        "contact": [
            "Email: mai.tran@example.com",
            "Phone: +84 912 000 102",
            "Address: 56 Fictional Street, Ward 7, Ho Chi Minh City",
        ],
        "title": "Data Analyst",
        "sections": [
            (
                "SUMMARY",
                [
                    "Data analyst with three years of experience turning sales data into "
                    "dashboards and forecasting models for retail teams."
                ],
            ),
            (
                "WORK EXPERIENCE",
                [
                    "Lotus Retail Analytics | Data Analyst | 01/2022 – Present",
                    "- Built Power BI dashboards used by 40 store managers every week",
                    "- Automated reporting pipelines with Python, pandas and SQL",
                    "- Designed A/B tests for promotion campaigns",
                    "Green River Consulting | Junior Analyst | 06/2020 – 12/2021",
                    "- Cleaned survey data and produced Excel reports for clients",
                ],
            ),
            ("EDUCATION", ["University of Economics HCMC | Bachelor of Statistics | 2016 – 2020"]),
            (
                "SKILLS",
                [
                    "Python, SQL, Power BI, Excel, pandas, scikit-learn, Tableau",
                    "Statistics, A/B testing, data visualization",
                ],
            ),
        ],
    },
    "cv03": {
        "lang": "vi",
        "name": "Lê Minh Khoa",
        "title": "Lập trình viên Frontend",
        "left": [
            ("LIÊN HỆ", ["khoa.le@example.vn", "0912 000 103", "Đà Nẵng"]),
            ("KỸ NĂNG", ["ReactJS", "TypeScript", "Next.js", "Tailwind CSS", "Redux", "Jest"]),
            ("NGOẠI NGỮ", ["Tiếng Anh giao tiếp", "Tiếng Nhật N3"]),
        ],
        "sections": [
            ("MỤC TIÊU", ["Phát triển giao diện web nhanh, dễ dùng và dễ bảo trì."]),
            (
                "KINH NGHIỆM",
                [
                    "Công ty TNHH Giải pháp Số Cầu Rồng | 05/2022 – nay",
                    "Lập trình viên Frontend",
                    "- Xây dựng trang quản trị bán hàng bằng ReactJS và TypeScript",
                    "- Tối ưu tốc độ tải trang từ 4 giây xuống 1,5 giây",
                    "Công ty Cổ phần Truyền thông Sông Hàn | 08/2020 – 04/2022",
                    "Lập trình viên Web",
                    "- Làm website giới thiệu sản phẩm bằng Next.js",
                ],
            ),
            ("HỌC VẤN", ["Đại học Đà Nẵng | Công nghệ thông tin | 2016 – 2020"]),
        ],
    },
    "cv04": {
        "lang": "vi",
        "name": "Phạm Thu Trang",
        "contact": ["Email: trang.pham@example.com", "Điện thoại: 0912 000 104"],
        "title": "Kiểm thử phần mềm",
        "sections": [
            ("MỤC TIÊU NGHỀ NGHIỆP", ["Phát triển thành kỹ sư kiểm thử tự động."]),
            ("KINH NGHIỆM LÀM VIỆC", []),
            ("KỸ NĂNG", []),
            ("CHỨNG CHỈ", ["ISTQB Foundation Level (2022)"]),
        ],
        "tables": {
            "KINH NGHIỆM LÀM VIỆC": [
                ["Thời gian", "Công ty", "Vị trí", "Công việc chính"],
                [
                    "02/2022 – nay",
                    "Công ty Cổ phần Phần mềm Ánh Dương",
                    "Tester",
                    "Kiểm thử API bằng Postman",
                ],
                ["06/2020 – 01/2022", "Công ty TNHH Dịch vụ Số Hoàng Gia", "QC", "Viết test case"],
            ],
            "KỸ NĂNG": [
                ["Kỹ năng", "Mức độ"],
                ["Selenium", "Khá"],
                ["Postman", "Tốt"],
                ["SQL", "Khá"],
                ["Jira", "Tốt"],
            ],
        },
    },
    "cv05": {
        "lang": "en",
        "name": "Hoang Quoc Viet",
        "contact": ["Email: viet.hoang@example.com", "Phone: 0912 000 105"],
        "title": "DevOps Engineer",
        "header": "Hoang Quoc Viet – DevOps Engineer – viet.hoang@example.com",
        "sections": [
            (
                "PROFILE",
                [
                    "DevOps engineer focused on reliable delivery pipelines and "
                    "observability for cloud-native systems."
                ],
            ),
            (
                "EXPERIENCE",
                [
                    "Blue Lotus Cloud | Senior DevOps Engineer | 03/2021 – Present",
                    *[
                        f"- Migrated service {i} to Kubernetes with Helm and Argo CD"
                        for i in range(1, 31)
                    ],
                    "Silver Peak Software | DevOps Engineer | 01/2019 – 02/2021",
                    *[
                        f"- Maintained Terraform module {i} for AWS networking"
                        for i in range(1, 26)
                    ],
                ],
            ),
            (
                "CERTIFICATIONS",
                [
                    "AWS Certified Solutions Architect – Associate",
                    "Certified Kubernetes Administrator (CKA)",
                ],
            ),
            (
                "SKILLS",
                [
                    "AWS, Terraform, Kubernetes, Helm, Argo CD, Prometheus, Grafana, "
                    "GitLab CI, Linux, Bash"
                ],
            ),
        ],
    },
    "cv08": {
        "lang": "vi",
        "name": "Đỗ Thanh Tùng",
        "contact": ["Email: tung.do@example.vn", "Điện thoại: 0912 000 108"],
        "title": "Lập trình viên Mobile",
        "sections": [
            (
                "Mục tiêu nghề nghiệp",
                ["Xây dựng ứng dụng di động mượt, ổn định cho hàng triệu người dùng."],
            ),
            (
                "Kinh nghiệm làm việc",
                [
                    "Công ty Cổ phần Ứng dụng Mây Hồng | 04/2022 – nay",
                    "Lập trình viên Flutter",
                    "# Phát triển ứng dụng đặt lịch khám bằng Flutter và Firebase",
                    "# Viết unit test, đạt độ phủ 80%",
                    "Công ty TNHH Di động Hải Âu | 09/2020 – 03/2022",
                    "Lập trình viên Android",
                    "# Bảo trì ứng dụng ví điện tử viết bằng Kotlin",
                ],
            ),
            ("Học vấn", ["Học viện Công nghệ Bưu chính Viễn thông | 2016 – 2020"]),
            (
                "Kỹ năng",
                [
                    "Flutter, Dart, Kotlin, Firebase, REST API, Git",
                    "English: good reading and writing",
                ],
            ),
        ],
    },
    "cv09": {
        "lang": "vi",
        "name": "Vũ Hải Yến",
        "contact": ["yen.vu@example.com · 0912 000 109 · Cần Thơ"],
        "title": "Chuyên viên Phân tích nghiệp vụ",
        "left": [
            ("KỸ NĂNG", ["Phân tích nghiệp vụ", "BPMN", "SQL", "Jira", "Confluence", "Figma"]),
            ("CHỨNG CHỈ", ["CBAP (2023)", "Scrum Master PSM I"]),
        ],
        "sections": [
            ("TÓM TẮT", ["Chuyên viên BA 4 năm trong lĩnh vực ngân hàng và bảo hiểm."]),
            (
                "KINH NGHIỆM",
                [
                    "Ngân hàng TMCP Phương Nam Giả Định | 06/2021 – nay",
                    "Chuyên viên BA",
                    "- Thu thập yêu cầu cho hệ thống cho vay trực tuyến",
                    "- Viết tài liệu đặc tả và vẽ quy trình BPMN",
                    "Công ty Bảo hiểm Hướng Dương | 07/2019 – 05/2021",
                    "Nhân viên BA",
                    "- Chuẩn hóa quy trình bồi thường",
                ],
            ),
            ("HỌC VẤN", ["Đại học Cần Thơ | Hệ thống thông tin | 2015 – 2019"]),
        ],
    },
}

MANUAL = {
    "cv06": ("pdf", "vi", "Xuất từ Word hoặc Google Docs sang PDF"),
    "cv07": ("pdf", "vi", "Mẫu Canva 2 cột có icon, tải về dạng PDF"),
    "cv10": ("docx", "vi", "Word, đặt khối liên hệ trong Text Box, có footer"),
}
MANUAL_PERSONAS = {
    "cv06": {
        "name": "Bùi Ngọc Lan",
        "contact": ["Email: lan.bui@example.com", "Điện thoại: 0912 000 106"],
        "title": "Kỹ sư Dữ liệu",
        "sections": [
            ("MỤC TIÊU NGHỀ NGHIỆP", ["Xây dựng nền tảng dữ liệu tin cậy cho doanh nghiệp."]),
            (
                "KINH NGHIỆM LÀM VIỆC",
                [
                    "Công ty Cổ phần Dữ liệu Bình Minh | 02/2022 – nay",
                    "Kỹ sư Dữ liệu",
                    "- Xây dựng pipeline ETL bằng Apache Airflow và dbt",
                    "- Quản lý kho dữ liệu trên Google BigQuery",
                ],
            ),
            ("HỌC VẤN", ["Đại học Quốc gia TP.HCM | Khoa học dữ liệu | 2017 – 2021"]),
            ("KỸ NĂNG", ["Python, SQL, Apache Airflow, dbt, BigQuery, Spark, Docker"]),
        ],
    },
    "cv07": {
        "name": "Trịnh Gia Bảo",
        "title": "Thiết kế UI/UX",
        "left": [
            ("LIÊN HỆ", ["bao.trinh@example.vn", "0912 000 107", "Huế"]),
            ("KỸ NĂNG", ["Figma", "Adobe XD", "Photoshop", "Illustrator", "Prototyping"]),
        ],
        "sections": [
            ("GIỚI THIỆU", ["Nhà thiết kế UI/UX yêu thích sản phẩm số đơn giản, dễ dùng."]),
            (
                "KINH NGHIỆM",
                [
                    "Công ty TNHH Sáng tạo Cố Đô | 01/2022 – nay",
                    "UI/UX Designer",
                    "- Thiết kế ứng dụng đặt tour du lịch trên Figma",
                    "- Thực hiện kiểm thử người dùng với 20 khách hàng",
                ],
            ),
            ("HỌC VẤN", ["Đại học Nghệ thuật Huế | Thiết kế đồ họa | 2017 – 2021"]),
        ],
    },
    "cv10": {
        "name": "Mai Anh Tuấn",
        "contact": ["tuan.mai@example.com", "0912 000 110", "Hải Phòng"],
        "title": "Kỹ sư An toàn thông tin",
        "sections": [
            ("TÓM TẮT", ["Kỹ sư bảo mật 3 năm kinh nghiệm kiểm thử xâm nhập ứng dụng web."]),
            (
                "KINH NGHIỆM",
                [
                    "Công ty Cổ phần An ninh Mạng Cửa Biển | 03/2022 – nay",
                    "Kỹ sư Pentest",
                    "- Kiểm thử xâm nhập 30 ứng dụng web theo OWASP Top 10",
                    "- Viết báo cáo lỗ hổng và hướng dẫn khắc phục",
                ],
            ),
            ("HỌC VẤN", ["Đại học Hàng hải Việt Nam | An toàn thông tin | 2017 – 2021"]),
            ("KỸ NĂNG", ["Burp Suite, Kali Linux, Nmap, Metasploit, Python, OWASP"]),
        ],
    },
}


# --------------------------------------------------------------------------- expected
def landmarks(p: dict) -> dict:
    """Cụm phải có nguyên vẹn + thứ tự heading + nhóm dòng phải liền nhau."""
    marks, order, contiguous = [p["name"], p["title"]], [], []
    for heading, lines in p.get("left", []):
        marks.append(heading)
        marks += lines
        contiguous.append(lines)  # cột trái 2 cột: không được xen dòng của cột phải
    left_order = [h for h, _ in p.get("left", [])]
    for heading, lines in p["sections"]:
        order.append(heading)
        marks.append(heading)
        for line in lines:
            text = line.lstrip("-# ").strip()
            for part in text.split(" | "):
                if len(part) >= 4:
                    marks.append(part)
        run: list[str] = []  # các gạch đầu dòng liên tiếp của cùng một việc
        for line in [*lines, ""]:
            if line.startswith(("-", "#")):
                run.append(line.lstrip("-# ").strip())
                continue
            if len(run) >= 2:
                contiguous.append(run)
            run = []
    for rows in p.get("tables", {}).values():
        for row in rows:
            marks += [c for c in row if len(c) >= 3]
    return {
        "lang": p.get("lang", "vi"),
        "landmarks": list(dict.fromkeys(marks)),
        "order": [left_order, order] if left_order else [order],
        "contiguous": contiguous,
        "min_tables": len(p.get("tables", {})),
    }


# --------------------------------------------------------------------------- PDF
def _pdf_styles(font: str):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "CV" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("CV", font))
    base = ParagraphStyle("b", fontName="CV", fontSize=10, leading=14)
    return {
        "name": ParagraphStyle("n", parent=base, fontSize=18, leading=22),
        "title": ParagraphStyle("t", parent=base, fontSize=12, leading=16),
        "h": ParagraphStyle("h", parent=base, fontSize=12, leading=18, spaceBefore=8),
        "p": base,
        "li": ParagraphStyle("li", parent=base, leftIndent=12),
    }


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _flow(p: dict, st: dict, with_head: bool = True) -> list:
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    out = []
    if with_head:
        out += [Paragraph(_esc(p["name"]), st["name"]), Paragraph(_esc(p["title"]), st["title"])]
        out += [Paragraph(_esc(c), st["p"]) for c in p.get("contact", [])]
        out.append(Spacer(1, 6))
    for heading, lines in p["sections"]:
        out.append(Paragraph(_esc(heading), st["h"]))
        if heading in p.get("tables", {}):
            data = [[Paragraph(_esc(c), st["p"]) for c in row] for row in p["tables"][heading]]
            t = Table(data, repeatRows=1)
            t.setStyle(
                TableStyle(
                    [("GRID", (0, 0), (-1, -1), 0.5, "black"), ("VALIGN", (0, 0), (-1, -1), "TOP")]
                )
            )
            out.append(t)
        for line in lines:
            if line.startswith("- "):
                out.append(Paragraph("• " + _esc(line[2:]), st["li"]))
            else:
                out.append(Paragraph(_esc(line), st["p"]))
    return out


def _doc_kwargs() -> dict:
    return {"author": "", "title": "", "subject": "", "creator": "", "keywords": ""}


def make_pdf_1col(p: dict, font: str, header: str | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate

    st = _pdf_styles(font)
    buf = io.BytesIO()

    def on_page(canvas, doc):
        if header:
            canvas.setFont("CV", 8)
            canvas.drawString(40, A4[1] - 30, header)
            canvas.drawRightString(A4[0] - 40, 25, f"Page {doc.page}")

    doc = SimpleDocTemplate(buf, pagesize=A4, invariant=1, topMargin=50, **_doc_kwargs())
    doc.build(_flow(p, st), onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def make_pdf_2col(p: dict, font: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, PageTemplate, Paragraph

    st = _pdf_styles(font)
    buf = io.BytesIO()
    w, h = A4
    left = Frame(30, 40, 170, h - 80, id="left")
    right = Frame(215, 40, w - 245, h - 80, id="right")
    doc = BaseDocTemplate(buf, pagesize=A4, invariant=1, **_doc_kwargs())
    doc.addPageTemplates([PageTemplate(id="two", frames=[left, right])])
    story = [Paragraph(_esc(p["name"]), st["title"])]
    for heading, lines in p["left"]:
        story.append(Paragraph(_esc(heading), st["h"]))
        story += [Paragraph(_esc(x), st["p"]) for x in lines]
    story.append(FrameBreak())
    story.append(Paragraph(_esc(p["title"]), st["title"]))
    story += _flow(p, st, with_head=False)
    doc.build(story)
    return buf.getvalue()


# --------------------------------------------------------------------------- DOCX
def _clean_docx_props(doc) -> None:
    cp = doc.core_properties
    cp.author = ""
    cp.last_modified_by = ""
    cp.title = ""
    cp.comments = ""


def _add_lines(container, lines: list[str], numbered_style: str | None = None) -> None:
    for line in lines:
        if line.startswith("# ") and numbered_style:
            container.add_paragraph(line[2:], style=numbered_style)
        elif line.startswith("- "):
            container.add_paragraph(line[2:], style="List Bullet")
        else:
            container.add_paragraph(line)


def make_docx_headings(p: dict) -> bytes:
    from docx import Document

    doc = Document()
    _clean_docx_props(doc)
    doc.add_paragraph(p["name"], style="Title")
    doc.add_paragraph(p["title"])
    for c in p["contact"]:
        doc.add_paragraph(c)
    for heading, lines in p["sections"]:
        doc.add_paragraph(heading, style="Heading 1")
        _add_lines(doc, lines, numbered_style="List Number")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_docx_layout(p: dict) -> bytes:
    from docx import Document

    doc = Document()
    _clean_docx_props(doc)
    header = doc.sections[0].header
    header.paragraphs[0].text = p["name"]
    header.add_paragraph(p["contact"][0])
    table = doc.add_table(rows=2, cols=2)
    title = table.cell(0, 0).merge(table.cell(0, 1))  # ô gộp ngang
    title.text = p["title"]
    left, right = table.cell(1, 0), table.cell(1, 1)
    left.paragraphs[0].text = p["left"][0][0]
    for heading, lines in p["left"]:
        if heading != p["left"][0][0]:
            left.add_paragraph(heading)
        for line in lines:
            left.add_paragraph(line)
    right.paragraphs[0].text = p["sections"][0][0]
    for i, (heading, lines) in enumerate(p["sections"]):
        if i:
            right.add_paragraph(heading)
        for line in lines:
            right.add_paragraph(line[2:] if line.startswith("- ") else line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- edge
def make_scan_pdf(pdf_bytes: bytes) -> bytes:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    image = pdf[0].render(scale=1).to_pil().convert("L")
    pdf.close()
    buf = io.BytesIO()
    image.save(buf, format="PDF", resolution=72)
    return buf.getvalue()


def make_encrypted_pdf(p: dict, font: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.pdfencrypt import StandardEncryption
    from reportlab.platypus import SimpleDocTemplate

    buf = io.BytesIO()
    enc = StandardEncryption("mat-khau-gia", ownerPassword="chu-file-gia", strength=128)
    doc = SimpleDocTemplate(buf, pagesize=A4, encrypt=enc, invariant=1, **_doc_kwargs())
    doc.build(_flow(p, _pdf_styles(font)))
    return buf.getvalue()


def manual_markdown(cid: str, p: dict) -> str:
    kind, _, how = MANUAL[cid]
    lines = [
        f"# {cid}: nội dung giả để làm tay ({how})",
        "",
        "Gõ hoặc dán nguyên văn nội dung dưới đây. Giữ nguyên chữ hoa/thường của tiêu đề.",
        f"Lưu thành `tests/fixtures/cv/samples/{cid}.{kind}`. Xem README.md mục Làm tay.",
        "",
    ]
    lines += [f"**{p['name']}**", "", p["title"], ""]
    for heading, items in p.get("left", []):
        lines += [f"[Cột trái] **{heading}**", *[f"- {x}" for x in items], ""]
    if p.get("contact"):
        lines += ["[Liên hệ]", *[f"- {x}" for x in p["contact"]], ""]
    for heading, items in p["sections"]:
        lines += [f"**{heading}**", *items, ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", help="font TTF có tiếng Việt (mặc định: Arial/DejaVu)")
    args = parser.parse_args(argv)
    font = args.font or next((f for f in FONTS if Path(f).exists()), None)
    if not font:
        parser.error("không thấy font TTF có tiếng Việt, truyền --font")
    for sub in ("samples", "expected", "edge", "manual"):
        (FIX / sub).mkdir(parents=True, exist_ok=True)

    files = {
        "cv01.pdf": make_pdf_1col(PERSONAS["cv01"], font),
        "cv02.pdf": make_pdf_1col(PERSONAS["cv02"], font),
        "cv03.pdf": make_pdf_2col(PERSONAS["cv03"], font),
        "cv04.pdf": make_pdf_1col(PERSONAS["cv04"], font),
        "cv05.pdf": make_pdf_1col(PERSONAS["cv05"], font, header=PERSONAS["cv05"]["header"]),
        "cv08.docx": make_docx_headings(PERSONAS["cv08"]),
        "cv09.docx": make_docx_layout(PERSONAS["cv09"]),
    }
    for name, data in files.items():
        (FIX / "samples" / name).write_bytes(data)
    (FIX / "edge" / "scan_image_only.pdf").write_bytes(make_scan_pdf(files["cv01.pdf"]))
    (FIX / "edge" / "encrypted_userpw.pdf").write_bytes(make_encrypted_pdf(PERSONAS["cv02"], font))

    for cid, p in {**PERSONAS, **MANUAL_PERSONAS}.items():
        exp = landmarks(p)
        kind = MANUAL[cid][0] if cid in MANUAL else ("docx" if cid in ("cv08", "cv09") else "pdf")
        exp |= {"file": f"{cid}.{kind}", "manual": cid in MANUAL}
        text = yaml.safe_dump(exp, allow_unicode=True, sort_keys=False, width=100)
        (FIX / "expected" / f"{cid}.yaml").write_text(text, encoding="utf-8")
    for cid, p in MANUAL_PERSONAS.items():
        (FIX / "manual" / f"{cid}.md").write_text(manual_markdown(cid, p), encoding="utf-8")
    print(f"{len(files)} file mẫu + 2 file lỗi + {len(PERSONAS) + len(MANUAL)} expected → {FIX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
