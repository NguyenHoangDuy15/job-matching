"""S2-T03: đọc JSON-LD JobPosting và chuyển thành dòng core.jobs."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ingestion.jsonld import find_job_posting, parse_job_posting
from ingestion.location import default_index
from ingestion.store import build_job_row, company_name_norm, content_hash

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "crawl"
FETCHED = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)


def _posting(name: str, source: str, job_id: str):
    item = find_job_posting((FIXTURES / name).read_text(encoding="utf-8"))
    assert item is not None
    return parse_job_posting(
        item, source=source, source_job_id=job_id, url=f"https://x/{job_id}", fetched_at=FETCHED
    )


@pytest.fixture
def itviec():
    return _posting("itviec_job.html", "itviec", "1234")


@pytest.fixture
def vnw():
    return _posting("vietnamworks_job.html", "vietnamworks", "1900002")


def test_find_job_posting_skips_other_ld_blocks():
    page = (FIXTURES / "itviec_job.html").read_text(encoding="utf-8")
    assert find_job_posting(page)["@type"] == "JobPosting"


def test_find_job_posting_inside_graph():
    page = (FIXTURES / "vietnamworks_job.html").read_text(encoding="utf-8")
    assert find_job_posting(page)["title"].startswith("DevOps Engineer")


def test_find_job_posting_none_when_missing():
    assert find_job_posting("<html><script type='application/ld+json'>{}</script></html>") is None


def test_parse_itviec_fields(itviec):
    assert itviec.title == "Backend Developer (Java, Spring Boot)"
    assert itviec.company_name == "Công ty TNHH Công Nghệ A"
    assert itviec.company_logo == "https://cdn.example.com/logo-a.png"
    assert itviec.date_posted == date(2026, 11, 5)
    assert itviec.valid_through == date(2026, 12, 5)
    assert itviec.years_exp_min == 3.0
    assert itviec.skills_text == "Java, Spring Boot, PostgreSQL"
    assert itviec.salary is None
    assert itviec.location_text() == "Hồ Chí Minh"


def test_description_is_text_and_contacts_masked(itviec):
    text = itviec.description_text
    assert "Phát triển API bằng Java" in text
    assert "<li>" not in text
    assert "hr@congtya.vn" not in text and "[email]" in text
    assert "0912 345 678" not in text and "[phone]" in text


def test_parse_vnw_escaped_description_list_type_and_salary(vnw):
    assert vnw.description_text.splitlines()[0] == "Vận hành hạ tầng AWS và Kubernetes."
    assert vnw.employment_type == "FULL_TIME"
    assert vnw.remote is True
    assert vnw.valid_through == date(2026, 10, 31)
    assert vnw.salary.min_value == 25_000_000 and vnw.salary.max_value == 40_000_000
    assert vnw.location_text() == "Ha Noi, Hà Nội; Đà Nẵng"


def test_build_row_itviec(itviec):
    row = build_job_row(itviec, default_index(), {}, date(2026, 11, 9))
    assert row.province_codes == (79,)
    assert row.columns["work_mode"] == "onsite"
    assert row.columns["status"] == "open"
    assert row.columns["salary_status"] == "missing"
    assert row.columns["salary_min_vnd"] is None
    assert row.columns["title_norm"] == "backend developer java spring boot"
    assert row.columns["origin"] == "crawled"
    assert row.columns["apply_url"] == "https://x/1234"


def test_build_row_vnw_salary_remote_and_expired(vnw):
    row = build_job_row(vnw, default_index(), {}, date(2026, 11, 9))
    assert set(row.province_codes) == {1, 48}
    assert row.columns["work_mode"] == "remote"
    assert row.columns["status"] == "expired"  # validThrough 31/10 < 09/11
    assert row.columns["salary_status"] == "parsed"
    assert row.columns["salary_min_vnd"] == 25_000_000
    assert row.columns["salary_max_vnd"] == 40_000_000
    assert row.columns["salary_currency"] == "VND"


def test_content_hash_stable_and_sensitive(itviec):
    assert content_hash(itviec) == content_hash(itviec.model_copy())
    changed = itviec.model_copy(update={"description_text": itviec.description_text + " mới"})
    assert content_hash(changed) != content_hash(itviec)
    later = itviec.model_copy(update={"fetched_at": datetime(2026, 11, 10, tzinfo=UTC)})
    assert content_hash(later) == content_hash(itviec)  # thời điểm tải không làm đổi hash


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Công ty TNHH Công Nghệ A", "cong nghe a"),
        ("Cong ty Co phan B JSC", "b"),
        ("FPT Software Co., Ltd", "fpt software"),
        ("KMS Technology", "kms technology"),
        ("Công ty", "cong ty"),  # bỏ hết thì giữ nguyên tên đã chuẩn hóa
    ],
)
def test_company_name_norm(name, expected):
    assert company_name_norm(name) == expected


def test_salary_text_from_numbers(vnw):
    assert vnw.salary_text() == "25,000,000 - 40,000,000 VND"
