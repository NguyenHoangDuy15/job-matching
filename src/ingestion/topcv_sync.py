"""Incrementally sync completed TopCV rows from SQLite/JSONL to Supabase."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from ingestion.jsonl_import import read_jsonl, record_to_posting
from ingestion.store import PgStore, RunStats


class TopCVSyncError(RuntimeError):
    """The durable local checkpoint cannot be synced safely."""


def pending_job_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """SELECT d.job_id
             FROM job_details d
             JOIN job_queue q ON q.job_id = d.job_id
            WHERE q.status = 'COMPLETED' AND COALESCE(d.synced_to_pg, 0) = 0
            ORDER BY d.job_id"""
    ).fetchall()
    return [str(row[0]) for row in rows]


def pending_postings(path: Path, job_ids: list[str], source: str):
    wanted = set(job_ids)
    fetched_at = datetime.now(UTC)
    postings = {}
    for line_no, record in read_jsonl(path):
        raw_id = record.get("job_id") or record.get("source_job_id")
        job_id = str(raw_id) if raw_id is not None else ""
        if job_id not in wanted:
            continue
        posting = record_to_posting(record, source, fetched_at)
        if posting is None:
            raise TopCVSyncError(f"Dòng {line_no} của {path} không tạo được posting hợp lệ")
        if posting.source_job_id != job_id:
            raise TopCVSyncError(
                f"Dòng {line_no} có source_job_id={posting.source_job_id}, mong đợi {job_id}"
            )
        postings[job_id] = posting
    missing = sorted(wanted - postings.keys())
    if missing:
        sample = ", ".join(missing[:10])
        raise TopCVSyncError(
            f"JSONL thiếu {len(missing)} JD chưa sync trong SQLite (ví dụ: {sample})"
        )
    return postings


def sync_pending(
    conn: sqlite3.Connection,
    jsonl_path: Path,
    store,
    *,
    source: str = "topcv",
    verbose: bool = False,
) -> RunStats:
    job_ids = pending_job_ids(conn)
    stats = RunStats()
    if not job_ids:
        print("[SYNC] Không có JD TopCV mới cần đồng bộ.")
        return stats

    postings = pending_postings(jsonl_path, job_ids, source)
    run_id = store.start_run(source, None, "topcv_automation")
    status, error = "success", None
    try:
        for index, job_id in enumerate(job_ids, start=1):
            posting = postings[job_id]
            result = store.save(posting, None, run_id)
            stats.count(result)
            with conn:
                changed = conn.execute(
                    """UPDATE job_details SET synced_to_pg=1
                        WHERE job_id=? AND COALESCE(synced_to_pg, 0)=0""",
                    (job_id,),
                ).rowcount
            if changed != 1:
                raise TopCVSyncError(f"Không đánh dấu được synced_to_pg cho job_id={job_id}")
            if verbose:
                print(f"[SYNC {index}/{len(job_ids)}] {result:9} {posting.title[:80]}")
    except Exception as exc:
        status, error = "failed", repr(exc)
        raise
    finally:
        store.finish_run(run_id, stats, status, error)

    unchanged = stats.items_seen - stats.items_new - stats.items_updated
    print(
        f"[SYNC] success · đã xét {stats.items_seen} · mới {stats.items_new} "
        f"· cập nhật {stats.items_updated} · không đổi {unchanged}"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    from ingestion.crawl import _database_url

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Đồng bộ tăng dần TopCV SQLite lên Supabase")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--source", default="topcv")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if not args.db.is_file():
        parser.error(f"Không tìm thấy SQLite checkpoint: {args.db}")
    if not args.jsonl.is_file():
        parser.error(f"Không tìm thấy JSONL checkpoint: {args.jsonl}")

    with sqlite3.connect(args.db) as conn:
        if not pending_job_ids(conn):
            print("[SYNC] Không có JD TopCV mới cần đồng bộ.")
            return 0

    dsn = _database_url()
    if not dsn:
        parser.error("Thiếu DATABASE_URL trong environment hoặc .env")
    store = PgStore(dsn)
    try:
        with sqlite3.connect(args.db) as conn:
            sync_pending(conn, args.jsonl, store, source=args.source, verbose=args.verbose)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
