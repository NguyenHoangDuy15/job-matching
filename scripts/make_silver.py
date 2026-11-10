"""Sinh dữ liệu train Tầng 2 (nhãn yếu do luật gán) từ VietJobs, trừ 50 JD gold (S2-D04).

    uv run python scripts/make_silver.py

Đầu vào: data/interim/vietjobs_it.csv (cột description, qualifications, requirements_text).
Đầu ra (chứa câu JD thật → KHÔNG lên git):
  data/interim/silver_mentions.csv  luật chắc (rule_neg / rule_section / rule_cue)
  data/interim/hard_mentions.csv    ca khó (rule_mixed, câu mô tả không cue) để gán sau
Chưa gọi LLM gán ca khó: nhóm chưa dùng API key (xem docs S2-D04).
"""

import ast
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skillkit.levels.pipeline import SkillLabeler  # noqa: E402
from skillkit.levels.rules import decide  # noqa: E402
from skillkit.sections import explode  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "interim" / "vietjobs_it.csv"
GOLD = ROOT / "data" / "eval" / "jd_gold.jsonl"
OUT = ROOT / "data" / "interim"
COLUMNS = {
    "description": "description",
    "qualifications": "requirements",
    "requirements_text": "requirements",
}
SILVER_SOURCES = {"rule_neg", "rule_section", "rule_cue"}
FIELDS = ["jd_id", "section", "sentence", "skill_id", "skill_text", "s", "e", "label", "source"]


def lines_of(text: object) -> list[str]:
    """Câu của một cột VietJobs (giống scripts/build_jd_gold.py)."""
    if not isinstance(text, str) or not text.strip():
        return []
    if text.startswith("["):
        try:
            return [f"- {item}" for item in ast.literal_eval(text) if str(item).strip()]
        except (ValueError, SyntaxError):
            pass
    return [p for line in text.splitlines() if line.strip() for p in explode(line.strip())]


def gold_rows() -> set[int]:
    if not GOLD.exists():
        print(f"! chưa có {GOLD}: chạy scripts/build_jd_gold.py trước để loại JD gold")
        return set()
    return {json.loads(line)["source_row"] for line in GOLD.open(encoding="utf-8")}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    df = pd.read_csv(SRC)
    held_out = gold_rows()
    labeler = SkillLabeler.default(with_model=False)
    silver, hard, seen = [], [], set()
    for idx, row in df.iterrows():
        if idx in held_out:
            continue
        lines = [(line, sec) for col, sec in COLUMNS.items() for line in lines_of(row[col])]
        for m in labeler.mentions(f"vj{idx}", lines, has_sections=True):
            key = (m.section, m.sentence, m.skill_id)
            if key in seen:
                continue
            seen.add(key)
            d = decide(m.section, m.sentence, m.s, m.e)
            record = {
                "jd_id": m.jd_id,
                "section": m.section,
                "sentence": m.sentence,
                "skill_id": m.skill_id,
                "skill_text": m.skill_text,
                "s": m.s,
                "e": m.e,
                "label": d.level if d else "",
                "source": d.source if d else "none",
            }
            if d and d.source in SILVER_SOURCES and d.level in ("REQUIRED", "PREFERRED"):
                silver.append(record)
            elif d is None or d.source == "rule_mixed":
                hard.append(record)
    for name, rows in (("silver_mentions.csv", silver), ("hard_mentions.csv", hard)):
        with (OUT / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    print(f"Bỏ {len(held_out)} JD gold. JD dùng: {df.shape[0] - len(held_out)}")
    print(f"silver: {len(silver)} mention từ {len({r['jd_id'] for r in silver})} JD")
    print(f"  theo nhãn: {dict(Counter(r['label'] for r in silver))}")
    print(f"  theo nguồn: {dict(Counter(r['source'] for r in silver))}")
    print(f"ca khó: {len(hard)} · {dict(Counter((r['section'], r['source']) for r in hard))}")


if __name__ == "__main__":
    main()
