import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

import ingestion.topcv as topcv

JOB_URL = "https://www.topcv.vn/viec-lam/tester/111.html"
VALID_HTML = r"""
<html><head><title>Senior Tester</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Senior Tester",
 "hiringOrganization":{"name":"ACME"},
 "description":"Mô tả công việc\nPhát triển và kiểm thử hệ thống phần mềm nội bộ quan trọng.",
 "qualifications":"Có kinh nghiệm kiểm thử, Python và viết tài liệu kỹ thuật.",
 "jobBenefits":"Lương thưởng cạnh tranh, bảo hiểm đầy đủ và làm việc linh hoạt."}
</script></head><body>
<div class="job-description__item"><h3>Mô tả công việc</h3>
  <div class="job-description__item--content">DOM không được ghi đè JSON-LD.</div></div>
</body></html>
"""


def open_db(tmp_path, name="jobs.db"):
    return topcv.initialize_db(tmp_path / name)


def listing(job_id, *, status="PENDING", title="Tester"):
    return {
        "job_id": str(job_id),
        "url": f"https://www.topcv.vn/viec-lam/tester/{job_id}.html",
        "title": title,
        "company_name": "ACME",
        "salary_preview": "",
        "location_preview": "Hà Nội",
        "experience_preview": "2 năm",
        "posted_at": "",
        "status": status,
    }


def add_jobs(conn, count, start=1):
    jobs = [listing(job_id) for job_id in range(start, start + count)]
    assert topcv.store_listing(conn, jobs) == count
    return jobs


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def fetch(self, url, is_listing=False):
        self.calls.append((url, is_listing))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


def test_t01_completed_rows_survive_upsert_and_changed_row_needs_sync(tmp_path):
    conn = open_db(tmp_path)
    jobs = add_jobs(conn, 10, 100)
    parsed = topcv.parse_jd_html(VALID_HTML)
    for job in jobs:
        topcv.save_job_detail(conn, job["job_id"], parsed)
    conn.execute("UPDATE job_details SET synced_to_pg=1")
    conn.commit()
    topcv.save_job_detail(conn, jobs[0]["job_id"], parsed)
    assert conn.execute("SELECT COUNT(*) FROM job_details").fetchone()[0] == 10
    assert conn.execute("SELECT SUM(synced_to_pg) FROM job_details").fetchone()[0] == 9
    assert (
        conn.execute("SELECT COUNT(*) FROM job_queue WHERE status='COMPLETED'").fetchone()[0] == 10
    )
    conn.close()


def test_t02_http_429_stops_before_next_job_and_blocks_source(tmp_path):
    conn = open_db(tmp_path)
    add_jobs(conn, 3, 201)
    limited = topcv.RateLimited(
        "HTTP 429",
        status=429,
        url="https://www.topcv.vn/viec-lam/tester/202.html",
        retry_after_raw="120",
        retry_after_at="2030-01-01T00:02:00+00:00",
    )
    client = FakeClient([VALID_HTML, limited, VALID_HTML])
    with pytest.raises(topcv.RateLimited):
        asyncio.run(topcv.crawl_details(conn, client, 3))
    assert len(client.calls) == 2
    states = dict(conn.execute("SELECT job_id,status FROM job_queue"))
    assert states == {"201": "COMPLETED", "202": "BLOCKED", "203": "PENDING"}
    source = topcv.get_source_state(conn)
    assert source["status"] == "BLOCKED"
    assert source["last_http_status"] == 429
    assert source["retry_after_raw"] == "120"
    conn.close()


