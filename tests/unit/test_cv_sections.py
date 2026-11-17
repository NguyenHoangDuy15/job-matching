"""S3-D02: tách section CV Việt–Anh. "Đúng section trên 10 CV mẫu" + từng luật riêng."""

from pathlib import Path

import pytest
import yaml

from cvparser.extract import extract_document
from cvparser.sections import load_lexicon, match_heading, split_sections

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "cv"
EXPECTED = sorted((FIX / "expected").glob("cv*.yaml"))
EVIDENCE = {"experience", "projects", "skills"}  # D04 dựa trực tiếp vào 3 mục này
MIN_LINE_ACCURACY = 0.95


def _flat(s: str) -> str:
    return " ".join(s.split()).lower()


def check_sections(result, exp: dict) -> list[str]:
    """Lý do không đạt (rỗng = đạt). Dùng chung cho test và báo cáo."""
    secs = split_sections(result.text, result.blocks)
    problems = []
    got = [(_flat(s.heading), s.name) for s in secs.sections if s.heading]
    want = [(_flat(h["heading"]), h["name"]) for h in exp["sections"]]
    if got != want:
        problems.append(f"heading: {got} != {want}")
    lines: dict[str, list[int]] = {}  # dòng (bỏ gạch đầu dòng) → các offset
    pos = 0
    for raw in result.text.split("\n"):
        key = _flat(raw.lstrip("-•# "))
        if key:
            lines.setdefault(key, []).append(pos + len(raw) - len(raw.lstrip()))
        pos += len(raw) + 1
    wrong, total = [], 0
    for line, name in exp["section_of"].items():
        found = lines.get(_flat(line), [])
        if len(found) != 1:
            continue  # thiếu (lỗi D01, test_cv_samples kiểm) hoặc trùng dòng (không xác định)
        total += 1
        actual = secs.section_at(found[0])
        if actual != name:
            wrong.append((line[:40], name, actual))
    accuracy = 1 - len(wrong) / total if total else 0
    if accuracy < MIN_LINE_ACCURACY:
        problems.append(f"đúng {accuracy:.2f} dòng, sai {wrong[:4]}")
    critical = [w for w in wrong if w[1] in EVIDENCE or w[2] in EVIDENCE]
    if critical:
        problems.append(f"sai ở mục D04 cần: {critical[:4]}")
    return problems


@pytest.mark.parametrize("path", EXPECTED, ids=[p.stem for p in EXPECTED])
def test_sample_cv_sections(path):
    exp = yaml.safe_load(path.read_text(encoding="utf-8"))
    sample = FIX / "samples" / exp["file"]
    result = extract_document(sample.read_bytes(), filename=sample.name)
    assert check_sections(result, exp) == []


# ----------------------------------------------------------------------------- tên mục


@pytest.mark.parametrize(
    ("line", "name"),
    [
        ("KINH NGHIỆM LÀM VIỆC", "experience"),
        ("Kinh nghiem lam viec", "experience"),  # gõ không dấu
        ("Quá trình công tác", "experience"),
        ("WORK EXPERIENCE", "experience"),
        ("Professional Experience:", "experience"),
        ("Employment History", "experience"),
        ("II. KINH NGHIỆM", "experience"),
        ("02 EXPERIENCE", "experience"),
        ("■ KINH NGHIỆM", "experience"),
        (" KINH NGHIỆM", "experience"),  # icon font
        ("DỰ ÁN", "projects"),
        ("Dự án tiêu biểu", "projects"),
        ("Personal Projects", "projects"),
        ("PROJECT EXPERIENCE", "projects"),
        ("HỌC VẤN", "education"),
        ("Trình độ học vấn", "education"),
        ("Học vấn & Bằng cấp", "education"),
        ("EDUCATION AND TRAINING", "education"),
        ("Academic Background", "education"),
        ("KỸ NĂNG", "skills"),
        ("Kỹ năng chuyên môn", "skills"),
        ("Technical Skills", "skills"),
        ("Tech Stack", "skills"),
        ("Skills & Tools", "skills"),
        ("Mục tiêu nghề nghiệp", "summary"),
        ("Giới thiệu bản thân", "summary"),
        ("Career Objective", "summary"),
        ("ABOUT ME", "summary"),
        ("Chứng chỉ", "certifications"),
        ("Licenses & Certifications", "certifications"),
        ("Ngoại ngữ", "languages"),
        ("Trình độ ngoại ngữ", "languages"),
        ("Hoạt động ngoại khóa", "activities"),
        ("Honors & Awards", "activities"),
        ("Sở thích", "other"),
        ("References", "other"),
        ("Thông tin cá nhân", "header"),
        ("CONTACT", "header"),
        ("PART I — ENGLISH VERSION", "header"),  # CV song ngữ (S3-D06)
        ("PHẦN II — PHIÊN BẢN TIẾNG VIỆT", "header"),
        ("KEY ACHIEVEMENTS", "activities"),
    ],
)
def test_heading_variants(line, name):
    assert match_heading(line) == (name, -1)


