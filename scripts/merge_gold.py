"""Ghép các file gán nhãn gold của từng người và kiểm lỗi trước khi chấm (S2-D04 / S2-D07).

    uv run python scripts/merge_gold.py                 # 3 file gold_<tên>.csv → gold_mentions.csv
    uv run python scripts/merge_gold.py --who duy tung  # chỉ ghép những file đã xong

Kiểm: nhãn hợp lệ, không để trống, không ai sửa/xóa/thêm dòng so với file mẫu
(gold_mentions_TEMPLATE.csv), không trùng dòng giữa các file. Có lỗi thì in ra và KHÔNG ghi.
Dòng có ghi chú (cột note) được in ra để cả nhóm xem lại.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"
LABELS = {"required", "preferred", "mentioned", "drop"}
KEY = ["jd_id", "sentence", "skill_id", "s"]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--who", nargs="+", default=["duy", "tung", "thinh"])
    args = parser.parse_args(argv)

    template = pd.read_csv(EVAL / "gold_mentions_TEMPLATE.csv")
    expected = set(map(tuple, template[KEY].astype(str).values))
    parts, errors = [], []
    for who in args.who:
        path = EVAL / f"gold_{who}.csv"
        if not path.exists():
            errors.append(f"thiếu file {path}")
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        missing_cols = [c for c in [*KEY, "gold"] if c not in df.columns]
        if missing_cols:
            errors.append(f"{who}: thiếu cột {missing_cols} (đã đổi tên hay xóa cột?)")
            continue
        df["gold"] = df["gold"].str.strip().str.lower()
        empty = df[df["gold"] == ""]
        bad = df[(df["gold"] != "") & ~df["gold"].isin(LABELS)]
        if len(empty):
            errors.append(f"{who}: {len(empty)} dòng chưa gán (dòng file {_rows(empty)})")
        if len(bad):
            errors.append(f"{who}: nhãn lạ {sorted(set(bad['gold']))} ở dòng {_rows(bad)}")
        keys = set(map(tuple, df[KEY].values))
        if keys - expected:
            errors.append(
                f"{who}: {len(keys - expected)} dòng không có trong file mẫu "
                "(đã sửa cột jd_id/sentence/skill_id/s?)"
            )
        df["_who"] = who
        parts.append(df)

    if not parts:
        print("\n".join(errors))
        return 2
    gold = pd.concat(parts, ignore_index=True)
    # File mẫu có sẵn vài dòng trùng (câu lặp trong JD); chỉ lỗi khi một dòng nằm ở 2 file.
    owners = gold.groupby(KEY)["_who"].nunique()
    if (owners > 1).any():
        errors.append(f"{int((owners > 1).sum())} dòng có ở nhiều file (gán trùng người)")
    covered = set(map(tuple, gold[KEY].values)) & expected
    if args.who == ["duy", "tung", "thinh"] and len(covered) < len(expected):
        errors.append(f"còn {len(expected) - len(covered)} dòng của file mẫu chưa ai gán")

    if "note" in gold.columns:
        notes = gold[gold["note"].fillna("").str.strip() != ""]
        if len(notes):
            print(f"{len(notes)} dòng có ghi chú, cả nhóm xem lại:")
            for _, r in notes.iterrows():
                where = f"[{r['_who']}] {r['jd_id']} {r['skill_text']!r}"
                print(f"  {where} → {r['gold']}: {r['note']}")

    if errors:
        print("LỖI, chưa ghi gold_mentions.csv:")
        print("\n".join(f"  - {e}" for e in errors))
        return 1
    out = EVAL / "gold_mentions.csv"
    gold.drop(columns="_who").to_csv(out, index=False)
    print(f"{len(gold)} dòng từ {args.who} → {out}")
    print("theo nhãn:", dict(gold["gold"].value_counts()))
    print("Tiếp: uv run python scripts/evaluate_levels.py score")
    return 0


def _rows(df: pd.DataFrame, limit: int = 10) -> str:
    rows = [str(i + 2) for i in df.index[:limit]]  # +2: dòng tiêu đề + đếm từ 1
    return ", ".join(rows) + (" …" if len(df) > limit else "")


if __name__ == "__main__":
    sys.exit(main())