def test_interrupted_run_reports_successes_saved_before_http_429(tmp_path, monkeypatch, capsys):
    db = tmp_path / "jobs.db"
    conn = topcv.initialize_db(db)
    jobs = add_jobs(conn, 2, 251)
    conn.close()
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n  - name: topcv\n    allowed: true\n    rate_limit_s: 1\n", encoding="utf-8"
    )

    class Browser:
        def __init__(self, *_args, **_kwargs):
            self.calls = 0

        async def start(self):
            pass

        async def fetch(self, _url, is_listing=False):
            assert not is_listing
            self.calls += 1
            if self.calls == 1:
                return VALID_HTML
            raise topcv.RateLimited("HTTP 429", status=429, url=jobs[1]["url"])

        async def close(self):
            pass

    monkeypatch.setattr(topcv, "NodriverBrowser", Browser)
    args = topcv.arguments(
        [
            "--details-only",
            "--limit",
            "2",
            "--db",
            str(db),
            "--out",
            str(tmp_path / "topcv_nodriver.jsonl"),
            "--sources-config",
            str(config),
        ]
    )

    assert asyncio.run(topcv.run(args)) == 2
    assert "JD mới thành công=1" in capsys.readouterr().out


def test_t03_http_403_stops_without_retry_or_deleting_completed(tmp_path):
    conn = open_db(tmp_path)
    jobs = add_jobs(conn, 2, 301)
    topcv.save_job_detail(conn, jobs[0]["job_id"], topcv.parse_jd_html(VALID_HTML))
    client = FakeClient(
        [
            topcv.AccessRestricted("HTTP 403", status=403, url=jobs[1]["url"]),
            VALID_HTML,
        ]
    )
    with pytest.raises(topcv.AccessRestricted):
        asyncio.run(topcv.crawl_details(conn, client, 2))
    assert len(client.calls) == 1
    assert (
        conn.execute("SELECT status FROM job_queue WHERE job_id='301'").fetchone()[0] == "COMPLETED"
    )
    assert conn.execute("SELECT COUNT(*) FROM job_details WHERE job_id='301'").fetchone()[0] == 1
    assert (
        conn.execute("SELECT status FROM job_queue WHERE job_id='302'").fetchone()[0] == "BLOCKED"
    )
    conn.close()


def test_t04_retry_after_supports_seconds_and_http_date():
    now = datetime(2030, 1, 1, tzinfo=UTC)
    assert topcv.parse_retry_after("120", now) == "2030-01-01T00:02:00+00:00"
    assert (
        topcv.parse_retry_after("Tue, 01 Jan 2030 00:03:00 GMT", now) == "2030-01-01T00:03:00+00:00"
    )
    assert topcv.parse_retry_after("unknown", now) is None


def test_main_document_status_ignores_unrelated_document_429(tmp_path):
    browser = topcv.NodriverBrowser(tmp_path / "profile", None, 0)
    browser._document_statuses = [
        {"url": "https://www.topcv.vn/iframe", "status": 429, "retry_after_raw": "10"},
        {"url": JOB_URL, "status": 200, "retry_after_raw": None},
    ]
    browser._check_document_status(JOB_URL)


