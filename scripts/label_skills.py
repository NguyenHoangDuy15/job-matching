"""Gắn kỹ năng + mức cho tin trong core.jobs và ghi core.job_skills (S2-D04, S2-D05).

    uv run python scripts/label_skills.py                     # chỉ báo cáo, không ghi
    uv run python scripts/label_skills.py --apply             # ghi DB (toàn bộ kho)
    uv run python scripts/label_skills.py --apply --stale     # chỉ tin chưa gắn / gắn bằng bản cũ
    uv run python scripts/label_skills.py --only-open --show 5
    uv run python scripts/label_skills.py --report            # số liệu nghiệm thu S2-D05
    uv run python scripts/label_skills.py --no-model          # chỉ luật, không dùng Tầng 2

Cần migration 0003, 0005 và seed_skills.sql. Tầng 2 cần models/jev_local_v1.joblib
(scripts/train_tier2.py); không có file thì chỉ dùng luật.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.crawl import _database_url  # noqa: E402
from skillkit.levels.db import (  # noqa: E402
    coverage_report,
    has_levels_schema,
    label_jobs,
    select_jobs,
    skill_ids,
    write_job_skills,
)
from skillkit.levels.pipeline import SkillLabeler  # noqa: E402


def print_report(report: dict) -> None:
    print(
        f"Tin đang mở: {report['open_jobs']} · có thẻ kỹ năng: {report['with_skill_cards']} "
        f"({report['pct_with_cards']}%, mục tiêu ≥ 90%) · "
        f"trung bình {report['avg_cards_per_job']} thẻ/tin"
    )
    for col in ("level", "extractor", "source_detail"):
        print(f"  {col}: {report[col]}")
    if report["jobs_without_cards"]:
        print("  Tin đang mở chưa có thẻ (mới nhất):")
        for job_id, title in report["jobs_without_cards"]:
            print(f"    {job_id}  {title}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="ghi DB (mặc định chỉ báo cáo)")
    parser.add_argument("--no-model", action="store_true", help="không dùng Tầng 2")
    parser.add_argument("--only-open", action="store_true", help="chỉ tin đang mở, còn hạn")
    parser.add_argument("--stale", action="store_true", help="chỉ tin chưa gắn hoặc gắn bản cũ")
    parser.add_argument("--limit", type=int, help="chỉ xử lý N tin mới nhất")
    parser.add_argument("--show", type=int, default=0, help="in chi tiết N tin đầu")
    parser.add_argument("--report", action="store_true", help="chỉ in số liệu nghiệm thu")
    args = parser.parse_args(argv)

    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL (biến môi trường hoặc file .env)")

    import psycopg

    with psycopg.connect(dsn.replace("+psycopg", ""), prepare_threshold=None) as conn:
        if not has_levels_schema(conn):
            print("DB chưa chạy db/migrations/0005_job_skill_levels.sql.")
            return 2
        if args.report:
            print_report(coverage_report(conn))
            return 0

        labeler = SkillLabeler.default(with_model=not args.no_model)
        print(f"model_version: {labeler.model_version}")
        if labeler.clf is None and not args.no_model:
            print("! chưa có model Tầng 2: chỉ dùng luật (chạy scripts/train_tier2.py)")
        rows = select_jobs(
            conn,
            model_version=labeler.model_version,
            only_open=args.only_open,
            stale=args.stale,
            limit=args.limit,
        )
        labeled = label_jobs(labeler, rows)

        total = Counter(r.level for rows in labeled.values() for r in rows)
        sources = Counter(r.source for rows in labeled.values() for r in rows)
        print(f"Tin: {len(labeled)} · kỹ năng: {sum(total.values())} · {dict(total)}")
        print(f"Theo nguồn: {dict(sources.most_common())}")
        for job_id in list(labeled)[: args.show]:
            print(f"\n# tin {job_id}")
            for r in sorted(labeled[job_id], key=lambda r: (r.level, r.skill_id)):
                print(
                    f"  {r.level:9} {r.skill_id:20} {r.source:12} {r.confidence:.2f}  "
                    f"{r.evidence[:90]}"
                )
        if not args.apply:
            print("\nChưa ghi gì (chạy lại với --apply để ghi).")
            return 0
        stats = write_job_skills(conn, labeled, skill_ids(conn), labeler.model_version)
        conn.commit()
        print(f"Đã ghi: {dict(stats)}\n")
        print_report(coverage_report(conn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