@pytest.mark.parametrize(
    "line",
    [
        "Kinh nghiệm làm việc với Docker và Kubernetes trên môi trường production",
        "Kinh nghiệm 3 năm Java",
        "Kỹ năng giao tiếp tốt.",
        "Có kinh nghiệm làm dự án",
        "Học vấn tốt, ham học hỏi, chủ động trong công việc",
        "Experience with AWS and Terraform",
        "Kinh nghiệm làm việc với Java: 3 năm",
        "",
    ],
)
def test_content_lines_are_not_headings(line):
    assert match_heading(line) is None


def test_inline_heading_returns_content_position():
    line = "Kỹ năng: Python, SQL, Docker"
    name, pos = match_heading(line)
    assert name == "skills" and line[pos:] == "Python, SQL, Docker"


def _split(text: str):
    return split_sections(text)


def test_preamble_inline_and_section_at():
    text = (
        "Nguyễn Văn A\nhung@example.com\n"
        "KINH NGHIỆM\nCông ty X | 2020 – nay\n- Java Spring Boot\n"
        "HỌC VẤN\nĐại học Y | 2016 – 2020\n"
        "Kỹ năng: Python, SQL"
    )
    s = _split(text)
    assert [x.name for x in s.sections] == ["header", "experience", "education", "skills"]
    assert s.section_at(text.index("hung@")) == "header"
    assert s.section_at(text.index("Java")) == "experience"
    assert s.section_at(text.index("Python")) == "skills"  # nội dung cùng dòng heading
    assert s.section_at(text.index("KINH NGHIỆM")) == "experience"
    assert s.to_jsonb()["skills"] == ["Python, SQL"]


def test_sub_heading_inside_experience_stays_experience():
    text = (
        "KINH NGHIỆM\nCông ty X | 2020 – nay\nDự án: Cổng thanh toán\n"
        "Công nghệ: Java, Kafka\nKỸ NĂNG\nJava"
    )
    s = _split(text)
    assert [x.name for x in s.sections] == ["experience", "skills"]
    assert s.section_at(text.index("Kafka")) == "experience"
    # Dòng IN HOA "KỸ NĂNG: …" vẫn là mục mới dù đang ở Kinh nghiệm.
    caps = _split("KINH NGHIỆM\nCông ty X | 2020 – nay\nKỸ NĂNG: Java, SQL")
    assert [x.name for x in caps.sections] == ["experience", "skills"]


def test_unknown_heading_inferred_from_dates():
    text = (
        "KỸ NĂNG\nJava\nCHẶNG ĐƯỜNG ĐÃ QUA\n"
        "Công ty Sao Mai | 03/2021 – nay\nLập trình viên Java\n"
        "Công ty Biển Xanh | 2019 – 2021\nNhân viên kiểm thử"
    )
    s = _split(text)
    assert [(x.name, x.method) for x in s.sections] == [
        ("skills", "lexicon"),
        ("experience", "inferred"),
    ]


def test_caps_skill_lines_are_not_headings():
    s = _split("KỸ NĂNG\nBPMN\nSQL\nJIRA\nREST API\nHỌC VẤN\nĐại học")
    assert [x.name for x in s.sections] == ["skills", "education"]


def test_no_heading_is_fallback():
    s = _split("Một đoạn văn không có tiêu đề nào cả.\nDòng thứ hai.")
    assert [(x.name, x.method) for x in s.sections] == [("other", "fallback")]


def test_docx_style_heading_used_for_unknown_heading():
    doc = extract_document((FIX / "samples" / "cv08.docx").read_bytes())
    s = split_sections(doc.text, doc.blocks)
    assert "projects" in [x.name for x in s.sections]


def test_lexicon_has_no_duplicate_and_version():
    lex = load_lexicon()
    assert lex.version.startswith("cv-sections-")
    assert len({p for p, _ in lex.phrases}) == len(lex.phrases)


def test_bilingual_cv_second_part_restarts_header():
    """Tên + liên hệ của phần tiếng Việt không bị gộp vào mục Học vấn/Chứng chỉ phía trước;
    nhãn che PII "[HỌ_TÊN]" (chữ HOA) không bị đoán là heading."""
    text = (
        "PART I — ENGLISH VERSION\n[HỌ_TÊN]\nBackend Developer\n"
        "EDUCATION\nB.Sc. — HUST (2019 – 2023)\n"
        "PHẦN II — PHIÊN BẢN TIẾNG VIỆT\n[HỌ_TÊN]\nGitHub: github.com/[LINK]\n"
        "KINH NGHIỆM\nCông ty X"
    )
    secs = split_sections(text)
    assert [s.name for s in secs.sections] == ["header", "education", "header", "experience"]
    assert secs.section_at(text.index("GitHub")) == "header"
