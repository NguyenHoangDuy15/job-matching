"""Lấy ngẫu nhiên N tin đang mở để kiểm tay thẻ kỹ năng (S2-D05: "kiểm tay 20 tin").

    uv run python scripts/check_job_skills.py              # 20 tin → data/eval/check_job_skills.csv
    uv run python scripts/check_job_skills.py --n 30 --seed 2
    uv run python scripts/check_job_skills.py --score      # chấm sau khi đã điền
    uv run python scripts/check_job_skills.py --merge a.csv b.csv   # gộp phần của từng người

Mỗi dòng một tin: link gốc, kỹ năng bắt buộc / ưu tiên máy gắn, và 4 cột để người kiểm điền:
  thieu   kỹ năng có trong tin gốc mà máy không gắn (cách nhau dấu phẩy)
  sai     thẻ máy gắn nhưng không phải kỹ năng tin yêu cầu
  sai_muc thẻ đúng kỹ năng nhưng sai mức (bắt buộc ↔ ưu tiên)
  note    ghi chú; ghi "bỏ qua" khi không chấm được tin (ví dụ trang lỗi)
File có tiêu đề và link tin thật → không lên git (data/).
"""

import argparse
import csv
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.crawl import _database_url  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eval" / "check_job_skills.csv"
SKILLS_YAML = ROOT / "config" / "skills.yaml"
COLUMNS = ["job_id", "tieu_de", "cong_ty", "link", "bat_buoc", "uu_tien"]
COLUMNS += ["thieu", "sai", "sai_muc", "note"]
FILLED = ("thieu", "sai", "sai_muc")

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


def comma_names(path: Path = SKILLS_YAML) -> tuple[str, ...]:
    """Tên kỹ năng có dấu phẩy ("Cẩn thận, chi tiết"): không được tách khi đọc ô."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(s["name"] for s in data["skills"] if "," in s.get("name", ""))


def _items(cell: str, keep: tuple[str, ...] = ()) -> list[str]:
    """Tách ô theo dấu phẩy, giữ nguyên tên trong `keep`, bỏ trùng (giữ thứ tự)."""
    text = cell or ""
    found = [name for name in keep if name in text]
    for name in found:
        text = text.replace(name, "")
    parts = [x.strip() for x in text.replace("\t", ",").split(",")]
    return list(dict.fromkeys([*found, *(p for p in parts if p)]))


def _skipped(row: dict) -> bool:
    return "bỏ qua" in (row.get("note") or "").lower()


def _fix_repeated_paste(cell: str) -> str:
    """Ô bị dán lặp ("A, B, CA, B, C" hoặc "A, B\tA, B"): giữ bản đầu tiên."""
    text = (cell or "").strip()
    first = text.split(",")[0].strip()
    if len(first) < 2:
        return text
    again = text.find(first, len(first))
    return text[:again].rstrip(" ,\t") if again > 0 else text


def read_rows(path: Path) -> list[dict]:
    # utf-8-sig: Excel lưu CSV có BOM, không bỏ thì cột đầu thành "﻿job_id".
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def merge(paths: list[Path], out: Path = OUT) -> list[str]:
    """Gộp file của từng người kiểm thành `out`; trả về các cảnh báo đã sửa."""
    rows, seen, notes = [], set(), []
    for path in paths:
        for row in read_rows(path):
            if row["job_id"] in seen:
                raise ValueError(f"job {row['job_id']} có ở nhiều file")
            seen.add(row["job_id"])
            for col in FILLED:
                fixed = _fix_repeated_paste(row.get(col, ""))
                if fixed != (row.get(col) or "").strip():
                    notes.append(f"job {row['job_id']}: cột {col} bị dán lặp, giữ bản đầu")
                row[col] = fixed
            rows.append({c: row.get(c, "") for c in COLUMNS})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return notes


def score(path: Path = OUT, keep: tuple[str, ...] | None = None) -> dict:
    """Tỷ lệ đúng của thẻ trên các tin đã kiểm; tin ghi "bỏ qua" không tính."""
    keep = comma_names() if keep is None else keep
    rows = read_rows(path)
    checked = [r for r in rows if not _skipped(r)]
    cards = wrong = wrong_level = missing = full = 0
    warnings = []
    for r in checked:
        tags = _items(r["bat_buoc"], keep) + _items(r["uu_tien"], keep)
        # Người kiểm ghi "thiếu" một thẻ máy đã gắn: không tính là thiếu.
        already = [x for x in _items(r["thieu"], keep) if x in tags]
        if already:
            warnings.append(f"job {r['job_id']}: {', '.join(already)} vừa ở 'thieu' vừa đã gắn")
        miss = [x for x in _items(r["thieu"], keep) if x not in tags]
        bad = _items(r["sai"], keep)
        cards += len(tags)
        wrong += len(bad)
        wrong_level += len(_items(r["sai_muc"], keep))
        missing += len(miss)
        full += not miss and not bad and bool(tags)
    correct = cards - wrong
    return {
        "tin": len(rows),
        "bo_qua": len(rows) - len(checked),
        "tin_cham": len(checked),
        "the": cards,
        "the_dung": correct,
        "the_sai": wrong,
        "sai_muc": wrong_level,
        "thieu": missing,
        "precision_the": round(correct / cards, 3) if cards else 0.0,
        "dung_muc": round((correct - wrong_level) / correct, 3) if correct else 0.0,
        "recall_xap_xi": round(correct / (correct + missing), 3) if correct + missing else 0.0,
        "tin_day_du": f"{full}/{len(checked)}",
        "canh_bao": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", default="1", help="đổi seed để lấy bộ tin khác")
    parser.add_argument("--score", action="store_true", help="chấm file đã điền")
    parser.add_argument("--merge", nargs="+", type=Path, metavar="CSV", help="gộp phần từng người")
    args = parser.parse_args(argv)
    if args.merge:
        for note in merge(args.merge):
            print("sửa:", note)
        print(f"{len(read_rows(OUT))} tin → {OUT}")
    if args.score:
        result = score()
        for warning in result.pop("canh_bao"):
            print("cảnh báo:", warning)
        print(result)
    if args.merge or args.score:
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
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([*row, "", "", "", ""])
    print(f"{len(rows)} tin → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
