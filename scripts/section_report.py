"""Đo bộ tách section (S2-D03) trên bộ 50 JD gán tay data/eval/jd_gold.jsonl.

Tạo bộ mẫu trước: PYTHONPATH=src uv run python scripts/build_jd_gold.py

Một JD "tách đúng" khi ≥ 95% câu có nội dung nằm đúng section VÀ mọi section có trong nhãn
đều được tìm thấy. Mục tiêu: ≥ 90% JD tách đúng. Heading con bị bộ tách bỏ ra khỏi nội dung
thì không tính lỗi (xem is_subheading).

Chạy: PYTHONPATH=src uv run python scripts/section_report.py [--show-errors]
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from skillkit.sections import assign_lines

GOLD = Path(__file__).resolve().parents[1] / "data" / "eval" / "jd_gold.jsonl"
LINE_TARGET, DOC_TARGET = 0.95, 0.90
_BULLETS = "-–•*+·"


def is_subheading(text: str) -> bool:
    """Heading con trong nội dung ("Kỹ năng mềm:", "AI & Innovation Focus:"): không chấm.

    Tiêu chí độc lập với bộ tách: kết thúc bằng ":" hoặc ≤ 6 từ không có dấu câu cuối,
    và không bắt đầu bằng gạch đầu dòng.
    """
    t = text.strip().strip("*_ ")
    if not t or t[0] in _BULLETS:
        return False
    return t.endswith(":") or (len(t.split()) <= 6 and not t.endswith((".", ";", ",", "!", "?")))


def predicted_labels(sample: dict) -> list[tuple[str, str, str]]:
    """(nội dung, nhãn đúng, nhãn dự đoán) cho từng câu có nội dung của nhãn đúng."""
    predicted = [
        (text, label) for text, label in assign_lines(sample["text"]) if label != "heading"
    ]
    out, j = [], 0
    for text, gold in sample["items"]:
        if gold == "heading":
            continue
        guess = "heading"  # cả câu bị coi là heading
        for k in range(j, len(predicted)):
            if predicted[k][0] in text or text in predicted[k][0]:
                guess, j = predicted[k][1], k + 1
                break
        if guess == "heading" and is_subheading(text):
            continue  # bộ tách coi heading con là heading: không phạt
        out.append((text, gold, guess))
    return out


def evaluate(samples: list[dict]) -> tuple[list[dict], Counter]:
    results, confusion = [], Counter()
    for s in samples:
        rows = predicted_labels(s)
        correct = sum(g == p for _, g, p in rows)
        gold_sections = {g for _, g, _ in rows}
        found = {p for _, _, p in rows}
        ok_lines = correct / len(rows) if rows else 1.0
        missing = sorted(gold_sections - found - {"other"})
        results.append(
            {
                "id": s["id"],
                "style": s["style"],
                "line_acc": ok_lines,
                "missing": missing,
                "ok": ok_lines >= LINE_TARGET and not missing,
                "errors": [(t, g, p) for t, g, p in rows if g != p],
            }
        )
        confusion.update((g, p) for _, g, p in rows)
    return results, confusion


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show-errors", action="store_true")
    args = parser.parse_args()
    samples = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines()]
    results, confusion = evaluate(samples)

    ok = sum(r["ok"] for r in results)
    lines = sum(n for n in confusion.values())
    right = sum(n for (g, p), n in confusion.items() if g == p)
    print(
        f"JD tách đúng: {ok}/{len(results)} = {ok / len(results):.0%} (mục tiêu ≥ {DOC_TARGET:.0%})"
    )
    print(f"Câu đúng section: {right}/{lines} = {right / lines:.1%}")
    by_style: dict[str, list[bool]] = {}
    for r in results:
        by_style.setdefault(r["style"], []).append(r["ok"])
    print("Theo kiểu trình bày:", {k: f"{sum(v)}/{len(v)}" for k, v in by_style.items()})
    print("Nhầm lẫn (đúng → đoán):", {f"{g}→{p}": n for (g, p), n in confusion.items() if g != p})
    for r in results:
        if not r["ok"]:
            print(
                f"  ✗ {r['id']} [{r['style']}] câu đúng {r['line_acc']:.0%}, thiếu {r['missing']}"
            )
            if args.show_errors:
                for text, gold, guess in r["errors"]:
                    print(f"      {gold:>12} → {guess:<12} {text[:90]}")


if __name__ == "__main__":
    main()
