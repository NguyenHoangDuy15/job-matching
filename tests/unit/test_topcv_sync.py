import json

import pytest

from ingestion import topcv
from ingestion.store import RunStats
from ingestion.topcv_sync import TopCVSyncError, pending_job_ids, sync_pending


def parsed_detail(title="Tester"):
    text = "Nội dung hợp lệ " * 40
    return {
        "title": title,
        "company_name": "ACME",
        "job_description": text,
        "requirements": "Yêu cầu " + text,
        "benefits": "Quyền lợi " + text,
        "skills": ["Python"],
    }


def listing(job_id):
    return {
        "job_id": str(job_id),
        "url": f"https://www.topcv.vn/viec-lam/tester/{job_id}.html",
        "title": f"Tester {job_id}",
        "company_name": "ACME",
        "salary_preview": "",
        "location_preview": "Hà Nội",
        "experience_preview": "2 năm",
        "posted_at": "",
        "status": "PENDING",
    }


class FakeStore:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.saved = []
        self.finished = []
        self.run_types = []

    def start_run(self, source, source_id, run_type):
        assert (source, source_id) == ("topcv", None)
        self.run_types.append(run_type)
        return 42

    def save(self, posting, key, run_id):
        assert key is None and run_id == 42
        if self.fail:
            raise RuntimeError("database unavailable")
        self.saved.append(posting.source_job_id)
        return "new"

    def finish_run(self, run_id, stats: RunStats, status, error):
        self.finished.append((run_id, stats.items_seen, status, error))


def make_checkpoint(tmp_path, count=2):
    db = tmp_path / "topcv.db"
    out = tmp_path / "topcv.jsonl"
    conn = topcv.initialize_db(db)
    jobs = [listing(100 + index) for index in range(count)]
    topcv.store_listing(conn, jobs)
    for job in jobs:
        topcv.save_job_detail(conn, job["job_id"], parsed_detail(job["title"]))
    topcv.export_jsonl(conn, out)
    return conn, out, jobs


def test_sync_only_sends_unsynced_rows_and_marks_after_success(tmp_path):
    conn, out, jobs = make_checkpoint(tmp_path)
    conn.execute("UPDATE job_details SET synced_to_pg=1 WHERE job_id=?", (jobs[0]["job_id"],))
    conn.commit()
    store = FakeStore()

    stats = sync_pending(conn, out, store)

    assert stats.items_seen == 1
    assert store.saved == [jobs[1]["job_id"]]
    assert store.run_types == ["manual"]
    assert pending_job_ids(conn) == []
    assert store.finished == [(42, 1, "success", None)]


def test_sync_failure_does_not_mark_row_as_synced(tmp_path):
    conn, out, _jobs = make_checkpoint(tmp_path, count=1)
    store = FakeStore(fail=True)

    with pytest.raises(RuntimeError, match="database unavailable"):
        sync_pending(conn, out, store, run_type="hourly")

    assert len(pending_job_ids(conn)) == 1
    assert store.run_types == ["hourly"]
    assert store.finished[0][2] == "failed"


def test_sync_refuses_jsonl_missing_a_pending_sqlite_row(tmp_path):
    conn, out, jobs = make_checkpoint(tmp_path, count=1)
    record = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    record["job_id"] = "999"
    out.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    store = FakeStore()

    with pytest.raises(TopCVSyncError, match="JSONL thiếu"):
        sync_pending(conn, out, store)

    assert store.finished == []
    assert pending_job_ids(conn) == [jobs[0]["job_id"]]


def test_headless_flag_accepts_cli_and_environment(monkeypatch):
    assert topcv.arguments(["--headless"]).headless is True
    assert topcv.arguments(["--no-headless"]).headless is False
    monkeypatch.setenv("TOPCV_HEADLESS", "true")
    assert topcv.arguments([]).headless is True
