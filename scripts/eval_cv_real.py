"""S3-D06: thử 10 CV THẬT (bạn bè, đã xin phép), đo độ đúng kỹ năng, tìm alias thiếu.

    # 1. Chép CV vào data/cv_real/ (PDF/DOCX; thư mục data/ không lên git)
    uv run python scripts/eval_cv_real.py run          # đọc CV, tạo file để chấm
    # 2. Mở data/eval/cv_real/cvrXX.md (văn bản ĐÃ che PII + kỹ năng máy tìm), điền 3 file CSV
    uv run python scripts/eval_cv_real.py score        # tính độ đúng + gợi ý alias

Riêng tư: mỗi CV đổi tên thành cvr01..cvr10 (bảng đối chiếu tên file chỉ ở data/eval/cv_real/);
file để chấm chỉ có văn bản ĐÃ che PII; báo cáo reports/ chỉ có số liệu và tên kỹ năng.

File để chấm (data/eval/):
  cv_real_skills.csv   mỗi kỹ năng máy gắn một dòng → điền `dung` (y/n) và `muc_dung`
                       (strong = dùng trong kinh nghiệm/dự án, listed = chỉ liệt kê) nếu máy sai mức
  cv_real_missing.csv  kỹ năng có trong CV mà máy bỏ sót → `ky_nang` + `cach_viet` (chữ đúng như
                       trong CV) + `muc`; một CV nhiều dòng
  cv_real_meta.csv     mỗi CV một dòng → `so_nam_dung`, `chuc_danh_dung`, `section_dung` (y/n),
                       `pii_lo` (y nếu văn bản đã che còn lộ tên/SĐT/email/địa chỉ)
"""

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

SRC = ROOT / "data" / "cv_real"
OUT = ROOT / "data" / "eval" / "cv_real"
EVAL = ROOT / "data" / "eval"
SKILLS_CSV = EVAL / "cv_real_skills.csv"
MISSING_CSV = EVAL / "cv_real_missing.csv"
META_CSV = EVAL / "cv_real_meta.csv"
REPORT_JSON = ROOT / "reports" / "eval_cv_real.json"
SKILL_COLS = [
    "cv",
    "skill_id",
    "ten",
    "muc_may",
    "muc_section",
    "ngu_canh",
    "dung",
    "muc_dung",
    "note",
]
MISSING_COLS = ["cv", "ky_nang", "cach_viet", "muc", "note"]
META_COLS = ["cv", "trang_thai", "so_nam_may", "so_nam_dung", "chuc_danh_may", "chuc_danh_dung",
             "section_dung", "pii_lo", "note"]  # fmt: skip


def _write(path: Path, cols: list[str], rows: list[dict], force: bool) -> None:
    if path.exists() and not force:
        print(f"  giữ nguyên {path.name} (đã có, có thể đã điền; --force để ghi đè)")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def cmd_run(args) -> int:
    from cvparser.pipeline import parse_cv

    src = Path(args.dir)
    files = sorted(p for p in src.glob("*") if p.suffix.lower() in (".pdf", ".docx", ".doc"))
    if not files:
        print(f"chưa có CV nào trong {src} (chép 10 CV PDF/DOCX vào đây, đã xin phép chủ CV)")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    skills_rows, meta_rows, missing_rows, mapping = [], [], [], []
    for i, path in enumerate(files, 1):
        cid = f"cvr{i:02d}"
        mapping.append({"cv": cid, "file": path.name})
        res = parse_cv(path.read_bytes(), filename=path.name, as_of=as_of)
        if res["status"] == "failed":
            meta_rows.append({"cv": cid, "trang_thai": f"failed:{res['error']['code']}"})
            err = res["error"]
            (OUT / f"{cid}.md").write_text(
                f"# {cid}: KHÔNG ĐỌC ĐƯỢC ({err['code']})\n\n{err['message_vi']}\n",
                encoding="utf-8",
            )
            print(f"  {cid}: failed {res['error']['code']}")
            continue
        p = res["profile"]
        lines = [
            f"# {cid}",
            "",
            f"- Chức danh máy đề xuất: **{p['target_title']}** ({p['target_title_source']})",
            f"- Số năm kinh nghiệm máy tính: **{p['years_exp']}** · khoảng: {p['years_ranges']}"
            f" · thực tập không tính: {p['internship_months']} tháng",
            f"- Section: {', '.join(res['sections'])}",
            "",
            "## Kỹ năng máy tìm (đối chiếu với văn bản bên dưới)",
            "",
        ]
        for s in p["skills"]:
            hl = s["evidence"][s["highlight"][0] : s["highlight"][1]]
            lines.append(
                f"- **{s['name']}** `{s['skill_id']}` · {s['evidence_level']} · {s['section']}"
                f'{" · " + s["context"] if s["context"] else ""} — "{s["evidence"]}" (chữ: {hl})'
            )
            skills_rows.append({
                "cv": cid, "skill_id": s["skill_id"], "ten": s["name"],
                "muc_may": s["evidence_level"], "muc_section": s["section"],
                "ngu_canh": s["context"] or "",
            })  # fmt: skip
        lines += ["", "## Văn bản CV (ĐÃ che PII)", "", "```", res["text_redacted"], "```", ""]
        (OUT / f"{cid}.md").write_text("\n".join(lines), encoding="utf-8")
        meta_rows.append({
            "cv": cid, "trang_thai": "parsed", "so_nam_may": p["years_exp"],
            "chuc_danh_may": p["target_title"] or "",
        })  # fmt: skip
        missing_rows.append({"cv": cid})
        print(f"  {cid}: {len(p['skills'])} kỹ năng · {p['years_exp']} năm · {p['target_title']!r}")
    _write(OUT / "_map.csv", ["cv", "file"], mapping, force=True)
    _write(SKILLS_CSV, SKILL_COLS, skills_rows, args.force)
    _write(MISSING_CSV, MISSING_COLS, missing_rows, args.force)
    _write(META_CSV, META_COLS, meta_rows, args.force)
    print(f"→ đọc {OUT}/cvrXX.md, điền {SKILLS_CSV.name}, {MISSING_CSV.name}, {META_CSV.name}")
    return 0


