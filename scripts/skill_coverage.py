"""Độ phủ từ điển kỹ năng (S2-D03): % lượt nhắc trong cột technical_skills của VietJobs
mà SkillMatcher nhận ra. In các giá trị hay gặp chưa nhận ra để bổ sung config/skills.yaml.

Chạy: PYTHONPATH=src uv run python scripts/skill_coverage.py [--top 40]
"""

import argparse
import ast
from collections import Counter
from pathlib import Path

import pandas as pd

from skillkit import load_taxonomy
from skillkit.matcher import SkillMatcher, prepare

ROOT = Path(__file__).resolve().parents[1]
# Công cụ thiết kế đồ họa/CAD/dựng video: VietJobs lẫn tin ngoài IT; cố ý không đưa vào từ điển.
NON_IT = {
    "indesign",
    "adobe indesign",
    "after effects",
    "after effect",
    "adobe after effects",
    "premiere",
    "adobe premiere",
    "premiere pro",
    "autocad",
    "canva",
    "capcut",
    "sketchup",
    "blender",
    "maya",
    "3ds max",
    "3d max",
    "3dsmax",
    "corel",
    "coreldraw",
    "revit",
    "lumion",
    "v-ray",
    "corona",
    "kỹ năng bán hàng",
    "kỹ năng đàm phán",
}


def skill_lists(path: Path) -> list[list[str]]:
    lists = []
    for raw in pd.read_csv(path)["technical_skills"].dropna():
        try:
            items = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            items = [raw]
        lists.append([str(i) for i in items if str(i).strip()])
    return lists


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(ROOT / "data" / "interim" / "vietjobs_it.csv"))
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()
    matcher = SkillMatcher(load_taxonomy(ROOT / "config" / "skills.yaml"))
    counts, hits = Counter(), Counter()
    for items in skill_lists(Path(args.input)):
        for item, found in zip(items, matcher.match_list(items), strict=True):
            key = prepare(item)[1]
            counts[key] += 1
            hits[key] += bool(found)
    it_counts = Counter({k: v for k, v in counts.items() if k not in NON_IT})
    for name, c in (("Mọi lượt nhắc", counts), ("Lượt nhắc IT", it_counts)):
        covered = sum(hits[k] for k in c)
        print(f"{name}: {covered}/{sum(c.values())} = {covered / sum(c.values()):.1%}")
    top = [k for k, _ in it_counts.most_common(200)]
    print(f"Top 200 giá trị IT hay gặp: nhận ra {sum(hits[k] > 0 for k in top)}/200")
    print(f"Top {args.top} giá trị IT chưa nhận ra (số lần trượt):")
    misses = Counter({k: v - hits[k] for k, v in it_counts.items() if v > hits[k]})
    for k, v in misses.most_common(args.top):
        print(f"  {v:4d}  {k}")


if __name__ == "__main__":
    main()
