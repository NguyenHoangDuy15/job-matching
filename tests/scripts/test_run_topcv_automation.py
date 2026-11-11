import json
import os
import sqlite3

import scripts.run_topcv_automation as automation


def test_prune_backups_keeps_newest_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    paths = []
    for index in range(4):
        path = backup_dir / f"state.{index}.bak"
        path.write_text(str(index), encoding="utf-8")
        path.touch()
        paths.append(path)
    # Explicit mtimes avoid relying on filesystem timestamp resolution.
    for index, path in enumerate(paths):
        path.chmod(0o600)
        path.touch()
        os.utime(path, (index + 1, index + 1))

    assert automation.prune_backups(backup_dir, keep=2) == 2
    assert sorted(path.name for path in backup_dir.glob("*.bak")) == [
        "state.2.bak",
        "state.3.bak",
    ]


def test_write_summary_reports_queue_and_source_state(tmp_path):
    db = tmp_path / "jobs.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE job_queue (status TEXT);
        CREATE TABLE job_details (synced_to_pg INTEGER);
        CREATE TABLE source_state (
            source TEXT, status TEXT, last_http_status INTEGER, blocked_at TEXT
        );
        INSERT INTO job_queue VALUES ('COMPLETED'), ('PENDING');
        INSERT INTO job_details VALUES (1), (0);
        INSERT INTO source_state VALUES ('topcv', 'READY', NULL, NULL);
        """
    )
    conn.commit()
    conn.close()
    output = tmp_path / "summary.json"

    summary = automation.write_summary(db, output, crawler_exit=0, sync_exit=0)

    assert summary["queue"] == {"COMPLETED": 1, "PENDING": 1}
    assert summary["synced_to_supabase"] == 1
    assert json.loads(output.read_text(encoding="utf-8")) == summary
