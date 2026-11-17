"""S3-D04 "hồ sơ JSON đúng trên 10 CV" + đọc khoảng thời gian, gộp số năm, câu trích."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from cvparser.dates import find_ranges, total_months
from cvparser.extract import extract_document
from cvparser.profile import CvProfile, build_profile, to_db_rows
from cvparser.redact import redact
from cvparser.sections import split_sections

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "cv"
GOLD = yaml.safe_load((FIX / "profile" / "gold.yaml").read_text(encoding="utf-8"))
AS_OF = GOLD["as_of"]
PII = yaml.safe_load((FIX.parent / "pii" / "cv_pii.yaml").read_text(encoding="utf-8"))


def profile_of(cid: str) -> CvProfile:
    sample = next((FIX / "samples").glob(f"{cid}.*"))
    result = extract_document(sample.read_bytes(), filename=sample.name)
    red = redact(result.text)
    return build_profile(red.text, split_sections(red.text), result.tables, as_of=AS_OF)


def check_profile(p: CvProfile, gold: dict, pii: list[str]) -> list[str]:
    """Lý do không đạt (rỗng = đạt). Dùng chung cho test và báo cáo."""
    problems = []
    if p.target_title != gold["target_title"]:
        problems.append(f"chức danh {p.target_title!r} != {gold['target_title']!r}")
    if p.years_exp is None or abs(p.years_exp - gold["years_exp"]) > 0.1:
        problems.append(f"số năm {p.years_exp} != {gold['years_exp']}")
    ignore = set(gold.get("dictionary_issues") or {})
    for level in ("strong", "listed"):
        got = {s.skill_id for s in p.skills if s.evidence_level == level} - ignore
        want = set(gold[level])
        if got != want:
            problems.append(f"{level}: thừa {sorted(got - want)}, thiếu {sorted(want - got)}")
    by_id = {s.skill_id: s for s in p.skills}
    for sid, exp in (gold.get("evidence") or {}).items():
        s = by_id.get(sid)
        if s is None or s.section != exp["section"] or s.context != exp.get("context"):
            problems.append(f"câu trích {sid}: {s and (s.section, s.context)} != {exp}")
    for s in p.skills:
        word = s.evidence[s.highlight[0] : s.highlight[1]]
        if not word or len(s.evidence) > 202:
            problems.append(f"câu trích {s.skill_id} sai vị trí in đậm / quá dài")
        low = s.evidence.lower()
        if any(x.lower() in low for x in pii):
            problems.append(f"câu trích {s.skill_id} lộ PII")
    CvProfile.model_validate_json(p.model_dump_json())  # JSON hợp lệ theo schema
    return problems


@pytest.mark.parametrize("cid", sorted(GOLD["cvs"]), ids=sorted(GOLD["cvs"]))
def test_profile_json_correct(cid):
    assert check_profile(profile_of(cid), GOLD["cvs"][cid], PII[cid]) == []


def test_ten_cvs():
    assert len(GOLD["cvs"]) == 10


# ----------------------------------------------------------------------------- khoảng thời gian

D = date(2026, 11, 18)


@pytest.mark.parametrize(
    ("text", "label", "months"),
    [
        ("Công ty X | 03/2023 – nay", ("2023-03", "present"), 45),
        ("07/2021 – 02/2023", ("2021-07", "2023-02"), 20),
        ("06.2019 – 12.2024", ("2019-06", "2024-12"), 67),
        ("2021-03 → 2022-05", ("2021-03", "2022-05"), 15),
        ("Tháng 3/2021 - Tháng 5/2022", ("2021-03", "2022-05"), 15),
        ("T3/2021 - T5/2022", ("2021-03", "2022-05"), 15),
        ("Mar 2021 – May 2022", ("2021-03", "2022-05"), 15),
        ("March 2021 - present", ("2021-03", "present"), 69),
        ("3/2021 - hiện tại", ("2021-03", "present"), 69),
        ("01/2022 – Present", ("2022-01", "present"), 59),
        ("2019 – 2021", ("2019-01", "2020-12"), 24),
        ("2021 - 2021", ("2021-01", "2021-06"), 6),
        ("tháng 3 năm 2021 đến tháng 6 năm 2022", ("2021-03", "2022-06"), 16),
        ("05/2025 – 06/2027", ("2025-05", "2026-11"), 19),  # kết thúc sau ngày tính: cắt
    ],
)
def test_find_ranges(text, label, months):
    (r,) = find_ranges(text, D)
    assert r.label() == label and r.months == months


@pytest.mark.parametrize(
    "text",
    [
        "Lương 15 – 20 triệu",
        "TOEIC 750, IELTS 7.0",
        "Top 10 Datathon 2021",
        "Mã dự án 2019120501",
        "01/2027 – nay",  # trong tương lai
        "05/2022 – 03/2021",  # ngược
        "Phiên bản 2.1 - 3.0",
    ],
)
def test_not_ranges(text):
    assert find_ranges(text, D) == []


def test_total_months_merges_overlap_and_skips_gaps():
    rs = [
        *find_ranges("01/2020 – 12/2020", D),
        *find_ranges("06/2020 – 06/2021", D),  # chồng: không cộng đôi
        *find_ranges("01/2023 – 03/2023", D),  # sau khoảng trống
    ]
    assert total_months(rs) == 18 + 3


# ----------------------------------------------------------------------------- luật hồ sơ


def _profile(text: str):
    red = redact(text)
    return build_profile(red.text, split_sections(red.text), as_of=D)


def test_internship_not_counted_and_reported():
    p = _profile(
        "Nguyễn Văn A\nBackend Developer\nKINH NGHIỆM\n"
        "Công ty X | 01/2023 – 12/2024\nLập trình viên Java\n"
        "Công ty Y | 06/2022 – 11/2022\nThực tập sinh Java\n"
    )
    assert p.years_exp == 2.0 and p.internship_months == 6
    assert [e.is_internship for e in p.entries] == [False, True]


def test_education_dates_not_counted_and_no_experience_warning():
    p = _profile("Nguyễn Văn A\nHỌC VẤN\nĐại học Y | 2016 – 2020\nKỸ NĂNG\nPython, SQL")
    assert p.years_exp is None and "no_experience_section" in p.warnings
    assert {s.evidence_level for s in p.skills} == {"listed"}


def test_strong_beats_listed_and_snippet_from_experience():
    p = _profile(
        "Nguyễn Văn A\nKỸ NĂNG\nJava, Docker\nKINH NGHIỆM\nCông ty X | 2020 – 2022\n"
        "- Triển khai Docker cho 10 dịch vụ\n"
    )
    docker = next(s for s in p.skills if s.skill_id == "docker")
    assert docker.evidence_level == "strong" and docker.context == "Công ty X"
    assert docker.evidence == "Triển khai Docker cho 10 dịch vụ" and docker.mentions == 2
    assert docker.evidence[slice(*docker.highlight)] == "Docker"
    java = next(s for s in p.skills if s.skill_id == "java")
    assert java.evidence_level == "listed" and java.years is None


def test_long_line_snippet_is_cut_around_skill():
    long = "Phát triển hệ thống " + "rất lớn " * 40 + "bằng Kubernetes và " + "nhiều thứ " * 30
    p = _profile(f"Nguyễn Văn A\nKINH NGHIỆM\nCông ty X | 2020 – 2022\n- {long}")
    k8s = next(s for s in p.skills if s.skill_id == "kubernetes")
    assert len(k8s.evidence) <= 202 and k8s.evidence.startswith("…") and k8s.evidence.endswith("…")
    assert k8s.evidence[slice(*k8s.highlight)] == "Kubernetes"


def test_header_skills_ignored_and_fallback_listed():
    p = _profile("Nguyễn Văn A\nJava Developer\nEmail: a@example.com\nKỸ NĂNG\nSQL")
    # "Java Developer" ở phần đầu CV là chức danh, không phải bằng chứng kỹ năng
    assert [(s.skill_id, s.evidence_level) for s in p.skills] == [("sql", "listed")]
    q = _profile("Tôi biết Python và SQL, đã làm Docker.")
    assert {s.evidence_level for s in q.skills} == {"listed"}


def test_to_db_rows():
    p = profile_of("cv01")
    cvs, rows = to_db_rows(p, {"java": 1, "git": 2})
    assert cvs == {"years_exp": 5.4, "target_title": "Lập trình viên Backend"}
    assert {(r["skill_id"], r["evidence_level"]) for r in rows} == {(1, "strong"), (2, "listed")}
    assert all(r["confirmed"] is False and r["evidence"] for r in rows)


def test_title_first_job_line_company_and_contact_labels():
    """Mẫu CV tiếng Anh (S3-D06): "Chức danh — Công ty" rồi dòng "ngày | nơi làm"; "GitHub:"
    là nhãn liên hệ; tên trường/ngành ở Học vấn không phải kỹ năng; chức danh bỏ phần ngoặc."""
    p = _profile(
        "PART I — ENGLISH VERSION\nNguyễn Văn A\nFull-Stack Software Engineer (Node.js / React)\n"
        "GitHub: github.com/an | Email: a@example.com\nWORK EXPERIENCE\n"
        "Backend Developer — FinTech Viet Technology JSC\nJune 2024 – Present | Hanoi, Vietnam\n"
        "Built Spring Boot services.\nJunior Developer — Blue Lotus Cloud\n"
        "January 2023 – May 2024 | Hanoi, Vietnam\nWrote SQL reports.\nEDUCATION\n"
        "B.Eng. in Computer Science — Academy of Cryptography Techniques (2018 – 2022)\n"
        "PHẦN II — PHIÊN BẢN TIẾNG VIỆT\nNguyễn Văn A\nGitHub: github.com/an\n"
    )
    assert (p.target_title, p.target_title_source) == ("Full-Stack Software Engineer", "header")
    ids = {s.skill_id for s in p.skills}
    assert {"spring_boot", "sql"} <= ids
    assert not ids & {"fintech", "cloud_computing", "github", "cryptography"}
    jobs = [(e.org, e.title) for e in p.entries]
    assert jobs == [
        ("FinTech Viet Technology JSC", "Backend Developer"),
        ("Blue Lotus Cloud", "Junior Developer"),
    ]
    sb = next(s for s in p.skills if s.skill_id == "spring_boot")
    assert sb.context == "FinTech Viet Technology JSC"
