"""Lấy ngẫu nhiên N tin đang mở để kiểm tay thẻ kỹ năng (S2-D05: "kiểm tay 20 tin").

    uv run python scripts/check_job_skills.py              # 20 tin → data/eval/check_job_skills.csv
    uv run python scripts/check_job_skills.py --n 30 --seed 2
    uv run python scripts/check_job_skills.py --score      # chấm sau khi đã điền

Mỗi dòng một tin: link gốc, kỹ năng bắt buộc / ưu tiên máy gắn, và 4 cột để người kiểm điền:
  thieu   kỹ năng có trong tin gốc mà máy không gắn (cách nhau dấu phẩy)
  sai     thẻ máy gắn nhưng không phải kỹ năng tin yêu cầu
  sai_muc thẻ đúng kỹ năng nhưng sai mức (bắt buộc ↔ ưu tiên)
  note    ghi chú
File có tiêu đề và link tin thật → không lên git (data/).
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.crawl import _database_url  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eval" / "check_job_skills.csv"

SQL = """
select j.id, j.title, c.name,
       coalesce((select js.url from core.job_sources js where js.job_id = j.id
                 order by js.last_seen_at desc limit 1), j.apply_url) as url,
       coalesce(string_agg(s.name, ', ' order by s.name)
                  filter (where k.level = 'required'), '') as bat_buoc,
       coalesce(string_agg(s.name, ', ' order by s.name)
                  filter (where k.level = 'preferred'), '') as uu_tien
from core.jobs j
left join core.companies c on c.id = j.company_id
left join core.job_skills k on k.job_id = j.id
left join ref.skills s on s.id = k.skill_id
where j.origin = 'crawled' and j.status = 'open'
  and (j.valid_through is null or j.valid_through >= current_date)
group by j.id, c.name
order by md5(j.id::text || %(seed)s)
limit %(n)s
"""


def _items(cell: str) -> list[str]:
    return [x.strip() for x in (cell or "").split(",") if x.strip()]


def score(path: Path = OUT) -> dict:
    """Tỷ lệ đúng của thẻ trên các tin đã kiểm."""
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    cards = sum(len(_items(r["bat_buoc"])) + len(_items(r["uu_tien"])) for r in rows)
    wrong = sum(len(_items(r["sai"])) for r in rows)
    wrong_level = sum(len(_items(r["sai_muc"])) for r in rows)
    missing = sum(len(_items(r["thieu"])) for r in rows)
    correct = cards - wrong
    full = sum(
        not _items(r["thieu"])
        and not _items(r["sai"])
        and bool(_items(r["bat_buoc"]) or _items(r["uu_tien"]))
        for r in rows
    )
    return {
        "tin": len(rows),
        "the": cards,
        "precision_the": round(correct / cards, 3) if cards else 0.0,
        "dung_muc": round((correct - wrong_level) / correct, 3) if correct else 0.0,
        "recall_xap_xi": round(correct / (correct + missing), 3) if correct + missing else 0.0,
        "tin_day_du": f"{full}/{len(rows)}",
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", default="1", help="đổi seed để lấy bộ tin khác")
    parser.add_argument("--score", action="store_true", help="chấm file đã điền")
    args = parser.parse_args(argv)
    if args.score:
        print(score())
        return 0
    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL (biến môi trường hoặc file .env)")

    import psycopg

    with psycopg.connect(dsn.replace("+psycopg", ""), prepare_threshold=None) as conn:
        rows = conn.execute(SQL, {"seed": args.seed, "n": args.n}).fetchall()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "job_id",
                "tieu_de",
                "cong_ty",
                "link",
                "bat_buoc",
                "uu_tien",
                "thieu",
                "sai",
                "sai_muc",
                "note",
            ]
        )
        for row in rows:
            writer.writerow([*row, "", "", "", ""])
    print(f"{len(rows)} tin → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