def test_t05_transient_cdp_error_retries_snapshot_without_navigation(tmp_path, monkeypatch):
    class Tab:
        calls = 0

        async def evaluate(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("ProtocolException -32000: Could not find node with given id")
            return "ok"

    browser = topcv.NodriverBrowser(tmp_path / "profile", None, 0)
    browser.tab = Tab()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(topcv.asyncio, "sleep", no_sleep)
    assert asyncio.run(browser._evaluate_snapshot("1")) == "ok"
    assert browser.tab.calls == 2


def test_t06_persistent_browser_error_marks_only_current_retry_pending(tmp_path):
    conn = open_db(tmp_path)
    add_jobs(conn, 3, 401)
    client = FakeClient([topcv.BrowserReadError("browser dead"), VALID_HTML])
    with pytest.raises(topcv.BrowserReadError):
        asyncio.run(topcv.crawl_details(conn, client, 3))
    states = dict(conn.execute("SELECT job_id,status FROM job_queue"))
    assert states == {"401": "RETRY_PENDING", "402": "PENDING", "403": "PENDING"}
    assert len(client.calls) == 1
    conn.close()


@pytest.mark.parametrize(
    "readiness",
    [
        json.dumps({"ready": "complete", "found": True, "challenge": False}),
        {"ready": "complete", "found": True, "challenge": False},
    ],
)
def test_t07_fetch_accepts_json_string_or_dict_readiness(tmp_path, readiness):
    class Tab:
        async def get(self, _url):
            return self

        async def evaluate(self, script, **_kwargs):
            return VALID_HTML if "outerHTML" in script else readiness

    browser = topcv.NodriverBrowser(tmp_path / "profile", None, 0)
    browser.tab = Tab()
    browser.driver = object()
    assert asyncio.run(browser.fetch(JOB_URL)) == VALID_HTML


def test_t08_jsonld_is_preferred_and_valid_detail_completes(tmp_path):
    parsed = topcv.parse_jd_html(VALID_HTML)
    assert "Phát triển và kiểm thử" in parsed["job_description"]
    assert "DOM không được ghi đè" not in parsed["job_description"]
    assert parsed["requirements"] and parsed["benefits"]
    conn = open_db(tmp_path)
    topcv.store_listing(conn, [listing(111)])
    topcv.save_job_detail(conn, "111", parsed)
    assert conn.execute("SELECT status FROM job_queue").fetchone()[0] == "COMPLETED"
    conn.close()


@pytest.mark.parametrize(
    "html",
    [
        "",
        "<html><body>menu việc làm tương tự</body></html>",
        "<html><title>Just a moment...</title><div id='challenge-form'></div></html>",
    ],
)
def test_t09_empty_menu_or_challenge_is_not_valid_jd(html):
    assert not topcv.is_valid_jd(topcv.parse_jd_html(html))
    if "challenge" in html:
        assert topcv.page_is_challenge(html)


def test_t10_listing_deduplicates_without_resetting_status(tmp_path):
    conn = open_db(tmp_path)
    job = listing(501)
    assert topcv.store_listing(conn, [job]) == 1
    topcv.set_status(conn, "501", "BLOCKED", "old")
    changed = {**job, "title": "New title"}
    assert topcv.store_listing(conn, [changed, changed]) == 0
    row = conn.execute("SELECT status,title,COUNT(*) OVER () FROM job_queue").fetchone()
    assert tuple(row) == ("BLOCKED", "New title", 1)
    conn.close()


def test_t11_crash_processing_recovery_is_controlled(tmp_path):
    conn = open_db(tmp_path)
    add_jobs(conn, 2, 601)
    topcv.set_status(conn, "601", "PROCESSING")
    topcv.save_job_detail(conn, "602", topcv.parse_jd_html(VALID_HTML))
    assert topcv.recover_processing(conn) == 1
    assert topcv.recover_processing(conn) == 0
    assert (
        conn.execute("SELECT status FROM job_queue WHERE job_id='601'").fetchone()[0]
        == "RETRY_PENDING"
    )
    assert (
        conn.execute("SELECT status FROM job_queue WHERE job_id='602'").fetchone()[0] == "COMPLETED"
    )
    conn.close()


def test_t12_old_schema_migration_is_idempotent(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE job_queue (job_id TEXT PRIMARY KEY,url TEXT NOT NULL,status TEXT)")
    conn.execute("CREATE TABLE job_details (job_id TEXT PRIMARY KEY,title TEXT)")
    conn.commit()
    conn.close()
    topcv.initialize_db(path).close()
    conn = topcv.initialize_db(path)
    queue_columns = {row[1] for row in conn.execute("PRAGMA table_info(job_queue)")}
    assert {
        "attempt_count",
        "last_error_kind",
        "last_http_status",
        "last_attempt_at",
        "updated_at",
    } <= queue_columns
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='source_state'").fetchone()
    conn.close()


def test_legacy_http_429_backfills_source_block_once(tmp_path):
    conn = open_db(tmp_path)
    topcv.store_listing(conn, [listing(650)])
    topcv.set_status(conn, "650", "BLOCKED", "HTTP 429: rate limited")
    assert topcv.migrate_legacy_source_block(conn) == 1
    assert topcv.migrate_legacy_source_block(conn) == 0
    state = topcv.get_source_state(conn)
    assert state["status"] == "BLOCKED"
    assert state["last_http_status"] == 429
    conn.close()


def test_t13_export_failure_keeps_existing_jsonl_bytes(tmp_path, monkeypatch):
    conn = open_db(tmp_path)
    topcv.store_listing(conn, [listing(701)])
    topcv.save_job_detail(conn, "701", topcv.parse_jd_html(VALID_HTML))
    output = tmp_path / "topcv_nodriver.jsonl"
    original = (json.dumps({"job_id": "701"}) + "\n").encode()
    output.write_bytes(original)

    def fail_replace(*_args):
        raise OSError("disk failure")

    monkeypatch.setattr(topcv.os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk failure"):
        topcv.export_jsonl(conn, output)
    assert output.read_bytes() == original
    assert not (tmp_path / "topcv_nodriver.jsonl.tmp").exists()
    conn.close()


def test_export_refuses_unexpected_reduction(tmp_path):
    conn = open_db(tmp_path)
    topcv.store_listing(conn, [listing(801)])
    topcv.save_job_detail(conn, "801", topcv.parse_jd_html(VALID_HTML))
    output = tmp_path / "topcv_nodriver.jsonl"
    original = b'{"job_id":"801"}\n{"job_id":"802"}\n'
    output.write_bytes(original)
    with pytest.raises(topcv.ExportSafetyError, match="ít hơn|thiếu"):
        topcv.export_jsonl(conn, output)
    assert output.read_bytes() == original
    conn.close()


def test_t14_details_limit_caps_jobs_and_skips_completed_blocked(tmp_path):
    conn = open_db(tmp_path)
    jobs = add_jobs(conn, 13, 901)
    topcv.save_job_detail(conn, jobs[0]["job_id"], topcv.parse_jd_html(VALID_HTML))
    topcv.set_status(conn, jobs[1]["job_id"], "BLOCKED", "blocked")
    client = FakeClient([VALID_HTML] * 20)
    assert asyncio.run(topcv.crawl_details(conn, client, 10)) == 10
    assert len(client.calls) == 10
    assert (
        conn.execute("SELECT COUNT(*) FROM job_queue WHERE status='COMPLETED'").fetchone()[0] == 11
    )
    assert conn.execute("SELECT COUNT(*) FROM job_queue WHERE status='BLOCKED'").fetchone()[0] == 1
    conn.close()


def test_t15_manual_import_is_offline_and_exports(tmp_path, monkeypatch):
    html = tmp_path / "saved.html"
    html.write_text(VALID_HTML, encoding="utf-8")
    db = tmp_path / "jobs.db"
    output = tmp_path / "topcv_nodriver.jsonl"

    async def must_not_start(_self):
        raise AssertionError("offline import must not open browser")

    monkeypatch.setattr(topcv.NodriverBrowser, "start", must_not_start)
    args = topcv.arguments(
        [
            "--import-html",
            str(html),
            "--job-url",
            JOB_URL,
            "--db",
            str(db),
            "--out",
            str(output),
        ]
    )
    assert asyncio.run(topcv.run(args)) == 0
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["job_id"] == "111"
    assert record["description"]


def test_nodriver_close_awaits_process_and_closes_windows_transport(tmp_path):
    class Transport:
        closed = False

        def close(self):
            self.closed = True

    class Process:
        def __init__(self):
            self.returncode = None
            self.waits = 0
            self.terminated = False
            self.communicated = False
            self._transport = Transport()

        async def wait(self):
            self.waits += 1
            if self.waits == 1:
                raise TimeoutError
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = 0

        def kill(self):
            raise AssertionError("terminate should be sufficient")

        async def communicate(self):
            self.communicated = True
            return b"", b""

    class Driver:
        def __init__(self):
            self._process = Process()
            self._process_pid = 123
            self.closed = False

        async def send(self, _command):
            raise ConnectionError("Chrome closed before CDP response")

        async def aclose(self):
            self.closed = True

        def stop(self):
            raise AssertionError("Nodriver stop() must not be used on Windows cleanup")

    class BrowserCommands:
        @staticmethod
        def close():
            return object()

    class Cdp:
        browser = BrowserCommands()

    class Uc:
        cdp = Cdp()

    browser = topcv.NodriverBrowser(tmp_path / "profile", None, 0)
    driver = Driver()
    process = driver._process
    browser.driver = driver
    browser.tab = object()
    browser.uc = Uc()

    asyncio.run(browser.close())

    assert driver.closed
    assert process.terminated
    assert process.waits == 2
    assert process.communicated
    assert process._transport.closed
    assert driver._process is None
    assert browser.driver is None
    assert browser.tab is None


def test_t16_close_error_still_closes_db_and_returns_error(tmp_path, monkeypatch):
    class Browser:
        def __init__(self, *_args, **_kwargs):
            pass

        async def start(self):
            pass

        async def close(self):
            raise OSError("close pipe")

    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n  - name: topcv\n    allowed: true\n    rate_limit_s: 1\n", encoding="utf-8"
    )
    monkeypatch.setattr(topcv, "NodriverBrowser", Browser)
    args = topcv.arguments(
        [
            "--details-only",
            "--db",
            str(tmp_path / "jobs.db"),
            "--out",
            str(tmp_path / "out.jsonl"),
            "--sources-config",
            str(config),
        ]
    )
    assert asyncio.run(topcv.run(args)) == 1
    conn = sqlite3.connect(tmp_path / "jobs.db")
    conn.execute("SELECT 1").fetchone()
    conn.close()


def test_blocked_source_does_not_start_browser_or_auto_reopen_jobs(tmp_path, monkeypatch):
    db = tmp_path / "jobs.db"
    conn = topcv.initialize_db(db)
    topcv.store_listing(conn, [listing(1001)])
    topcv.set_status(conn, "1001", "BLOCKED", "HTTP 403", http_status=403)
    topcv.record_source_block(
        conn, topcv.AccessRestricted("HTTP 403", status=403, url=listing(1001)["url"])
    )
    conn.close()
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n  - name: topcv\n    allowed: true\n    rate_limit_s: 1\n", encoding="utf-8"
    )

    async def must_not_start(_self):
        raise AssertionError("blocked source must not start browser")

    monkeypatch.setattr(topcv.NodriverBrowser, "start", must_not_start)
    args = topcv.arguments(
        [
            "--details-only",
            "--db",
            str(db),
            "--out",
            str(tmp_path / "out.jsonl"),
            "--sources-config",
            str(config),
        ]
    )
    assert asyncio.run(topcv.run(args)) == 2
    conn = sqlite3.connect(db)
    assert (
        conn.execute("SELECT status FROM job_queue WHERE job_id='1001'").fetchone()[0] == "BLOCKED"
    )
    conn.close()


def test_help_preserves_old_options_and_lists_offline_modes(capsys):
    with pytest.raises(SystemExit) as error:
        topcv.arguments(["--help"])
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    for option in (
        "--pages",
        "--start-page",
        "--limit",
        "--target-total",
        "--details-only",
        "--no-details",
        "--reset-dom-failures",
        "--import-html",
        "--import-listing-csv",
        "--job-url",
        "--db",
        "--out",
        "--delay",
        "--report-only",
        "--export-only",
    ):
        assert option in help_text


def test_target_total_already_reached_skips_policy_and_browser(tmp_path, monkeypatch, capsys):
    db = tmp_path / "jobs.db"
    conn = topcv.initialize_db(db)
    topcv.store_listing(conn, [listing(1101)])
    topcv.save_job_detail(conn, "1101", topcv.parse_jd_html(VALID_HTML))
    conn.close()

    async def must_not_start(_self):
        raise AssertionError("target already reached must not start browser")

    monkeypatch.setattr(topcv.NodriverBrowser, "start", must_not_start)
    output = tmp_path / "out.jsonl"
    args = topcv.arguments(
        [
            "--details-only",
            "--target-total",
            "1",
            "--db",
            str(db),
            "--out",
            str(output),
            "--sources-config",
            str(tmp_path / "missing.yaml"),
        ]
    )

    assert asyncio.run(topcv.run(args)) == 0
    assert "[TARGET]" in capsys.readouterr().out
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


def test_target_total_caps_detail_requests_without_overshooting(tmp_path, monkeypatch):
    db = tmp_path / "jobs.db"
    conn = topcv.initialize_db(db)
    jobs = add_jobs(conn, 3, 1201)
    topcv.save_job_detail(conn, jobs[0]["job_id"], topcv.parse_jd_html(VALID_HTML))
    conn.close()
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n  - name: topcv\n    allowed: true\n    rate_limit_s: 1\n", encoding="utf-8"
    )

    class Browser:
        calls = 0

        def __init__(self, *_args, **_kwargs):
            pass

        async def start(self):
            pass

        async def fetch(self, _url, is_listing=False):
            assert not is_listing
            type(self).calls += 1
            return VALID_HTML

        async def close(self):
            pass

    monkeypatch.setattr(topcv, "NodriverBrowser", Browser)
    args = topcv.arguments(
        [
            "--details-only",
            "--limit",
            "10",
            "--target-total",
            "2",
            "--db",
            str(db),
            "--out",
            str(tmp_path / "out.jsonl"),
            "--sources-config",
            str(config),
        ]
    )

    assert asyncio.run(topcv.run(args)) == 0
    assert Browser.calls == 1
    conn = sqlite3.connect(db)
    states = dict(conn.execute("SELECT status, COUNT(*) FROM job_queue GROUP BY status"))
    conn.close()
    assert states == {"COMPLETED": 2, "PENDING": 1}


