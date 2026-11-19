"""S3-D03 "20/20 mẫu không lộ PII": 10 CV mẫu + 10 mẫu khó, kiểm cả che thiếu lẫn che thừa."""

import re
from pathlib import Path

import pytest
import yaml

from cvparser.extract import extract_document
from cvparser.redact import fold_keep_length, redact
from cvparser.sections import split_sections

FIX = Path(__file__).resolve().parents[1] / "fixtures"
HARD = yaml.safe_load((FIX / "pii" / "samples.yaml").read_text(encoding="utf-8"))["samples"]
CV_PII = yaml.safe_load((FIX / "pii" / "cv_pii.yaml").read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return " ".join(fold_keep_length(s).split())


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def leaks(redacted: str, pii: list[str]) -> list[str]:
    """PII còn sót: so không dấu/không phân biệt hoa thường; SĐT/số giấy tờ so theo dãy số."""
    out = []
    for p in pii:
        number = len(_digits(p)) >= 9 and _digits(p)[-9:] in _digits(redacted)
        if _norm(p) in _norm(redacted) or number:
            out.append(p)
    return out


def _skills(text: str) -> set[str]:
    from skillkit.levels.pipeline import SKILLS_YAML
    from skillkit.matcher import SkillMatcher
    from skillkit.taxonomy import load_taxonomy

    return set(SkillMatcher(load_taxonomy(SKILLS_YAML)).skills(text))


# ----------------------------------------------------------------------------- 20 mẫu


@pytest.mark.parametrize("cid", sorted(CV_PII), ids=sorted(CV_PII))
def test_cv_samples_no_leak_and_skills_kept(cid):
    sample = next((FIX / "cv" / "samples").glob(f"{cid}.*"))
    text = extract_document(sample.read_bytes(), filename=sample.name).text
    red = redact(text)
    assert leaks(red.text, CV_PII[cid]) == []
    assert _skills(red.text) == _skills(text)  # không che nhầm kỹ năng nào
    assert not red.warnings


@pytest.mark.parametrize("sample", HARD, ids=[s["id"] for s in HARD])
def test_hard_samples_no_leak_no_overmask(sample):
    red = redact(sample["text"])
    assert leaks(red.text, sample["pii"]) == []
    lost = [k for k in sample["keep"] if _norm(k) not in _norm(red.text)]
    assert lost == []


def test_twenty_samples():
    assert len(CV_PII) + len(HARD) == 20


# ----------------------------------------------------------------------------- từng luật


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        ("Liên hệ: 0912 000 101", True),
        ("SĐT 0912.000.101", True),
        ("(+84) 912-000-101", True),
        ("+84912000101", True),
        ("Tel:0912000101", True),
        ("Máy bàn 024 3999 8888", True),
        ("Làm việc 2017 – 2021", False),
        ("Lương 15.000.000 – 20.000.000", False),
        ("Mã dự án 2019120501", False),
        ("Phiên bản 0.12.000.101", False),
    ],
)
def test_phone(text, masked):
    assert ("[SĐT]" in redact(text).text) is masked


def test_email_variants_and_profile_links():
    out = redact(
        "a.b@example.com · c [at] example [dot] vn · github.com/abc · linkedin.com/in/x"
    ).text
    assert out.count("[EMAIL]") == 2 and out.count("[LINK]") == 2


def test_labels_keep_label_and_mask_value():
    out = redact(
        "Họ tên: Trần Văn Bình · Ngày sinh: 01/02/2000 · Giới tính: Nam\nCCCD: 001200000999"
    ).text
    assert out == "Họ tên: [HỌ_TÊN] · Ngày sinh: [NGÀY_SINH] · Giới tính: [ẨN]\nCCCD: [SỐ_GIẤY_TỜ]"


def test_address_keeps_province_and_returns_code():
    red = redact("Nguyễn Văn A\nĐịa chỉ: Số 1 ngõ 2 phố Huế, phường Phố Huế, Hà Nội\nKỸ NĂNG\nJava")
    assert "Địa chỉ: [ĐỊA_CHỈ], Hà Nội" in red.text and red.province_codes == [1]


def test_common_words_are_not_address_or_name():
    text = (
        "Nguyễn Văn A\nKINH NGHIỆM\n- Xây dựng nền tảng dữ liệu, đường ống ETL trên tầng ứng dụng\n"
        "- Làm việc tại Hà Nội và Đà Nẵng\nHỌC VẤN\nĐại học Bách khoa Hà Nội | 2016 – 2020\n"
        "Trường THPT Lê Quý Đôn"
    )
    out = redact(text).text
    assert out.split("\n")[1:] == text.split("\n")[1:]  # chỉ dòng tên bị che


