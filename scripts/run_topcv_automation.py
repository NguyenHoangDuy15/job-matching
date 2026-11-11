"""Run one safe TopCV automation batch and incrementally sync it to Supabase."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion import topcv  # noqa: E402
from ingestion.topcv_sync import VALID_RUN_TYPES  # noqa: E402
from ingestion.topcv_sync import main as sync_main  # noqa: E402


def prune_backups(directory: Path, keep: int) -> int:
    if keep < 1 or not directory.is_dir():
        return 0
    backups = sorted(
        (path for path in directory.glob("*.bak") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for path in backups[keep:]:
        path.unlink()
        removed += 1
    return removed


def write_summary(db_path: Path, output: Path, crawler_exit: int, sync_exit: int) -> dict:
    with sqlite3.connect(db_path) as conn:
        counts = dict(conn.execute("SELECT status, COUNT(*) FROM job_queue GROUP BY status"))
        synced = conn.execute(
            "SELECT COUNT(*) FROM job_details WHERE COALESCE(synced_to_pg, 0)=1"
        ).fetchone()[0]
        source = conn.execute(
            "SELECT status,last_http_status,blocked_at FROM source_state WHERE source='topcv'"
        ).fetchone()
    summary = {
        "crawler_exit": crawler_exit,
        "sync_exit": sync_exit,
        "queue": counts,
        "synced_to_supabase": synced,
        "source": {
            "status": source[0] if source else "READY",
            "last_http_status": source[1] if source else None,
            "blocked_at": source[2] if source else None,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SUMMARY] {json.dumps(summary, ensure_ascii=False)}")
    return summary


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Một lượt TopCV crawler + Supabase sync")
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path(os.environ.get("TOPCV_STATE_ROOT", "C:/topcv-automation")),
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--target-total", type=int, default=1000)
    parser.add_argument("--backup-retention", type=int, default=10)
    parser.add_argument("--run-type", choices=VALID_RUN_TYPES, default="manual")
    parser.add_argument("--sources-config", type=Path, default=ROOT / "config" / "sources.yaml")
    parser.add_argument("--chrome-path", default=os.environ.get("CHROME_PATH"))
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sync-only", action="store_true")
    args = parser.parse_args(argv)
    if args.limit < 1 or args.target_total < 1 or args.backup_retention < 1:
        parser.error("--limit, --target-total và --backup-retention phải >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = arguments(argv)
    state_root = args.state_root.resolve()
    db_path = state_root / "state" / "topcv_jobs.db"
    jsonl_path = state_root / "raw" / "topcv_nodriver.jsonl"
    profile_path = state_root / "chrome-profile"
    summary_path = state_root / "logs" / "latest-summary.json"

    if not db_path.is_file():
        print(
            f"[STOP] Chưa có checkpoint {db_path}. "
            "Hãy bootstrap SQLite hiện tại trước khi bật lịch.",
            file=sys.stderr,
        )
        return 3
    for path in (jsonl_path.parent, profile_path, summary_path.parent):
        path.mkdir(parents=True, exist_ok=True)

    crawler_exit = 0
    if not args.sync_only:
        crawler_argv = [
            "--details-only",
            "--limit",
            str(args.limit),
            "--target-total",
            str(args.target_total),
            "--db",
            str(db_path),
            "--out",
            str(jsonl_path),
            "--seen-file",
            str(state_root / "state" / "topcv_seen.txt"),
            "--profile",
            str(profile_path),
            "--sources-config",
            str(args.sources_config),
            "--headless" if args.headless else "--no-headless",
        ]
        if args.chrome_path:
            crawler_argv.extend(("--chrome-path", args.chrome_path))
        crawler_exit = asyncio.run(topcv.run(topcv.arguments(crawler_argv)))

    sync_exit = 0
    if jsonl_path.is_file():
        try:
            sync_exit = sync_main(
                [
                    "--db",
                    str(db_path),
                    "--jsonl",
                    str(jsonl_path),
                    "--source",
                    "topcv",
                    "--run-type",
                    args.run_type,
                ]
            )
        except Exception as exc:
            print(f"[SYNC ERROR] {exc}", file=sys.stderr)
            sync_exit = 1
    else:
        print(f"[SYNC ERROR] Chưa có JSONL checkpoint: {jsonl_path}", file=sys.stderr)
        sync_exit = 1

    write_summary(db_path, summary_path, crawler_exit, sync_exit)
    removed = prune_backups(db_path.parent / "backups", args.backup_retention)
    removed += prune_backups(jsonl_path.parent / "backups", args.backup_retention)
    if removed:
        print(f"[BACKUP] Đã xóa {removed} backup cũ; giữ {args.backup_retention} file mỗi loại.")

    if sync_exit:
        return sync_exit
    return crawler_exit


if __name__ == "__main__":
    raise SystemExit(main())
