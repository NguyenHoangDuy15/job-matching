"""Tách 4 section cho các tin ĐÃ CÓ trong core.jobs (đọc jd_text, ghi 4 cột section).

Quy ước sau migration 0003:
- core.jobs.jd_text: toàn văn JD, CHỈ crawler / load_jsonl ghi.
- description / requirements / preferred / benefits: kết quả tách section, luôn sinh từ jd_text.
Chạy lại bao nhiêu lần cũng ra cùng kết quả; không đụng jd_text nên không mất bản gốc.

    uv run python scripts/split_sections.py                 # chỉ báo cáo, không ghi
    uv run python scripts/split_sections.py --apply         # ghi vào DB
    uv run python scripts/split_sections.py --apply --source topcv

Cần skillkit.sections (S2-D03, PR #618).
"""

import argparse
import sys
from collections import Counter
from collections.abc import Iterable

from ingestion.store import section_columns, split_text

SECTION_COLUMNS = ("description", "requirements", "preferred", "benefits")


def plan(rows: Iterable[tuple]) -> tuple[list[tuple], Counter]:
    """rows: (id, jd_text, description, requirements, preferred, benefits).

    Trả (danh sách cập nhật (id, 4 cột mới), thống kê).
    """
    updates: list[tuple] = []
    stats: Counter = Counter()
    for job_id, jd_text, *current in rows:
        stats["tin"] += 1
        new = section_columns(jd_text or "")
        values = tuple(new[c] for c in SECTION_COLUMNS)
        if any(values[1:]):
            stats["tach_duoc"] += 1
        else:
            stats["khong_co_heading"] += 1
        for name, value in zip(SECTION_COLUMNS, values, strict=True):
            if value:
                stats[f"co_{name}"] += 1
        if values != tuple(current):
            updates.append((job_id, *values))
    stats["can_cap_nhat"] = len(updates)
    return updates, stats


def main(argv: list[str] | None = None) -> int:
    from ingestion.crawl import _database_url

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Tách 4 section JD cho tin đã có trong core.jobs")
    parser.add_argument("--apply", action="store_true", help="ghi vào DB (mặc định chỉ báo cáo)")
    parser.add_argument("--source", help="chỉ xử lý một nguồn (ops.sources.code)")
    args = parser.parse_args(argv)

    if split_text is None:
        print("Chưa có skillkit.sections (S2-D03, PR #618). Merge #618 rồi chạy lại.")
        return 2
    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL (biến môi trường hoặc file .env)")

    import psycopg

    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, prepare_threshold=None) as conn:
        has_jd_text = conn.execute(
            "select 1 from information_schema.columns where table_schema = 'core' "
            "and table_name = 'jobs' and column_name = 'jd_text'"
        ).fetchone()
        if not has_jd_text:
            print(
                "DB chưa chạy db/migrations/0003_skill_tree_sections.sql (thiếu core.jobs.jd_text)."
            )
            return 2
        sql = (
            "select j.id, j.jd_text, j.description, j.requirements, j.preferred, j.benefits "
            "from core.jobs j where j.jd_text is not null"
        )
        params: tuple = ()
        if args.source:
            sql += (
                " and exists (select 1 from core.job_sources js join ops.sources s "
                "on s.id = js.source_id where js.job_id = j.id and s.code = %s)"
            )
            params = (args.source,)
        updates, stats = plan(conn.execute(sql, params).fetchall())

        print(f"Tin có jd_text: {stats['tin']}")
        print(f"  tách được section: {stats['tach_duoc']}")
        print(f"  không có heading: {stats['khong_co_heading']}")
        for name in SECTION_COLUMNS:
            print(f"  có {name}: {stats[f'co_{name}']}")
        print(f"  cần cập nhật: {stats['can_cap_nhat']}")
        if not args.apply:
            print("Chưa ghi gì (chạy lại với --apply để ghi).")
            return 0
        with conn.cursor() as cur:
            cur.executemany(
                "update core.jobs set description = %s, requirements = %s, preferred = %s, "
                "benefits = %s where id = %s",
                [(*values, job_id) for job_id, *values in updates],
            )
        conn.commit()
        print(f"Đã cập nhật {len(updates)} tin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
