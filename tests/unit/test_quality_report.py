"""Báo cáo chất lượng mỗi lượt crawl (S4-T05) → ops.quality_reports."""

import logging
from contextlib import contextmanager
from datetime import UTC, date, datetime

import pytest

from ingestion.location import load_index_from_seed
from ingestion.models import JobPostingRaw, LocationRaw, SalaryRaw
from ingestion.quality import (
    MAX_SAMPLES,
    QualityCounter,
    build_report,
    freshness_hours,
    invalid_reasons,
    salary_parsed,
)
from ingestion.store import JobRow, LocalStore, PgStore, RunStats, build_job_row

INDEX = load_index_from_seed()
NOW = datetime(2026, 11, 23, 3, 0, tzinfo=UTC)  # 10h sáng 23/11 giờ Việt Nam


def posting(job_id: str = "1", **kw) -> JobPostingRaw:
    data = {
        "source": "topcv",
        "source_job_id": job_id,
        "url": f"https://example.com/{job_id}",
        "title": "Backend Developer",
        "company_name": "Công ty ABC",
        "description_text": "Phát triển API",
        "fetched_at": datetime(2026, 11, 22, tzinfo=UTC),
    } | kw
    return JobPostingRaw(**data)


def row_of(p: JobPostingRaw) -> JobRow:
    return build_job_row(p, INDEX, {}, date(2026, 11, 22))


def fake_row(**cols) -> JobRow:
    base = {"title": "Dev", "jd_text": "mô tả", "apply_url": "https://x/1"}
    return JobRow(columns=base | cols, company_name="ABC", province_codes=(1,), address_raw="Hà Nội")


def test_counts_complete_valid_salary_province():
    counter = QualityCounter()
    full = posting("1")
    full_row = fake_row(salary_min_vnd=10_000_000, salary_max_vnd=20_000_000)
    counter.add(full_row, full, "new")

    bare = posting("2", company_name=None, description_text="")
    bare_row = JobRow(
        columns={"title": "Dev", "apply_url": "https://x/2"},
        company_name=None,
        province_codes=(),
        address_raw="",
    )
    counter.add(bare_row, bare, "new")

    report = build_report(counter, RunStats(), NOW)
    assert report["completeness"] == 0.5
    assert report["validity"] == 1.0
    assert report["salary_parsed_pct"] == 0.5
    assert report["province_parsed_pct"] == 0.5
    assert report["details"]["missing"] == {"company": 1, "description": 1, "location": 1}


def test_invalid_reasons_and_samples():
    assert invalid_reasons({"title": "Dev", "salary_min_vnd": 30, "salary_max_vnd": 10}) == [
        "salary_min_gt_max"
    ]
    assert invalid_reasons({"title": "Dev", "salary_min_vnd": -1}) == ["salary_negative"]
    assert invalid_reasons(
        {"title": " ", "posted_at": date(2026, 11, 20), "valid_through": date(2026, 11, 1)}
    ) == ["title_empty", "valid_through_before_posted"]

    counter = QualityCounter()
    for i in range(MAX_SAMPLES + 3):
        counter.add(fake_row(salary_min_vnd=30, salary_max_vnd=10), posting(str(i)), "new")
    report = build_report(counter, RunStats(), NOW)
    assert report["validity"] == 0.0
    assert report["details"]["invalid"] == {"salary_min_gt_max": MAX_SAMPLES + 3}
    assert len(report["details"]["invalid_samples"]) == MAX_SAMPLES
    assert report["details"]["invalid_samples"][0] == {
        "source_job_id": "0",
        "reason": "salary_min_gt_max",
    }


def test_salary_parsed_negotiable_and_status():
    assert salary_parsed({"salary_is_negotiable": True})
    assert salary_parsed({"salary_max_vnd": 0})
    assert salary_parsed({"salary_status": "parsed"})
    assert not salary_parsed({"salary_status": "unparsed"})


def test_duplicates_lower_uniqueness():
    counter = QualityCounter()
    counter.add(fake_row(), posting("1"), "new")
    counter.add(fake_row(), posting("2"), "duplicate")
    counter.add(fake_row(), posting("3"), "unchanged")
    counter.add(fake_row(), posting("4"), "duplicate")
    report = build_report(counter, RunStats(), NOW)
    assert report["uniqueness"] == 0.5
    assert report["details"]["duplicates"] == 2