def test_name_found_once_is_masked_everywhere():
    text = "Lê Thu Hà\nKINH NGHIỆM\nDự án của LE THU HA\nThu Hà Lê viết tài liệu\nTôi là Hà."
    out = redact(text).text
    assert "thu ha" not in fold_keep_length(out) and "le thu" not in fold_keep_length(out)
    assert out.count("[HỌ_TÊN]") == 4


def test_given_name_alone_is_masked():
    text = (
        "NGUYỄN VĂN HÙNG\nKINH NGHIỆM\n"
        "- Hùng phụ trách mentoring; anh Hùng viết tài liệu. Thanks to Hung for the review.\n"
    )
    out = redact(text).text
    assert "hung" not in fold_keep_length(out)
    assert out.count("[HỌ_TÊN]") == 4


@pytest.mark.parametrize(
    "line",
    [
        "Văn phòng ở đường Trần Duy Hưng, Hà Nội",  # dấu khác: Hưng ≠ Hùng
        "Văn phòng ở đường Phạm Hùng",  # dính chữ hoa liền trước: tên đường
        "Dự án Hùng Vương Plaza",  # dính chữ hoa liền sau
        "Viết API bằng Python, Django",
    ],
)
def test_given_name_not_masked_inside_other_names(line):
    out = redact(f"Nguyễn Văn Hùng\nKINH NGHIỆM\n{line}").text
    assert out.split("\n")[2] == line


def test_given_name_like_english_word_kept_when_alone():
    out = redact("Trần An\nKINH NGHIỆM\nAn experienced developer.\nTôi là An.").text
    assert "An experienced developer." in out
    assert "Tôi là [HỌ_TÊN]." in out


def test_known_names_from_account():
    out = redact(
        "KINH NGHIỆM\nNgười phụ trách: anh Bình\nCảm ơn Trần Văn Bình",
        known_names=["Trần Văn Bình"],
    )
    assert "Trần Văn Bình" not in out.text


def test_dates_of_work_are_not_masked():
    text = "Nguyễn Văn A\nKINH NGHIỆM\nCông ty X | 03/2021 – nay\nCông ty Y | 2019 – 2021"
    out = redact(text).text
    assert "03/2021 – nay" in out and "2019 – 2021" in out


def test_sections_same_after_redaction():
    sample = FIX / "cv" / "samples" / "cv01.pdf"
    text = extract_document(sample.read_bytes()).text
    before = [(s.name, s.heading) for s in split_sections(text).sections]
    after = [(s.name, s.heading) for s in split_sections(redact(text).text).sections]
    assert after == before  # S3-D05 tách section trên văn bản đã che


def test_result_has_no_pii_values():
    red = redact("Nguyễn Văn A\nEmail: a@example.com")
    dumped = red.model_dump_json(exclude={"text"})
    assert "example.com" not in dumped and "Nguyễn" not in dumped


@pytest.mark.parametrize("name", ["VO DUC QUAN", "TRẦN ĐỨC QUÂN", "Ngô Thị Huyền", "LY THU PHUONG"])
def test_names_like_district_words_are_masked(name):
    """Quân/Huyền/Phương bỏ dấu trùng quận/huyện/phường: vẫn là tên (S3-D06, CV thật)."""
    out = redact(f"PART I — ENGLISH VERSION\n{name}\nBackend Developer\nKỸ NĂNG\nJava").text
    assert name not in out and "[HỌ_TÊN]" in out


def test_place_lines_still_not_names():
    for line in ("Quận Cầu Giấy", "Phường Bến Nghé", "Trường Sơn Hà"):
        assert redact(f"KỸ NĂNG\nJava\nHỌC VẤN\n{line}").text.endswith(line)


def test_portfolio_links_masked_everywhere():
    text = (
        "Nguyễn Văn A\nApp Store / Play Store Portfolio: an.dev | huggingface.co/anvan\n"
        "Portfolio: an.dev | Web: an-portfolio.vercel.app\nKỸ NĂNG\nJava"
    )
    out = redact(text).text
    assert "an.dev" not in out and "anvan" not in out and "an-portfolio" not in out
    assert "huggingface.co/[LINK]" in out
