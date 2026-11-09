"""Nạp file JSONL tin tuyển dụng (định dạng topcv.jsonl) → JobPostingRaw."""

import json
from datetime import UTC, datetime

import pytest

from ingestion.jsonl_import import (
    job_id_from_url,
    load_file,
    locations_from_record,
    record_to_posting,
    years_from_text,
)
from ingestion.location import default_index
from ingestion.store import LocalStore, build_job_row

NOW = datetime(2026, 11, 9, tzinfo=UTC)
RECORD = {
    "site": "topcv",
    "job_url": "https://www.topcv.vn/viec-lam/tester-manual-automation/2169805.html",
    "title": "Tester (Manual/Automation)  –  Thu Nhập 18-24 Triệu",
    "company": "Công ty TNHH Thiết kế T&T",
    "location": "Hà Nội",
    "salary": "18 - 24 triệu",
    "experience_level": "2 năm",
    "date_posted": "2026-11-05",
    "employment_type": "FULL_TIME",
    "description": "Mô tả công việc\nViết test case\nLiên hệ hr@tt.vn\n\nYêu cầu ứng viên\nSQL",
    "work_location": "Hà Nội:\nTòa nhà VPI 167 Trung Kính\nHồ Chí Minh:\n12 Lê Lợi",
    "details_status": "ok",
}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.topcv.vn/viec-lam/abc/2169805.html", "2169805"),
        ("https://www.topcv.vn/brand/x/tuyen-dung/abc-j123456.html?ta_source=1", "123456"),
        ("https://www.topcv.vn/viec-lam", None),
    ],
)
def test_job_id_from_url(url, expected):
    assert job_id_from_url(url) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2 năm", 2.0),
        ("Trên 5 năm", 5.0),
        ("Dưới 1 năm", 0.0),
        ("Không yêu cầu kinh nghiệm", 0.0),
        ("1,5 năm", 1.5),
        (None, None),
    ],
)
def test_years_from_text(text, expected):
    assert years_from_text(text) == expected


def test_locations_from_location_and_work_location_headings():
    names = [loc.locality for loc in locations_from_record(RECORD)]
    assert names == ["Hà Nội", "Hồ Chí Minh"]


def test_record_to_posting_and_row():
    posting = record_to_posting(RECORD, "topcv", NOW)
    assert posting.source_job_id == "2169805"
    assert posting.title == "Tester (Manual/Automation) – Thu Nhập 18-24 Triệu"
    assert "hr@tt.vn" not in posting.description_text
    assert posting.json_ld == RECORD
    row = build_job_row(posting, default_index(), {}, NOW.date())
    assert set(row.province_codes) == {1, 79}
    assert row.columns["salary_min_vnd"] == 18_000_000
    assert row.columns["salary_max_vnd"] == 24_000_000
    assert row.columns["years_exp_min"] == 2.0
    assert row.columns["posted_at"].isoformat() == "2026-11-05"


def test_negotiable_salary():
    posting = record_to_posting({**RECORD, "salary": "Thoả thuận"}, "topcv", NOW)
    row = build_job_row(posting, default_index(), {}, NOW.date())
    assert row.columns["salary_status"] == "negotiable"
    assert row.columns["salary_is_negotiable"] is True


@pytest.mark.parametrize(
    "bad",
    [{"details_status": "error"}, {"job_url": None}, {"title": "  "}],
)
def test_invalid_records_skipped(bad):
    assert record_to_posting({**RECORD, **bad}, "topcv", NOW) is None


def test_load_file_dry_run(tmp_path):
    path = tmp_path / "topcv.jsonl"
    other = {**RECORD, "job_url": RECORD["job_url"].replace("2169805", "2169806")}
    lines = [RECORD, other, {**RECORD, "details_status": "error"}]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in lines) + "\n\n")
    store = LocalStore(default_index(), out_dir=tmp_path / "out")
    stats = load_file(path, store, "topcv")
    assert stats.items_new == 2
    assert stats.skipped == {"invalid": 1}


VNW = {
    "jd_id": "vietnamworks_2102766",
    "source": "vietnamworks",
    "source_job_id": "2102766",
    "title": "Tech Lead Java Developer",
    "company": "FPT Software",
    "description": "ABOUT FPT SOFTWARE\nJava, Spring Boot",
    "location": "Hà Nội, Hải Phòng",
    "locations": ["Hà Nội", "Hải Phòng"],
    "source_url": "https://www.vietnamworks.com/tech-lead-java-developer-2102766-jv",
    "salary": None,
    "skills": ["Java", "Spring Boot"],
    "posted_at": "2026-10-13T10:22:19+07:00",
    "expired_on": "2026-11-12T23:59:59+07:00",
}


def test_vietnamworks_clean_format():
    posting = record_to_posting(VNW, "vietnamworks", NOW)
    assert posting.source_job_id == "2102766"
    assert posting.url.endswith("-2102766-jv")
    assert posting.date_posted.isoformat() == "2026-10-13"
    assert posting.valid_through.isoformat() == "2026-11-12"
    assert posting.skills_text == "Java, Spring Boot"
    row = build_job_row(posting, default_index(), {}, NOW.date())
    assert set(row.province_codes) == {1, 31}
    assert row.columns["status"] == "open"
    assert row.columns["salary_status"] == "missing"


def test_topcv_job_id_field_and_ward_location():
    record = {**RECORD, "job_id": "1032919", "location": "Phường Từ Liêm, Hà Nội"}
    record.pop("work_location")
    posting = record_to_posting(record, "topcv", NOW)
    assert posting.source_job_id == "1032919"
    row = build_job_row(posting, default_index(), {}, NOW.date())
    assert row.province_codes == (1,)
