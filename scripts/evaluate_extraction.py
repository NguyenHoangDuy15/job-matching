"""S2-D07: F1 trích xuất kỹ năng (Tầng 1, từ điển + FlashText) trên 50 JD của jd_gold.jsonl.

    uv run python scripts/evaluate_extraction.py template   # tạo file ghi kỹ năng máy bỏ sót
    uv run python scripts/evaluate_extraction.py score      # chấm sau khi đã điền

Đơn vị chấm: cặp (JD, kỹ năng) hiện thành THẺ, tức mức required hoặc preferred.
  - Thẻ máy: pipeline hiện tại (label_text) trên nội dung JD.
  - Thẻ chuẩn = (a) kỹ năng máy tìm thấy mà người gán S2-D04 cho required/preferred
                 (data/eval/gold_mentions.csv)
              + (b) kỹ năng người đọc JD thấy mà máy bỏ sót (data/eval/bo_sot.csv).
Precision = thẻ đúng / thẻ máy; recall = thẻ đúng / thẻ chuẩn. Tính hai kiểu: chỉ kỹ năng,
và kỹ năng + đúng mức.

Bước template tạo:
  data/eval/bo_sot.csv     một dòng mẫu cho mỗi JD; người gán thêm dòng cho từng kỹ năng bỏ sót.
  data/eval/bo_sot_jd.md   nội dung JD (chỉ phần Yêu cầu / Ưu tiên / Mô tả) + thẻ máy đã gắn.
Hai file có nội dung JD nên ở data/ (không lên git). Bước score ghi nhãn chuẩn KHÔNG kèm câu JD
vào tests/fixtures/jd_gold/skills_gold.csv, và kết quả vào reports/.
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skillkit.levels.pipeline import SKILLS_YAML, SkillLabeler  # noqa: E402
from skillkit.taxonomy import Taxonomy, load_taxonomy  # noqa: E402

EVAL = ROOT / "data" / "eval"
JDS = EVAL / "jd_gold.jsonl"
GOLD_MENTIONS = EVAL / "gold_mentions.csv"
BO_SOT = EVAL / "bo_sot.csv"
BO_SOT_MD = EVAL / "bo_sot_jd.md"
ERRORS = EVAL / "extraction_errors.csv"
FIXTURE = ROOT / "tests" / "fixtures" / "jd_gold" / "skills_gold.csv"
REPORTS = ROOT / "reports"
CARD = ("required", "preferred")
RANK = {"required": 3, "preferred": 2, "mentioned": 1, "drop": 0}
BO_SOT_COLS = ["jd_id", "ky_nang_bo_sot", "muc", "note"]
_SECTION_VI = {
    "description": "Mô tả",
    "requirements": "Yêu cầu",
    "preferred": "Ưu tiên",
    "benefits": "Quyền lợi",
    "other": "Khác",
}
# Gợi ý từ có dáng tên công nghệ: có chữ hoa giữa từ, viết hoa toàn bộ, hoặc có + # . số.
_TECHY = re.compile(r"(?<![\w.])([A-Za-z][A-Za-z0-9]*(?:[+#]+|[.\-/][A-Za-z0-9]+)*)(?![\w])")


def _key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).lower().split())


# ----------------------------------------------------------------------------- dữ liệu


def load_jds(path: Path = JDS) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def machine_cards(labeler: SkillLabeler, jds: list[dict]) -> dict[tuple[str, str], str]:
    """(jd_id, skill_id) → level của các thẻ máy gắn."""
    out = {}
    for jd in jds:
        for row in labeler.label_text(jd["id"], jd["text"]):
            if row.level in CARD:
                out[(jd["id"], row.skill_id)] = row.level
    return out


def gold_from_mentions(path: Path = GOLD_MENTIONS) -> dict[tuple[str, str], str]:
    """Gộp nhãn từng lần nhắc của S2-D04 về mức cao nhất mỗi (jd, kỹ năng); giữ thẻ."""
    best: dict[tuple[str, str], str] = {}
    with path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            label = (r["gold"] or "").strip().lower()
            key = (r["jd_id"], r["skill_id"])
            if label in RANK and RANK[label] > RANK.get(best.get(key, "drop"), 0):
                best[key] = label
            best.setdefault(key, label if label in RANK else "drop")
    return {k: v for k, v in best.items() if v in CARD}


class NameResolver:
    """Tên người gán viết → skill_id trong từ điển, hoặc None nếu ngoài từ điển."""

    def __init__(self, taxonomy: Taxonomy, labeler: SkillLabeler) -> None:
        self.terms: dict[str, str] = {}
        for skill in taxonomy:
            if skill.level == 1:
                continue
            for term in [skill.id, *skill.terms()]:
                self.terms.setdefault(_key(term), skill.id)
        self.matcher = labeler.matcher

    def resolve(self, name: str) -> tuple[str | None, str]:
        """(skill_id, cách nhận): exact = đúng tên/alias/id; partial = từ điển tìm thấy một
        kỹ năng trong cụm; none = ngoài từ điển."""
        key = _key(name)
        if key in self.terms:
            return self.terms[key], "exact"
        found = self.matcher.skills(name)
        if len(found) == 1:
            return found[0], "partial"
        return None, "none"


def read_bo_sot(path: Path = BO_SOT) -> list[dict]:
    """Các dòng đã điền ky_nang_bo_sot (bỏ dòng mẫu để trống). Báo lỗi nếu mức sai."""
    rows, errors = [], []
    with path.open(encoding="utf-8-sig") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            name = (r.get("ky_nang_bo_sot") or "").strip()
            if not name:
                continue
            level = (r.get("muc") or "").strip().lower()
            level = {
                "bat buoc": "required",
                "bắt buộc": "required",
                "uu tien": "preferred",
                "ưu tiên": "preferred",
                "r": "required",
                "p": "preferred",
            }.get(level, level)
            if level not in CARD:
                errors.append(f"dòng {i}: muc '{r.get('muc')}' phải là required hoặc preferred")
            rows.append({**r, "ky_nang_bo_sot": name, "muc": level, "_line": i})
    if errors:
        raise ValueError("\n".join(errors))
    return rows


# ----------------------------------------------------------------------------- chấm


def prf(tp: int, n_pred: int, n_gold: int) -> dict:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {
        "precision": round(p, 3),
        "recall": round(r, 3),
        "f1": round(f, 3),
        "tp": tp,
        "pred": n_pred,
        "gold": n_gold,
    }


def score_sets(pred: dict, gold: dict) -> dict:
    """pred/gold: (jd, skill) → level. Trả kết quả chỉ-kỹ-năng và kỹ-năng+mức."""
    both = set(pred) & set(gold)
    exact = sum(pred[k] == gold[k] for k in both)
    return {
        "skill": prf(len(both), len(pred), len(gold)),
        "skill_level": prf(exact, len(pred), len(gold)),
    }


def build_gold(
    from_mentions: dict, bo_sot: list[dict], resolver: NameResolver, pred: dict
) -> tuple[dict, list[dict], list[str]]:
    """Thẻ chuẩn = (a) + (b). Kỹ năng ngoài từ điển có khóa 'new:<tên>'."""
    gold = dict(from_mentions)
    added, warnings = [], []
    for r in bo_sot:
        sid, how = resolver.resolve(r["ky_nang_bo_sot"])
        key = (r["jd_id"], sid or f"new:{_key(r['ky_nang_bo_sot'])}")
        if sid and key in pred:
            warnings.append(
                f"{r['jd_id']} '{r['ky_nang_bo_sot']}': máy đã có thẻ {sid}, không tính bỏ sót"
            )
            continue
        if key in gold:
            continue
        gold[key] = r["muc"]
        added.append({**r, "skill_id": sid or "", "match": how})
    return gold, added, warnings


def by_style(pred: dict, gold: dict, style_of: dict[str, str]) -> dict:
    out = {}
    for style in sorted(set(style_of.values())):
        ids = {j for j, s in style_of.items() if s == style}
        out[style] = score_sets(
            {k: v for k, v in pred.items() if k[0] in ids},
            {k: v for k, v in gold.items() if k[0] in ids},
        )["skill"]
    return out


def macro_f1(pred: dict, gold: dict, jd_ids: list[str]) -> float:
    scores = []
    for j in jd_ids:
        p = {k: v for k, v in pred.items() if k[0] == j}
        g = {k: v for k, v in gold.items() if k[0] == j}
        if p or g:
            scores.append(score_sets(p, g)["skill"]["f1"])
    return round(sum(scores) / len(scores), 3) if scores else 0.0


# ----------------------------------------------------------------------------- lệnh


def cmd_template(labeler: SkillLabeler, force: bool) -> int:
    if BO_SOT.exists() and not force:
        print(f"{BO_SOT} đã có (có thể đã điền). Thêm --force nếu muốn tạo lại.")
        return 1
    jds = load_jds()
    names = {s.id: s.name or s.id for s in load_taxonomy(SKILLS_YAML)}
    md = [
        "# S2-D07: tìm kỹ năng máy bỏ sót\n\n"
        "Mỗi JD: đọc phần **Yêu cầu** và **Ưu tiên** (phần Mô tả để tham khảo), so với thẻ "
        "máy đã gắn. Kỹ năng nào JD yêu cầu mà KHÔNG có trong thẻ → thêm một dòng vào "
        "`data/eval/bo_sot.csv`. Mục *Gợi ý* chỉ là từ có dáng tên công nghệ chưa thành "
        "thẻ, có thể sai hoặc thiếu: vẫn phải đọc hết JD.\n"
    ]
    with BO_SOT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BO_SOT_COLS)
        writer.writeheader()
        for n, jd in enumerate(jds, 1):
            cards = labeler.label_text(jd["id"], jd["text"])
            req = [names.get(c.skill_id, c.skill_id) for c in cards if c.level == "required"]
            pref = [names.get(c.skill_id, c.skill_id) for c in cards if c.level == "preferred"]
            found = {_key(t) for c in cards for t in [c.skill_id, names.get(c.skill_id, "")]}
            md.append(f"\n---\n\n## {n}/{len(jds)} · `{jd['id']}`\n")
            md.append(f"\n- **Máy gắn bắt buộc:** {', '.join(req) or '(trống)'}")
            md.append(f"\n- **Máy gắn ưu tiên:** {', '.join(pref) or '(trống)'}\n")
            hints: list[str] = []
            current = None
            items = jd["items"]
            for i, (text, label) in enumerate(items):
                if label == "heading":
                    nxt = next((lb for _, lb in items[i + 1 :] if lb != "heading"), "other")
                    if nxt not in ("benefits", "other"):
                        md.append(f"\n\n**{text}**\n")
                    current = None
                    continue
                if label in ("benefits", "other"):
                    continue
                if label != current:
                    md.append(f"\n*[{_SECTION_VI[label]}]*\n")
                    current = label
                md.append(f"\n- {text}")
                if label in ("requirements", "preferred"):
                    for tok in _TECHY.findall(text):
                        techy = any(c.isdigit() or c in "+#./" for c in tok) or (
                            sum(c.isupper() for c in tok) >= 2
                        )
                        if techy and _key(tok) not in found and tok not in hints:
                            hints.append(tok)
            md.append(f"\n\n*Gợi ý (kiểm lại):* {', '.join(hints) or '—'}\n")
            writer.writerow({"jd_id": jd["id"], "ky_nang_bo_sot": "", "muc": "", "note": ""})
    BO_SOT_MD.write_text("".join(md), encoding="utf-8")
    print(f"{len(jds)} JD → {BO_SOT_MD}\nfile điền → {BO_SOT}")
    return 0


def cmd_score(labeler: SkillLabeler, report_name: str) -> int:
    jds = load_jds()
    pred = machine_cards(labeler, jds)
    resolver = NameResolver(load_taxonomy(SKILLS_YAML), labeler)
    try:
        bo_sot = read_bo_sot()
    except ValueError as e:
        print(f"LỖI trong {BO_SOT}:\n{e}")
        return 1
    from_mentions = gold_from_mentions()
    gold, added, warnings = build_gold(from_mentions, bo_sot, resolver, pred)
    for w in warnings:
        print("  ! " + w)

    style_of = {jd["id"]: jd["style"] for jd in jds}
    result = score_sets(pred, gold)
    fp = sorted(k for k in pred if k not in gold)
    fn = sorted(k for k in gold if k not in pred)
    fn_cause = Counter(
        "ngoai_tu_dien"
        if k[1].startswith("new:")
        else ("bo_sot_khi_doc_so_bo" if k in from_mentions else "co_trong_tu_dien_khong_bat_duoc")
        for k in fn
    )
    level_wrong = sorted(k for k in set(pred) & set(gold) if pred[k] != gold[k])
    new_names = Counter(k[1][4:] for k in fn if k[1].startswith("new:"))
    in_dict_missed = Counter(
        f"{a['ky_nang_bo_sot']} → {a['skill_id']}" for a in added if a["skill_id"]
    )

    report = {
        "model_version": labeler.model_version,
        "jd": len(jds),
        "jd_co_the_chuan": len({k[0] for k in gold}),
        "the_may": len(pred),
        "the_chuan": len(gold),
        "the_chuan_tu_gold_d04": len(from_mentions),
        "the_chuan_bo_sung": len(added),
        "micro": result,
        "macro_f1_theo_jd": macro_f1(pred, gold, [jd["id"] for jd in jds]),
        "theo_kieu_trinh_bay": by_style(pred, gold, style_of),
        "loi": {
            "the_sai": [list(k) for k in fp],
            "sai_muc": [[*k, pred[k], gold[k]] for k in level_wrong],
            "bo_sot_theo_nguyen_nhan": dict(fn_cause),
            "ngoai_tu_dien_hay_gap": new_names.most_common(30),
            "co_trong_tu_dien_ma_khong_bat": in_dict_missed.most_common(30),
        },
    }
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{report_name}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Nhãn chuẩn, không kèm câu JD: được lên git.
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    with FIXTURE.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["jd_id", "skill_id", "skill_name", "level", "nguon"])
        names = {
            a["jd_id"] + "|" + (a["skill_id"] or "new:" + _key(a["ky_nang_bo_sot"])): a[
                "ky_nang_bo_sot"
            ]
            for a in added
        }
        for (j, s), lvl in sorted(gold.items()):
            src = "gold_d04" if (j, s) in from_mentions else "bo_sot_d07"
            w.writerow(
                [
                    j,
                    "" if s.startswith("new:") else s,
                    names.get(f"{j}|{s}", s[4:] if s.startswith("new:") else ""),
                    lvl,
                    src,
                ]
            )

    with ERRORS.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["loai", "jd_id", "skill", "may", "chuan"])
        for k in fp:
            w.writerow(["the_sai", k[0], k[1], pred[k], ""])
        for k in fn:
            w.writerow(["bo_sot", k[0], k[1], "", gold[k]])
        for k in level_wrong:
            w.writerow(["sai_muc", k[0], k[1], pred[k], gold[k]])

    s, sl = result["skill"], result["skill_level"]
    print(f"model_version: {labeler.model_version}")
    print(
        f"Thẻ máy {len(pred)} · thẻ chuẩn {len(gold)} "
        f"({len(from_mentions)} từ gold D04 + {len(added)} bỏ sót bổ sung)"
    )
    print(f"Chỉ kỹ năng:   P {s['precision']}  R {s['recall']}  F1 {s['f1']}")
    print(f"Kỹ năng + mức: P {sl['precision']}  R {sl['recall']}  F1 {sl['f1']}")
    print(f"Macro-F1 theo JD: {report['macro_f1_theo_jd']}")
    print(f"Bỏ sót theo nguyên nhân: {dict(fn_cause)}")
    print(f"→ {out}\n→ {FIXTURE}\n→ {ERRORS}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cmd", choices=["template", "score"])
    parser.add_argument("--force", action="store_true", help="template: ghi đè bo_sot.csv")
    parser.add_argument("--name", default="eval_extraction_lan1", help="tên file báo cáo")
    args = parser.parse_args(argv)
    labeler = SkillLabeler.default()
    if args.cmd == "template":
        return cmd_template(labeler, args.force)
    return cmd_score(labeler, args.name)


if __name__ == "__main__":
    sys.exit(main())