def test_import_listing_csv_is_offline_and_preserves_existing_status(tmp_path, monkeypatch):
    db = tmp_path / "jobs.db"
    conn = topcv.initialize_db(db)
    topcv.store_listing(conn, [listing(1301)])
    topcv.save_job_detail(conn, "1301", topcv.parse_jd_html(VALID_HTML))
    conn.close()
    csv_file = tmp_path / "jobs.csv"
    csv_file.write_text(
        "title,company,location,experience,salary,date_posted,url\n"
        "Existing,Updated company,Hà Nội,3 năm,20 triệu,2026-11-01,"
        "https://www.topcv.vn/viec-lam/tester/1301.html?tracking=1\n"
        "New job,New company,Đà Nẵng,1 năm,Thoả thuận,2026-11-02,"
        "https://www.topcv.vn/viec-lam/new-job/1302.html?tracking=2\n",
        encoding="utf-8-sig",
    )

    async def must_not_start(_self):
        raise AssertionError("CSV queue import must not start browser")

    monkeypatch.setattr(topcv.NodriverBrowser, "start", must_not_start)
    output = tmp_path / "out.jsonl"
    args = topcv.arguments(
        [
            "--import-listing-csv",
            str(csv_file),
            "--db",
            str(db),
            "--out",
            str(output),
            "--sources-config",
            str(tmp_path / "missing.yaml"),
        ]
    )

    assert asyncio.run(topcv.run(args)) == 0
    assert not output.exists()
    conn = sqlite3.connect(db)
    rows = dict(conn.execute("SELECT job_id,status FROM job_queue"))
    normalized = conn.execute("SELECT url FROM job_queue WHERE job_id='1302'").fetchone()[0]
    conn.close()
    assert rows == {"1301": "COMPLETED", "1302": "PENDING"}
    assert normalized == "https://www.topcv.vn/viec-lam/new-job/1302.html"


