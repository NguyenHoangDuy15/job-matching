"""Gắn lại các cột SUY RA của core.jobs cho tin crawl đã có, từ dữ liệu đã lưu (không crawl lại).

    uv run python scripts/rederive_jobs.py                                   # chạy thử cả 2 trường
    uv run python scripts/rederive_jobs.py --field work_mode --sample 30     # in 30 tin để kiểm tay
    uv run python scripts/rederive_jobs.py --field seniority --field work_mode --apply

Trường:
  seniority  config/seniority.yaml (ô cấp bậc của nguồn → tiêu đề → số năm kinh nghiệm)
  work_mode  config/work_mode.yaml (tiêu đề/địa điểm → nội dung JD → có tỉnh thì onsite)

Tin mới crawl đã được gắn trong store.build_job_row. Tin không đổi nội dung thì crawl không ghi lại
các cột này, nên chạy script mỗi khi đổi file yaml. Chạy lại nhiều lần được.
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
from ingestion.work_mode import infer_work_mode  # noqa: E402

FIELDS = ("seniority", "work_mode")

# Payload gốc mới nhất (ô cấp bậc của nguồn, JSON-LD TELECOMMUTE) + địa điểm gốc + có tỉnh không.
SQL = """
select j.id, j.title, j.years_exp_min, j.seniority::text, j.work_mode::text, j.status::text,
       coalesce(j.jd_text,
                concat_ws(E'\n', j.description, j.requirements, j.preferred, j.benefits)),
       exists (select 1 from core.job_locations l where l.job_id = j.id),
       (select string_agg(distinct l.address_raw, '; ') from core.job_locations l
         where l.job_id = j.id),
       snap.payload
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


def derive(field: str, row: tuple) -> tuple[str, str]:
    _, title, years, _, _, _, text, has_province, location, payload = row
    if field == "seniority":
        y = float(years) if years is not None else None
        return infer_seniority(title, y, *source_signals(payload))
    telecommute = "TELECOMMUTE" in str((payload or {}).get("jobLocationType") or "").upper()
    return infer_work_mode(
        title, location, text, has_province=has_province, telecommute=telecommute
    )


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--field", action="append", choices=FIELDS, help="mặc định: tất cả")
    parser.add_argument("--apply", action="store_true", help="ghi vào DB")
    parser.add_argument("--sample", type=int, default=0, help="in N tin ngẫu nhiên để kiểm tay")
    args = parser.parse_args(argv)
    fields = args.field or list(FIELDS)
    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL")

    import psycopg

    with psycopg.connect(dsn.replace("+psycopg", ""), prepare_threshold=None) as conn:
        rows = conn.execute(SQL).fetchall()
        for field in fields:
            old_at = 3 if field == "seniority" else 4
            changes, methods, open_values, out = [], Counter(), Counter(), []
            for row in rows:
                value, method = derive(field, row)
                methods[method] += 1
                if row[5] == "open":
                    open_values[value] += 1
                    out.append((row[0], value, method, row[1]))
                if value != row[old_at]:
                    changes.append((value, row[0]))
            total = sum(open_values.values())
            print(f"== {field}: tin crawl {len(rows)} · sẽ đổi {len(changes)}")
            print(f"   theo cách suy: {dict(methods.most_common())}")
            print(f"   tin đang mở ({total}): {dict(open_values.most_common())}")
            if args.sample:
                for job_id, value, method, title in random.Random(1).sample(
                    out, min(args.sample, len(out))
                ):
                    print(f"   {job_id:>6} {value:8} {method:11} {title[:70]}")
            if args.apply and changes:
                enum = "core.seniority" if field == "seniority" else "core.work_mode"
                with conn.cursor() as cur:
                    cur.executemany(
                        f"update core.jobs set {field} = %s::{enum} where id = %s", changes
                    )
                conn.commit()
                print(f"   đã ghi {len(changes)} tin")
        if not args.apply:
            print("Chưa ghi gì (chạy lại với --apply để ghi).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
