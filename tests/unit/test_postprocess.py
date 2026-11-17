"""Bước ③ gắn kỹ năng + ④ vector hóa chạy sau MỌI đường nạp tin, không riêng crawl.py.

Lỗi thật ngày 17/11/2026: tin TopCV vào DB qua topcv_sync không gắn kỹ năng → 516/1.441 tin
đang mở không có thẻ nào, web không hiện "Kỹ năng bắt buộc".
"""

import sqlite3

import pytest

from ingestion import jsonl_import, postprocess, topcv_sync


class FakeConn:
    def __init__(self, slugs=()):
        self.slugs = list(slugs)
        self.executed: list[str] = []
        self.commits = 0

    def execute(self, sql, *args):
        self.executed.append(sql)
        rows = [(s,) for s in self.slugs]

        class _R:
            def fetchall(self_inner):
                return rows

        return _R()

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_post_steps_run_skills_before_vectors(monkeypatch):
    """Thẻ kỹ năng nằm trong đoạn tóm tắt để vector hóa, nên ③ phải chạy trước ④."""
    calls = []
    monkeypatch.setattr(postprocess, "label_skills", lambda s: calls.append("skills") or True)
    monkeypatch.setattr(postprocess, "embed", lambda s: calls.append("embed") or True)
    assert postprocess.run_post_steps(object()) is True
    assert calls == ["skills", "embed"]


def test_post_steps_report_failure_but_still_try_vectors(monkeypatch):
    calls = []
    monkeypatch.setattr(postprocess, "label_skills", lambda s: (calls.append("skills"), False)[1])
    monkeypatch.setattr(postprocess, "embed", lambda s: calls.append("embed") or True)
    assert postprocess.run_post_steps(object()) is False
    assert calls == ["skills", "embed"]


def test_post_steps_can_be_skipped(monkeypatch):
    monkeypatch.setattr(postprocess, "label_skills", lambda s: pytest.fail("không được gắn"))
    monkeypatch.setattr(postprocess, "embed", lambda s: pytest.fail("không được vector hóa"))
    assert postprocess.run_post_steps(object(), skills=False, vectors=False) is True


def test_seed_reloaded_when_dictionary_has_new_skill(tmp_path):
    want = postprocess.yaml_skill_slugs()
    seed = tmp_path / "seed.sql"
    seed.write_text("-- seed\nselect 1;")
    conn = FakeConn(sorted(want)[1:])  # DB thiếu đúng 1 kỹ năng
    assert postprocess.sync_skill_seed(conn, seed_path=seed) == 1
    assert conn.executed[-1].startswith("-- seed") and conn.commits == 1


def test_seed_not_touched_when_db_matches_dictionary(tmp_path):
    conn = FakeConn(sorted(postprocess.yaml_skill_slugs()))
    assert postprocess.sync_skill_seed(conn, seed_path=tmp_path / "khong_can.sql") == 0
    assert len(conn.executed) == 1 and conn.commits == 0


def test_seed_file_matches_dictionary_used_for_sync():
    """Seed trong repo phải chứa đúng các kỹ năng sync_skill_seed so với DB."""
    sql = postprocess.SKILLS_SEED.read_text(encoding="utf-8")
    missing = [s for s in postprocess.yaml_skill_slugs() if f"('{s}'," not in sql]
    assert missing == []


class FakeStore:
    def __init__(self, dsn=None):
        self.conn = None
        self.changed_job_ids = []
        self.closed = False

    def close(self):
        self.closed = True


def _topcv_checkpoint(tmp_path):
    db = tmp_path / "topcv.db"
    with sqlite3.connect(db) as conn:
        conn.execute("create table job_queue (job_id text, status text)")
        conn.execute("create table job_details (job_id text, synced_to_pg int)")
        conn.execute("insert into job_queue values ('1', 'COMPLETED')")
        conn.execute("insert into job_details values ('1', 0)")
    jsonl = tmp_path / "topcv.jsonl"
    jsonl.write_text("")
    return db, jsonl


@pytest.mark.parametrize(
    ("flags", "expected"),
    [([], (True, True)), (["--skip-skills"], (False, True)), (["--skip-embed"], (True, False))],
)
def test_topcv_sync_runs_post_steps(tmp_path, monkeypatch, flags, expected):
    db, jsonl = _topcv_checkpoint(tmp_path)
    seen = {}
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setattr(topcv_sync, "PgStore", FakeStore)
    monkeypatch.setattr(topcv_sync, "sync_pending", lambda *a, **k: None)
    monkeypatch.setattr(
        postprocess,
        "run_post_steps",
        lambda store, skills, vectors: seen.update(args=(skills, vectors)) or True,
    )
    assert topcv_sync.main(["--db", str(db), "--jsonl", str(jsonl), *flags]) == 0
    assert seen["args"] == expected


def test_topcv_sync_fails_when_post_steps_fail(tmp_path, monkeypatch):
    db, jsonl = _topcv_checkpoint(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setattr(topcv_sync, "PgStore", FakeStore)
    monkeypatch.setattr(topcv_sync, "sync_pending", lambda *a, **k: None)
    monkeypatch.setattr(postprocess, "run_post_steps", lambda store, **k: False)
    assert topcv_sync.main(["--db", str(db), "--jsonl", str(jsonl)]) == 1


def test_jsonl_import_runs_post_steps(tmp_path, monkeypatch):
    seen = []
    stats = jsonl_import.RunStats()
    stats.items_seen = 1
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    class Pg(FakeStore):
        salary_v2 = True

    monkeypatch.setattr(jsonl_import, "PgStore", Pg)
    monkeypatch.setattr(jsonl_import, "load_file", lambda *a, **k: stats)
    monkeypatch.setattr(postprocess, "run_post_steps", lambda store, **k: seen.append(k) or True)
    assert jsonl_import.main([str(tmp_path / "a.jsonl"), "--source", "topcv"]) == 0
    assert seen == [{"skills": True, "vectors": True}]


def test_jsonl_dry_run_does_not_touch_db(tmp_path, monkeypatch):
    stats = jsonl_import.RunStats()
    stats.items_seen = 1
    monkeypatch.setattr(jsonl_import, "load_file", lambda *a, **k: stats)
    monkeypatch.setattr(postprocess, "run_post_steps", lambda *a, **k: pytest.fail("không gọi"))
    assert jsonl_import.main([str(tmp_path / "a.jsonl"), "--source", "topcv", "--dry-run"]) == 0