def score(skills: list[dict], missing: list[dict], meta: list[dict]) -> dict:
    """Số liệu từ 3 file đã điền. Dùng chung cho lệnh score và test."""
    from scripts.evaluate_extraction import NameResolver
    from skillkit.levels.pipeline import SKILLS_YAML, SkillLabeler
    from skillkit.taxonomy import load_taxonomy

    judged = [r for r in skills if (r.get("dung") or "").strip().lower() in ("y", "n")]
    correct = [r for r in judged if r["dung"].strip().lower() == "y"]
    wrong = [r for r in judged if r["dung"].strip().lower() == "n"]
    miss = [r for r in missing if (r.get("ky_nang") or r.get("cach_viet") or "").strip()]
    level_judged = correct
    level_ok = [r for r in correct if not (r.get("muc_dung") or "").strip()
                or r["muc_dung"].strip().lower() == r["muc_may"]]  # fmt: skip

    resolver = NameResolver(load_taxonomy(SKILLS_YAML), SkillLabeler.default(with_model=False))
    alias_gaps, new_skills = [], []
    for r in miss:
        name = (r.get("ky_nang") or r.get("cach_viet") or "").strip()
        sid, _ = resolver.resolve(name)
        written = (r.get("cach_viet") or name).strip()
        if sid:
            written_sid, _ = resolver.resolve(written)
            if written_sid != sid:  # có kỹ năng nhưng thiếu cách viết như trong CV
                alias_gaps.append({"skill_id": sid, "cach_viet": written.lower(), "cv": r["cv"]})
        else:
            new_skills.append({"ky_nang": name, "cach_viet": written, "cv": r["cv"]})

    years = [
        (float(m["so_nam_may"]), float(m["so_nam_dung"]))
        for m in meta
        if (m.get("so_nam_dung") or "").strip() and (m.get("so_nam_may") or "").strip()
    ]
    titles = [m for m in meta if (m.get("chuc_danh_dung") or "").strip()]
    title_ok = [m for m in titles if _title_ok(m)]
    p = len(correct) / len(judged) if judged else 0.0
    rec = len(correct) / (len(correct) + len(miss)) if correct or miss else 0.0
    return {
        "cv": len(meta),
        "doc_duoc": sum(m.get("trang_thai") == "parsed" for m in meta),
        "ky_nang_may": len(judged),
        "dung": len(correct),
        "sai": len(wrong),
        "bo_sot": len(miss),
        "precision": round(p, 3),
        "recall": round(rec, 3),
        "f1": round(2 * p * rec / (p + rec), 3) if p + rec else 0.0,
        "dung_muc": round(len(level_ok) / len(level_judged), 3) if level_judged else None,
        "so_nam_mae": round(sum(abs(a - b) for a, b in years) / len(years), 2) if years else None,
        "so_nam_lech_le_0_5": sum(abs(a - b) <= 0.5 for a, b in years),
        "so_nam_cham": len(years),
        "chuc_danh_dung": f"{len(title_ok)}/{len(titles)}",
        "section_dung": sum((m.get("section_dung") or "").strip().lower() == "y" for m in meta),
        "pii_lo": sum((m.get("pii_lo") or "").strip().lower() == "y" for m in meta),
        "sai_hay_gap": Counter(r["skill_id"] for r in wrong).most_common(15),
        "alias_thieu": alias_gaps,
        "ngoai_tu_dien": Counter(x["ky_nang"] for x in new_skills).most_common(30),
    }


def _title_ok(m: dict) -> bool:
    """`chuc_danh_dung` = y/đúng, hoặc ghi lại đúng chức danh máy đề xuất."""
    given = m["chuc_danh_dung"].strip()
    return given.lower() in ("y", "dung", "đúng") or given == (m.get("chuc_danh_may") or "").strip()


def cmd_score(args) -> int:
    for path in (SKILLS_CSV, MISSING_CSV, META_CSV):
        if not path.exists():
            print(f"thiếu {path} (chạy lệnh run trước)")
            return 2
    result = score(_read(SKILLS_CSV), _read(MISSING_CSV), _read(META_CSV))
    REPORT_JSON.parent.mkdir(exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    keys = ["cv", "doc_duoc", "precision", "recall", "f1", "dung_muc", "so_nam_mae",
            "chuc_danh_dung", "section_dung", "pii_lo"]  # fmt: skip
    print({k: result[k] for k in keys})
    print("Alias thiếu (thêm vào config/skills.yaml):")
    for a in result["alias_thieu"]:
        print(f"  {a['skill_id']}: + {a['cach_viet']!r}  ({a['cv']})")
    print("Ngoài từ điển:", result["ngoai_tu_dien"])
    print(f"→ {REPORT_JSON}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--as-of", help="ngày tính 'nay' (YYYY-MM-DD), mặc định hôm nay")
    run.add_argument("--force", action="store_true", help="ghi đè các file CSV đã điền")
    run.add_argument("--dir", default=str(SRC), help="thư mục CV (mặc định data/cv_real)")
    sub.add_parser("score")
    args = parser.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_score(args)


if __name__ == "__main__":
    sys.exit(main())