def test_unmatched_locations_collected_once():
    counter = QualityCounter()
    row = JobRow(
        columns={"title": "Dev"}, company_name="A", province_codes=(), address_raw="Sao Hỏa"
    )
    counter.add(row, posting("1"), "new")
    counter.add(row, posting("2"), "new")
    assert counter.unmatched_locations == ["Sao Hỏa"]


def test_freshness_from_vn_midnight():
    # 0h 22/11 giờ VN = 17h 21/11 UTC → tới 3h UTC 23/11 là 34 giờ
    assert freshness_hours(date(2026, 11, 22), NOW) == 34.0
    assert freshness_hours(date(2026, 11, 22), NOW.replace(tzinfo=None)) == 34.0  # naive = UTC
    assert freshness_hours(date(2026, 11, 30), NOW) == 0.0  # ngày đăng ở tương lai
    assert freshness_hours(None, NOW) is None


def test_newest_posted_uses_vn_date():
    counter = QualityCounter()
    # 18h UTC 21/11 = 1h sáng 22/11 giờ VN
    counter.add(fake_row(posted_at=datetime(2026, 11, 21, 18, tzinfo=UTC)), posting("1"), "new")
    counter.add(fake_row(posted_at=date(2026, 11, 20)), posting("2"), "new")
    assert counter.newest_posted == date(2026, 11, 22)
    assert build_report(counter, RunStats(), NOW)["details"]["newest_posted"] == "2026-11-22"


def test_empty_run_has_no_ratios_and_counts_schema_errors():
    stats = RunStats()
    stats.skip("no_title")
    stats.skip("no_title")
    stats.skip("bad_json")
    report = build_report(QualityCounter(), stats, NOW)
    for key in ("completeness", "validity", "uniqueness", "salary_parsed_pct", "province_parsed_pct"):
        assert report[key] is None
    assert report["freshness_hours"] is None
    assert report["schema_errors"] == 3
    assert report["details"]["skipped"] == {"bad_json": 1, "no_title": 2}


def test_build_job_row_feeds_counter():
    p = posting(
        "1",
        locations=[LocationRaw(region="Hà Nội", country="VN")],
        salary=SalaryRaw(
            currency="VND",
            min_value=15_000_000,
            max_value=20_000_000,
            unit="MONTH",
            text="15 - 20 triệu",
        ),
        date_posted=date(2026, 11, 22),
    )
    counter = QualityCounter()
    counter.add(row_of(p), p, "new")
    report = build_report(counter, RunStats(), NOW)
    assert report["completeness"] == 1.0
    assert report["province_parsed_pct"] == 1.0
    assert report["salary_parsed_pct"] == 1.0
    assert report["freshness_hours"] == 34.0


def test_local_store_logs_report(tmp_path, caplog):
    store = LocalStore(INDEX, tmp_path)
    p = posting("1")
    assert store.save(p, "k", None) == "new"
    assert store.save(p, "k", None) == "unchanged"
    with caplog.at_level(logging.INFO, logger="ingestion.quality"):
        store.finish_run(None, RunStats(), "success", None)
    assert store.quality.total == 2
    assert any('"items": 2' in r.getMessage() for r in caplog.records)


class FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


def test_pg_store_writes_quality_report():
    pytest.importorskip("psycopg")
    store = object.__new__(PgStore)
    store.conn = FakeConn()
    store.quality = QualityCounter()
    store.quality.add(fake_row(salary_is_negotiable=True), posting("1"), "new")
    stats = RunStats()
    stats.skip("no_title")

    store.finish_run(42, stats, "success", None)

    assert len(store.conn.calls) == 2
    assert "ops.crawl_runs" in store.conn.calls[0][0]
    sql, params = store.conn.calls[1]
    assert "ops.quality_reports" in sql
    assert params[0] == 42
    assert params[1:7] == (1.0, 1.0, 1.0, 1.0, 1.0, 1)
    assert params[-1].obj["items"] == 1
    assert params[-1].obj["skipped"] == {"no_title": 1}
