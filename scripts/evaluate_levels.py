"""Nghiệm thu S2-D04 trên bộ gold do NGƯỜI gán (50 JD của data/eval/jd_gold.jsonl).

    uv run python scripts/evaluate_levels.py template   # tạo file để gán tay
    uv run python scripts/evaluate_levels.py score      # chấm sau khi đã gán

Bước 1 tạo data/eval/gold_mentions_TEMPLATE.csv: mỗi dòng là một lần nhắc kỹ năng, có sẵn
dự đoán của pipeline, cột `gold` để trống. Người gán đổi tên file thành gold_mentions.csv và
điền `gold` ∈ required | preferred | mentioned | drop (drop = không phải kỹ năng, hoặc nằm
trong Quyền lợi/phần ngoài 4 section). Script KHÔNG tự điền cột gold.

Bước 2 in accuracy, macro-F1 (required/preferred), precision/recall từng lớp, ma trận nhầm,
kết quả theo nguồn, so "chỉ luật" với "luật + JEV-local" trên lát khó; lưu
reports/eval_<model_version>.json. File gold chứa câu JD thật → không lên git.
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skillkit.levels.cascade import label_mention  # noqa: E402
from skillkit.levels.pipeline import SkillLabeler  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JDS = ROOT / "data" / "eval" / "jd_gold.jsonl"
TEMPLATE = ROOT / "data" / "eval" / "gold_mentions_TEMPLATE.csv"
GOLD = ROOT / "data" / "eval" / "gold_mentions.csv"
LABELS = ["required", "preferred", "mentioned", "drop"]
HARD = {"rule_mixed", "model", "fallback", "rule_desc"}
FIELDS = [
    "jd_id",
    "style",
    "section",
    "skill_id",
    "skill_text",
    "s",
    "sentence",
    "pred",
    "source",
    "rules_pred",
    "rules_source",
    "gold",
]


def predictions(labeler: SkillLabeler) -> list[dict]:
    out = []
    for line in JDS.open(encoding="utf-8"):
        jd = json.loads(line)
        for m in labeler.text_mentions(jd["id"], jd["text"]):
            full = label_mention(m, labeler.clf, labeler.config, labeler.cues)
            rules = label_mention(m, None, labeler.config, labeler.cues)
            out.append(
                {
                    "jd_id": jd["id"],
                    "style": jd["style"],
                    "section": m.section,
                    "skill_id": m.skill_id,
                    "skill_text": m.skill_text,
                    "s": m.s,
                    "sentence": m.sentence,
                    "pred": full.level.lower(),
                    "source": full.source,
                    "rules_pred": rules.level.lower(),
                    "rules_source": rules.source,
                    "gold": "",
                }
            )
    return out


def _key(r: dict) -> tuple:
    return r["jd_id"], r["sentence"], r["skill_id"], int(r["s"])


def scores(pairs: list[tuple[str, str]]) -> dict:
    n = len(pairs)
    per = {}
    for label in ("required", "preferred"):
        tp = sum(g == p == label for g, p in pairs)
        fp = sum(p == label != g for g, p in pairs)
        fn = sum(g == label != p for g, p in pairs)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[label] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "support": tp + fn,
        }
    return {
        "n": n,
        "accuracy": round(sum(g == p for g, p in pairs) / n, 4) if n else 0.0,
        "macro_f1": round((per["required"]["f1"] + per["preferred"]["f1"]) / 2, 4),
        **per,
    }


def cmd_template(labeler: SkillLabeler) -> int:
    rows = predictions(labeler)
    with TEMPLATE.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} mention / {len({r['jd_id'] for r in rows})} JD → {TEMPLATE}")
    print(f"theo nguồn: {dict(Counter(r['source'] for r in rows).most_common())}")
    print("Điền cột gold rồi lưu thành data/eval/gold_mentions.csv, sau đó chạy `score`.")
    return 0


def cmd_score(labeler: SkillLabeler) -> int:
    if not GOLD.exists():
        print(f"Chưa có {GOLD}. Chạy `template`, gán tay cột gold rồi lưu thành file này.")
        return 2
    gold = {_key(r): r["gold"].strip().lower() for r in csv.DictReader(GOLD.open(encoding="utf-8"))}
    bad = {g for g in gold.values() if g not in LABELS}
    if bad:
        print(f"Cột gold có giá trị lạ hoặc để trống: {bad}")
        return 2
    preds = {_key(r): r for r in predictions(labeler)}
    missing = gold.keys() - preds.keys()
    rows = [(gold[k], preds[k]) for k in gold.keys() & preds.keys()]
    full = scores([(g, p["pred"]) for g, p in rows])
    rules = scores([(g, p["rules_pred"]) for g, p in rows])
    hard = [(g, p) for g, p in rows if p["rules_source"] in HARD or p["section"] == "NONE"]
    confusion = Counter((g, p["pred"]) for g, p in rows)
    by_source = defaultdict(list)
    for g, p in rows:
        by_source[p["source"]].append(g == p["pred"])

    print(f"Gold: {len(gold)} mention · khớp {len(rows)} · lệch câu (code đổi?) {len(missing)}")
    print(f"luật + {labeler.model_version}: {full}")
    print(f"chỉ luật: {rules}")
    hard_full = scores([(g, p["pred"]) for g, p in hard])
    hard_rules = scores([(g, p["rules_pred"]) for g, p in hard])
    print(
        f"lát khó ({len(hard)}): chỉ luật acc {hard_rules['accuracy']} · "
        f"luật + model acc {hard_full['accuracy']}"
    )
    print("ma trận nhầm (gold → pred):")
    for g in LABELS:
        print(f"  {g:10}" + "".join(f"{confusion[(g, p)]:>11}" for p in LABELS))
    print("đúng theo nguồn:", {s: f"{sum(v)}/{len(v)}" for s, v in by_source.items()})

    report = {
        "model_version": labeler.model_version,
        "n_gold": len(gold),
        "n_matched": len(rows),
        "full": full,
        "rules_only": rules,
        "hard_slice": {"n": len(hard), "full": hard_full, "rules_only": hard_rules},
        "confusion": {f"{g}->{p}": n for (g, p), n in confusion.items()},
        "by_source": {s: {"correct": sum(v), "n": len(v)} for s, v in by_source.items()},
        "targets": {
            "macro_f1": 0.85,
            "preferred_recall": 0.80,
            "note": "ngưỡng nhóm tự đặt, chưa có benchmark công bố",
        },
    }
    out = ROOT / "reports" / f"eval_{labeler.model_version}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] not in ("template", "score"):
        print(__doc__)
        return 2
    if not JDS.exists():
        print(f"Chưa có {JDS}: chạy scripts/build_jd_gold.py trước.")
        return 2
    labeler = SkillLabeler.default()
    return cmd_template(labeler) if argv[0] == "template" else cmd_score(labeler)


if __name__ == "__main__":
    sys.exit(main())
