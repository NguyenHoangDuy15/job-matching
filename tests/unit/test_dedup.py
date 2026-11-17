"""S3-T03: khóa khử trùng chính xác (URL chuẩn hóa, dedup hash)."""

import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingestion.dedup import canonical_url, dedup_hash
from ingestion.jsonld import find_job_posting, parse_job_posting
from ingestion.location import default_index
from ingestion.store import build_job_row, company_name_norm, content_hash

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "crawl"
JD = (
    "Mô tả công việc:\n• Xây dựng pipeline dữ liệu bằng Python, Airflow và PostgreSQL.\n"
    "• Thiết kế mô hình dữ liệu cho hệ thống gợi ý việc làm.\n"
    "Yêu cầu:\n- Tối thiểu 2 năm kinh nghiệm Data Engineer.\n- Thành thạo SQL, Spark là lợi thế.\n"
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://itviec.com/it-jobs/data-engineer-123",
            "https://itviec.com/it-jobs/data-engineer-123",
        ),
        (
            "http://www.ITviec.com/it-jobs/data-engineer-123/",
            "https://itviec.com/it-jobs/data-engineer-123",
        ),
        ("https://itviec.com//it-jobs/x-1?utm_source=fb#apply", "https://itviec.com/it-jobs/x-1"),
        ("  https://www.topcv.vn/viec-lam/Abc/99.html  ", "https://topcv.vn/viec-lam/Abc/99.html"),
        ("https://example.test:8443/a", "https://example.test:8443/a"),
        ("https://example.test:443/a", "https://example.test/a"),
        ("https://example.test", "https://example.test"),
    ],
)
def test_canonical_url(url, expected):
    assert canonical_url(url) == expected


def test_dedup_hash_ignores_formatting():
    base = dedup_hash("Data Engineer", "fpt software", [1], JD)
    assert base is not None
    reformatted = JD.upper().replace("• ", "* ").replace("\n", "  \n\n ").replace(",", " ,")
    assert dedup_hash("DATA ENGINEER ", "fpt software", [1], reformatted) == base
    # cùng chữ nhưng khác dạng Unicode (NFD/NFC) giữa hai trang
    assert (
        dedup_hash("Data Engineer", "fpt software", [1], unicodedata.normalize("NFD", JD)) == base
    )
    assert dedup_hash("Data Engineer", "fpt software", (1, 1), JD) == base


def test_dedup_hash_province_order_does_not_matter():
    assert dedup_hash("Dev", "abc", [79, 1], JD) == dedup_hash("Dev", "abc", [1, 79], JD)


@pytest.mark.parametrize(
    "change",
    [
        {"title": "Senior Data Engineer"},
        {"company": "vng"},
        {"provinces": [79]},
        {"text": JD + "Làm việc tại TP. Hồ Chí Minh."},
    ],
)
def test_dedup_hash_sensitive_to_identity_fields(change):
    args = {"title": "Data Engineer", "company": "fpt software", "provinces": [1], "text": JD}
    base = dedup_hash(args["title"], args["company"], args["provinces"], args["text"])
    args |= change
    assert dedup_hash(args["title"], args["company"], args["provinces"], args["text"]) != base


def test_dedup_hash_none_when_not_enough_to_be_sure():
    assert dedup_hash("Java Developer", "fpt software", [1], "Java, Spring") is None
    assert dedup_hash("Java Developer", "fpt software", [1], None) is None
    assert dedup_hash("Data Engineer", None, [1], JD) is None
    assert dedup_hash("Data Engineer", "", [1], JD) is None


def test_build_job_row_uses_dedup_hash_and_keeps_source_hash():
    item = find_job_posting((FIXTURES / "itviec_job.html").read_text(encoding="utf-8"))
    posting = parse_job_posting(
        item,
        source="itviec",
        source_job_id="1",
        url="https://itviec.com/it-jobs/x-1",
        fetched_at=datetime(2026, 11, 17, tzinfo=UTC),
    )
    posting = posting.model_copy(update={"description_text": JD})  # fixture quá ngắn để băm
    row = build_job_row(posting, default_index(), {}, posting.fetched_at.date())
    assert row.columns["content_hash"] is not None
    assert row.source_hash == content_hash(posting)
    assert row.columns["content_hash"] == dedup_hash(
        posting.title,
        company_name_norm(posting.company_name),
        row.province_codes,
        posting.description_text,
    )
    # cùng tin ở nguồn khác (khác mã, URL, hạn nộp, lương) → cùng dedup hash
    other = posting.model_copy(
        update={"source": "vietnamworks", "source_job_id": "9", "url": "https://vnw/9"}
    )
    other_row = build_job_row(other, default_index(), {}, other.fetched_at.date())
    assert other_row.columns["content_hash"] == row.columns["content_hash"]
