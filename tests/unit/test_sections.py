"""S2-D03: tách 4 section JD theo heading Việt–Anh."""

import json

import pytest

from scripts.section_report import DOC_TARGET, GOLD, evaluate
from skillkit.sections import assign_lines, explode, html_to_text, split_jobposting, split_text

TOPCV = """Tuyển dụng Backend Developer
Mô tả công việc
- Phát triển API bằng Java Spring Boot
- Trách nhiệm cao trong công việc
Yêu cầu ứng viên
- 3 năm kinh nghiệm Java
- Ưu tiên biết Docker, Kubernetes
- Có kinh nghiệm AWS là một lợi thế
- Có thẩm mỹ tốt (ưu tiên mạnh về thiết kế in ấn)
Quyền lợi
- Lương 20-30 triệu
Địa điểm làm việc
- Hà Nội"""


def test_topcv_layout():
    r = split_text(TOPCV)
    assert r.method == "heading"
    assert r.description.splitlines() == [
        "- Phát triển API bằng Java Spring Boot",
        "- Trách nhiệm cao trong công việc",
    ]
    assert r.requirements.splitlines() == [
        "- 3 năm kinh nghiệm Java",
        "- Có thẩm mỹ tốt (ưu tiên mạnh về thiết kế in ấn)",
    ]
    assert r.preferred.splitlines() == [
        "- Ưu tiên biết Docker, Kubernetes",
        "- Có kinh nghiệm AWS là một lợi thế",
    ]
    assert r.benefits == "- Lương 20-30 triệu"
    assert r.other.splitlines() == ["Tuyển dụng Backend Developer", "- Hà Nội"]


@pytest.mark.parametrize(
    ("heading", "section"),
    [
        ("Job description", "description"),
        ("🎯 **Responsibilities**", "description"),
        ("1. MÔ TẢ CÔNG VIỆC:", "description"),
        ("Your skills and experience", "requirements"),
        ("YÊU CẦU ỨNG VIÊN", "requirements"),
        ("Nice to have", "preferred"),
        ("ĐIỂM CỘNG/ƯU TIÊN ỨNG VIÊN:", "preferred"),
        ("Tại sao bạn sẽ yêu thích làm việc tại đây", "benefits"),
        ("Why you'll love working here", "benefits"),
        ("Các phúc lợi dành cho bạn", "benefits"),
    ],
)
def test_heading_variants(heading, section):
    r = split_text(f"{heading}\n- nội dung mẫu")
    assert getattr(r, section) == "- nội dung mẫu"


@pytest.mark.parametrize(
    "line",
    [
        "Trách nhiệm cao trong công việc",  # nội dung, không phải heading "Trách nhiệm"
        "Ưu tiên biết Docker",  # dòng ưu tiên, không mở section mới
        "Yêu cầu tối thiểu 2 năm kinh nghiệm Java.",
    ],
)
def test_content_lines_are_not_headings(line):
    labels = [label for _, label in assign_lines(f"Yêu cầu\n{line}")]
    assert labels[1] != "heading"


def test_inline_heading_and_sentence_split():
    r = split_text("Yêu cầu: 3 năm Java. Ưu tiên biết Docker.\nQuyền lợi: Thưởng tháng 13")
    assert r.requirements == "3 năm Java."
    assert r.preferred == "Ưu tiên biết Docker."
    assert r.benefits == "Thưởng tháng 13"


@pytest.mark.parametrize(
    ("line", "parts"),
    [
        ("Thành thạo Node.js và ASP.NET. Biết Go.", ["Thành thạo Node.js và ASP.NET.", "Biết Go."]),
        ("1. Phát triển ứng dụng:", ["1. Phát triển ứng dụng:"]),
    ],
)
def test_explode(line, parts):
    assert explode(line) == parts


def test_parenthetical_marker_makes_line_preferred():
    r = split_text("Yêu cầu\n- Có dự án cá nhân về scripting (điểm cộng, không bắt buộc)")
    assert r.preferred and not r.requirements


def test_unknown_heading_inferred_from_content():
    text = "Bạn nhận được gì\n- Thưởng tháng 13\n- Bảo hiểm đầy đủ\n- Nghỉ phép 12 ngày"
    assert split_text(text).benefits.count("\n") == 2


def test_fallback_without_headings():
    r = split_text("Chúng tôi cần lập trình viên Python có 2 năm kinh nghiệm.")
    assert r.method == "fallback" and r.description.startswith("Chúng tôi")


def test_jsonld_structured_fields():
    posting = {
        "description": "<h2>Mô tả công việc</h2><ul><li>Phát triển API</li></ul>",
        "qualifications": "3 năm Java",
        "jobBenefits": ["Thưởng tháng 13", "Bảo hiểm"],
    }
    r = split_jobposting(posting)
    assert r.method == "structured"
    assert r.description == "Phát triển API"
    assert r.requirements == "3 năm Java"
    assert r.benefits == "Thưởng tháng 13\nBảo hiểm"
    assert r.columns()["preferred"] is None


def test_html_to_text_keeps_blocks():
    assert html_to_text("<p>A&amp;B</p><ul><li>x</li><li>y</li></ul>").split() == ["A&B", "x", "y"]


@pytest.mark.skipif(
    not GOLD.exists(), reason="chưa có data/eval/jd_gold.jsonl (dữ liệu không lên git)"
)
def test_gold_set_meets_target():
    """Done S2-D03: tách đúng ≥ 90% trên 50 JD gán tay."""
    samples = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines()]
    results, _ = evaluate(samples)
    assert len(samples) == 50
    assert sum(r["ok"] for r in results) / len(results) >= DOC_TARGET