def test_csv_batch_details_prioritizes_newest_posted_date(tmp_path):
    conn = open_db(tmp_path)
    jobs = [
        {**listing(1401, title="Older"), "posted_at": "2026-01-01"},
        {**listing(1402, title="Newest"), "posted_at": "2026-11-01"},
    ]
    topcv.store_listing(conn, jobs)
    client = FakeClient([VALID_HTML])

    assert asyncio.run(topcv.crawl_details(conn, client, 1)) == 1
    completed = conn.execute("SELECT job_id FROM job_queue WHERE status='COMPLETED'").fetchone()[0]
    conn.close()
    assert completed == "1402"


def test_repository_topcv_policy_uses_cautious_30_second_minimum():
    assert topcv.source_policy(Path("config/sources.yaml")) >= 30


# --- Lỗi 105 tin 11/2026: tin bị gỡ chuyển hướng về /viec-lam, popup MoMo bị lưu làm JD ---
REMOVED_JOB_HOMEPAGE_HTML = """
<html><head><title>Tuyển dụng, tìm việc làm 24h</title></head><body>
<h1>Tìm việc làm nhanh, việc làm nổi bật trên toàn quốc</h1>
<div class="modal fade" id="modal-payment-momo" role="dialog"><div class="modal-body">
Quyền lợi ứng viên
Số tiền thanh toán
VNĐ
Giá trị đơn hàng đã bao gồm VAT
Thanh toán bằng ví điện tử MOMO
Tự động hết hạn sau: 9 s
Mã QR đã hết hạn
Hướng dẫn thanh toán: Mở ứng dụng ngân hàng hoặc ứng dụng MoMo trên điện thoại
</div></div>
<h2>Việc làm nổi bật</h2></body></html>
"""


