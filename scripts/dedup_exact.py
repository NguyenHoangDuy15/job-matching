"""Khử trùng chính xác cho tin đã có trong DB (S3-T03, cần migration 0011).

    uv run python scripts/dedup_exact.py            # chạy thử: in số tin sẽ gộp, không ghi
    uv run python scripts/dedup_exact.py --apply    # ghi thật

Các bước: điền core.job_sources.url_norm → tính lại dedup hash (core.jobs.content_hash)
→ gộp tin chuẩn cùng URL chuẩn hóa hoặc cùng dedup hash (đều đang mở) bằng core.merge_jobs.
Tin bị gộp KHÔNG bị xóa: status closed, close_reason duplicate, duplicate_of = tin giữ lại.
Tin crawl mới đã được khử trùng ngay lúc ghi, nên chỉ cần chạy script một lần sau migration
và mỗi khi đổi cách chuẩn hóa trong src/ingestion/dedup.py. Chạy lại nhiều lần được.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion.crawl import _database_url  # noqa: E402
from ingestion.dedup_pg import backfill_exact  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="ghi vào DB (mặc định chỉ chạy thử)")
    parser.add_argument("--sample", type=int, default=10, help="số cặp gộp in ra để kiểm tay")
    args = parser.parse_args(argv)

    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL (biến môi trường hoặc file .env)")

    import psycopg

    # Một transaction: chạy thử thì rollback toàn bộ, số liệu in ra vẫn đúng như khi ghi thật.
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn) as conn, conn.transaction():
        report = backfill_exact(conn)
        if not args.apply:
            raise psycopg.Rollback()

    mode = "ĐÃ GHI" if args.apply else "CHẠY THỬ (không ghi)"
    print(f"[dedup-exact] {mode}")
    print(f"  url_norm điền mới      : {report.url_filled}")
    print(f"  dedup hash tính lại    : {report.hash_updated}")
    print(f"  nhóm trùng URL / hash  : {report.url_groups} / {report.hash_groups}")
    print(f"  tin bị gộp             : {report.merged}")
    print(f"  trùng chính xác còn lại: {report.remaining}")
    for keep, dup, reason in report.samples[: args.sample]:
        print(f"    #{dup} → #{keep} ({reason})")
    return 0 if report.remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
