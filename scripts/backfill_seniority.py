"""Gắn lại core.jobs.seniority cho tin crawl đã có (luật: config/seniority.yaml).

    uv run python scripts/backfill_seniority.py              # chạy thử: in phân bố, không ghi
    uv run python scripts/backfill_seniority.py --apply      # ghi DB
    uv run python scripts/backfill_seniority.py --sample 30  # in 30 tin ngẫu nhiên để kiểm tay

Tin mới crawl đã được gắn trong store.build_job_row. Script này cần chạy một lần cho tin cũ và
mỗi khi đổi config/seniority.yaml (tin không đổi nội dung thì crawl không ghi lại cột này).
Chạy lại nhiều lần được.
"""

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion.crawl import _database_url  # noqa: E402
from ingestion.seniority import infer_seniority, source_signals  # noqa: E402

# Payload gốc mới nhất của mỗi tin (để lấy ô cấp bậc của nguồn).
SQL = """
select j.id, j.title, j.years_exp_min, j.seniority::text, j.status::text, snap.payload
from core.jobs j
left join lateral (
  select p.payload
  from core.job_sources js
  join raw.job_snapshots p on p.source_id = js.source_id and p.source_job_id = js.source_job_id
  where js.job_id = j.id
  order by p.fetched_at desc
  limit 1
) snap on true
where j.origin = 'crawled'
"""


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="ghi vào DB")
    parser.add_argument("--sample", type=int, default=0, help="in N tin ngẫu nhiên để kiểm tay")
    args = parser.parse_args(argv)
    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL")

    import psycopg

    with psycopg.connect(dsn.replace("+psycopg", ""), prepare_threshold=None) as conn:
        rows = conn.execute(SQL).fetchall()
        changes, levels, methods, open_levels, out = [], Counter(), Counter(), Counter(), []
        for job_id, title, years, old, status, payload in rows:
            level, method = infer_seniority(
                title, float(years) if years is not None else None, *source_signals(payload)
            )
            levels[level] += 1
            methods[method] += 1
            if status == "open":
                open_levels[level] += 1
            out.append((job_id, title, years, level, method))
            if level != old:
                changes.append((level, job_id))
        total_open = sum(open_levels.values())
        known = total_open - open_levels["unknown"]
        print(f"Tin crawl: {len(rows)} · sẽ đổi: {len(changes)}")
        print(f"Theo cách suy: {dict(methods.most_common())}")
        print(f"Tin đang mở theo cấp bậc: {dict(open_levels.most_common())}")
        if total_open:
            print(f"Tin đang mở có cấp bậc: {known}/{total_open} ({100 * known / total_open:.1f}%)")
        if args.sample:
            for job_id, title, years, level, method in random.Random(1).sample(
                out, min(args.sample, len(out))
            ):
                print(f"  {job_id:>6} {level:8} {method:6} {years!s:>5}  {title[:80]}")
        if args.apply and changes:
            with conn.cursor() as cur:
                cur.executemany(
                    "update core.jobs set seniority = %s::core.seniority where id = %s", changes
                )
            conn.commit()
            print(f"Đã ghi {len(changes)} tin.")
        elif not args.apply:
            print("Chưa ghi gì (chạy lại với --apply để ghi).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