def test_payment_popup_on_homepage_is_not_a_jd():
    parsed = topcv.parse_jd_html(REMOVED_JOB_HOMEPAGE_HTML)
    assert "Mã QR" not in parsed["benefits"]
    assert not topcv.is_valid_jd(parsed)


def test_popup_text_alone_is_rejected_even_if_parsed():
    text = "Số tiền thanh toán VNĐ\nThanh toán bằng ví điện tử MOMO\nMã QR đã hết hạn\n" * 3
    assert not topcv.is_valid_jd({"job_description": "", "requirements": "", "benefits": text})
    assert not topcv.is_valid_jd({"job_description": text, "requirements": "", "benefits": ""})


def test_benefits_only_is_not_a_jd():
    parsed = {"job_description": "", "requirements": "", "benefits": "Lương tháng 13. " * 10}
    assert not topcv.is_valid_jd(parsed)


def test_save_job_detail_refuses_removed_job_page(tmp_path):
    conn = open_db(tmp_path)
    topcv.store_listing(conn, [listing(1703730)])
    with pytest.raises(topcv.InvalidJobData):
        topcv.save_job_detail(conn, "1703730", topcv.parse_jd_html(REMOVED_JOB_HOMEPAGE_HTML))
    conn.close()


@pytest.mark.parametrize(
    ("final_url", "removed"),
    [
        ("https://www.topcv.vn/viec-lam", True),
        ("https://www.topcv.vn/", True),
        ("https://www.topcv.vn/viec-lam/tester/111.html", False),
        ("https://www.topcv.vn/viec-lam/khac/222.html", False),
        ("about:blank", False),
    ],
)
def test_redirected_off_job(final_url, removed):
    assert topcv.redirected_off_job(final_url) is removed


