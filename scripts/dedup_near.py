"""Gộp tin gần trùng bằng MinHash/LSH (S3-T04, cần migration 0011).

    uv run python scripts/dedup_near.py            # chạy thử: in cặp gộp / vào hàng chờ, không ghi
    uv run python scripts/dedup_near.py --apply    # ghi thật

Chỉ so tin đang mở cùng công ty, có chung tỉnh. Độ giống = Jaccard cụm 3 từ của chức danh + mô tả:
  ≥ 0,85 và chức danh gần như trùng, mô tả đủ dài → gộp (core.merge_jobs, giữ tin id nhỏ)
  0,70–0,85 hoặc chưa đủ chắc                     → core.dedup_candidates chờ admin duyệt
Crawl hằng ngày đã tự chạy bước này (scripts/crawl.py run, bỏ bằng --skip-dedup).
Nên chạy scripts/dedup_exact.py --apply trước một lần cho dữ liệu cũ.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion.crawl import _database_url  # noqa: E402
from ingestion.dedup_pg import run_near_dedup  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="ghi vào DB (mặc định chỉ chạy thử)")
    parser.add_argument("--sample", type=int, default=15, help="số cặp in ra để kiểm tay")
    args = parser.parse_args(argv)

    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL (biến môi trường hoặc file .env)")

    import psycopg

    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn) as conn, conn.transaction():
        report = run_near_dedup(conn)
        titles = dict(
            conn.execute(
                "select id, title from core.jobs where id = any(%s)",
                ([i for a, b, *_ in report.samples for i in (a, b)],),
            ).fetchall()
        )
        if not args.apply:
            raise psycopg.Rollback()

    mode = "ĐÃ GHI" if args.apply else "CHẠY THỬ (không ghi)"
    print(f"[dedup-near] {mode}")
    print(f"  tin mở đã so          : {report.compared}")
    print(f"  gộp tự động (≥ 0,85)  : {report.merged}")
    print(f"  vào hàng chờ admin    : {report.queued}")
    print(f"  admin đã bác trước đó : {report.skipped_distinct}")
    print(f"  cặp chờ đã đóng, dọn  : {report.stale_removed}")
    for a, b, sim, decision in report.samples[: args.sample]:
        print(
            f"    {decision:6} {sim:.2f}  #{a} {titles.get(a, '')!r}  ~  #{b} {titles.get(b, '')!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