def test_fetch_raises_not_found_when_redirected_to_homepage(tmp_path):
    readiness = json.dumps(
        {
            "ready": "complete",
            "found": False,
            "challenge": False,
            "href": "https://www.topcv.vn/viec-lam",
        }
    )

    class Tab:
        async def get(self, _url):
            return self

        async def evaluate(self, script, **_kwargs):
            return REMOVED_JOB_HOMEPAGE_HTML if "outerHTML" in script else readiness

    browser = topcv.NodriverBrowser(tmp_path / "profile", None, 0)
    browser.tab = Tab()
    browser.driver = object()
    with pytest.raises(topcv.PageNotFound):
        asyncio.run(browser.fetch(JOB_URL))


def test_crawl_details_marks_removed_job_not_found_not_completed(tmp_path):
    conn = open_db(tmp_path)
    add_jobs(conn, 1, 901)
    client = FakeClient([topcv.PageNotFound("Tin đã bị gỡ: chuyển hướng tới /viec-lam")])
    assert asyncio.run(topcv.crawl_details(conn, client, 1)) == 0
    assert conn.execute("SELECT status FROM job_queue").fetchone()[0] == "NOT_FOUND"
    assert conn.execute("SELECT COUNT(*) FROM job_details").fetchone()[0] == 0
    conn.close()
