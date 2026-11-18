"""Đo precision/recall của khử trùng gần trùng và chọn ngưỡng (S3-T05, US-14).

    # 1. Lấy mẫu 100 cặp từ toàn kho (CHỈ ĐỌC DB, không gộp gì)
    uv run python scripts/eval_dedup.py sample --out reports/s3_t05/pairs.csv
       → pairs.csv (cột "nhan" để trống) + pairs.html (xem hai tin cạnh nhau, chỗ khác tô màu)

    # 2. Mở pairs.html để đọc, điền cột "nhan" trong pairs.csv: 1 = cùng một tin, 0 = khác

    # 3. Chấm điểm luật hiện tại + thử các bộ ngưỡng (không cần DB)
    uv run python scripts/eval_dedup.py score reports/s3_t05/pairs.csv \
        --report reports/s3_t05/score.md

Chi tiết cách lấy mẫu và trọng số: src/ingestion/dedup_eval.py.
"""

import argparse
import csv
import difflib
import html
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion.dedup_eval import (  # noqa: E402
    BASELINE_RULE,
    CSV_FIELDS,
    CURRENT_RULE,
    MIN_SIMILARITY,
    STRATA,
    TITLE_GRID,
    Metrics,
    Rule,
    all_pairs,
    best_rule,
    evaluate,
    read_labels,
    rule_grid,
    sample_pairs,
)
from ingestion.near_dedup import JobDoc  # noqa: E402

# Tin đang mở chưa bị gộp + tin ĐÃ bị gộp (để đo cả những gì luật đã gộp trước đó).
_DOCS_SQL = """
select j.id, j.company_id,
       coalesce(array_agg(distinct l.province_code)
                filter (where l.province_code is not null), '{}'),
       j.title,
       coalesce(j.jd_text,
                concat_ws(E'\\n', j.description, j.requirements, j.preferred, j.benefits)),
       j.duplicate_of,
       c.name
from core.jobs j
left join core.companies c on c.id = j.company_id
left join core.job_locations l on l.job_id = j.id
where j.origin = 'crawled'
  and ((j.status = 'open' and j.duplicate_of is null) or j.duplicate_of is not null)
group by j.id, c.name
"""

_SOURCES_SQL = """
select s.job_id, string_agg(o.code, ' | ' order by o.code), string_agg(s.url, ' | ' order by o.code)
from core.job_sources s join ops.sources o on o.id = s.source_id
where s.job_id = any(%s)
group by s.job_id
"""


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}"


def _database_url() -> str | None:
    """Như ingestion.crawl._database_url nhưng không import crawler (ít thư viện)."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def cmd_sample(args) -> int:
    dsn = _database_url()
    if not dsn:
        print("thiếu DATABASE_URL (biến môi trường hoặc file .env)", file=sys.stderr)
        return 2
    import psycopg

    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, prepare_threshold=None) as conn:
        conn.read_only = True
        rows = conn.execute(_DOCS_SQL).fetchall()
        docs = [
            JobDoc(id=r[0], company_id=r[1], provinces=frozenset(r[2]), title=r[3], text=r[4] or "")
            for r in rows
        ]
        meta = {
            r[0]: {"dup_of": r[5], "company": r[6] or "", "doc": d}
            for r, d in zip(rows, docs, strict=True)
        }
        pairs = all_pairs(docs)
        sampled = sample_pairs(pairs, total=args.n, seed=args.seed)
        ids = sorted({i for p, *_ in sampled for i in (p.job_a, p.job_b)})
        srcs = {r[0]: (r[1], r[2]) for r in conn.execute(_SOURCES_SQL, (ids,))}

    def root(i: int) -> int:
        return meta[i]["dup_of"] or i

    counts = {name: 0 for name, *_ in STRATA}
    for p in pairs:
        for name, lo, hi, _ in STRATA:
            if lo <= p.similarity < hi:
                counts[name] += 1
    merged_now = sum(1 for p in pairs if root(p.job_a) == root(p.job_b))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for n, (p, name, size, taken) in enumerate(sampled, start=1):
            a, b = meta[p.job_a], meta[p.job_b]
            w.writerow(
                {
                    "pair_id": n,
                    "tang": name,
                    "so_cap_tang": size,
                    "so_cap_mau_tang": taken,
                    "job_a": p.job_a,
                    "job_b": p.job_b,
                    "do_giong": f"{p.similarity:.4f}",
                    "do_giong_chuc_danh": f"{p.title_similarity:.4f}",
                    "so_tu_it_hon": p.min_tokens,
                    "quyet_dinh_hien_tai": CURRENT_RULE.decide(
                        p.similarity, p.title_similarity, p.min_tokens
                    ),
                    "da_gop": int(root(p.job_a) == root(p.job_b)),
                    "cong_ty": a["company"],
                    "chuc_danh_a": a["doc"].title,
                    "chuc_danh_b": b["doc"].title,
                    "nguon_a": srcs.get(root(p.job_a), ("", ""))[0],
                    "nguon_b": srcs.get(root(p.job_b), ("", ""))[0],
                    "url_a": srcs.get(root(p.job_a), ("", ""))[1],
                    "url_b": srcs.get(root(p.job_b), ("", ""))[1],
                    "nhan": "",
                    "ghi_chu": "",
                }
            )
    html_path = out.with_suffix(".html")
    html_path.write_text(_render_html(sampled, meta), encoding="utf-8")

    print(
        f"[eval-dedup] tin đã so: {len(docs)} · cặp cùng công ty, chung tỉnh"
        f" ≥ {MIN_SIMILARITY:.2f}: {len(pairs)}"
    )
    for name, lo, hi, _ in STRATA:
        taken = sum(1 for _, s, *_ in sampled if s == name)
        print(f"  {name:12} {lo:.2f}–{min(hi, 1):.2f}: {counts[name]:5} cặp · lấy mẫu {taken}")
    print(f"  cặp đã được gộp trước đó (cùng tin gốc): {merged_now}")
    print(f"  → {out}  (điền cột 'nhan')\n  → {html_path}  (mở để đọc)")
    return 0


def _diff_html(a: str, b: str) -> tuple[str, str]:
    wa, wb = a.split(), b.split()
    sm = difflib.SequenceMatcher(a=wa, b=wb, autojunk=False)
    out_a, out_b = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        ta = html.escape(" ".join(wa[i1:i2]))
        tb = html.escape(" ".join(wb[j1:j2]))
        if op == "equal":
            out_a.append(ta)
            out_b.append(tb)
        else:
            if ta:
                out_a.append(f"<del>{ta}</del>")
            if tb:
                out_b.append(f"<ins>{tb}</ins>")
    return " ".join(out_a), " ".join(out_b)


def _render_html(sampled, meta) -> str:
    parts = [
        "<!DOCTYPE html><html lang='vi'><meta charset='utf-8'><title>S3-T05 cặp tin</title>",
        "<style>body{font:14px/1.5 system-ui;margin:24px;max-width:1400px}"
        "section{border-top:2px solid #ccc;padding:12px 0}"
        ".g{display:grid;grid-template-columns:1fr 1fr;gap:16px}"
        ".t{white-space:pre-wrap;background:#fafafa;padding:8px;max-height:420px;overflow:auto}"
        "del{background:#fdd;text-decoration:none}ins{background:#dfd;text-decoration:none}"
        "h3{margin:4px 0}.m{color:#555}</style>",
        "<h1>S3-T05 · cặp tin cần gán nhãn</h1>",
        "<p>Điền cột <b>nhan</b> trong file CSV cùng tên: <b>1</b> = cùng một tin tuyển dụng "
        "(cùng vị trí, cùng đợt tuyển, chỉ khác cách viết/nguồn), <b>0</b> = hai tin khác nhau "
        "(khác cấp bậc, khác chuyên môn, khác địa điểm làm việc cụ thể, khác đợt tuyển). "
        "Đỏ = chỉ có ở tin A, xanh = chỉ có ở tin B.</p>",
    ]
    for n, (p, name, *_rest) in enumerate(sampled, start=1):
        a, b = meta[p.job_a], meta[p.job_b]
        ta, tb = _diff_html(a["doc"].text, b["doc"].text)
        decision = CURRENT_RULE.decide(p.similarity, p.title_similarity, p.min_tokens)
        parts.append(
            f"<section id='p{n}'><h2>#{n} · {html.escape(a['company'])}</h2>"
            f"<p class='m'>tầng {name} · độ giống {p.similarity:.3f} · chức danh "
            f"{p.title_similarity:.2f} · {p.min_tokens} từ · luật hiện tại: <b>{decision}</b></p>"
            "<div class='g'>"
            f"<div><h3>A · #{p.job_a} · {html.escape(a['doc'].title)}</h3>"
            f"<div class='t'>{ta}</div></div>"
            f"<div><h3>B · #{p.job_b} · {html.escape(b['doc'].title)}</h3>"
            f"<div class='t'>{tb}</div></div></div></section>"
        )
    return "\n".join(parts)


def _metrics_row(m: Metrics) -> str:
    return (
        f"| {m.rule.merge:.2f} | {m.rule.title:.1f} | {m.rule.min_tokens} | {_pct(m.precision)} "
        f"| {_pct(m.precision_low)} | {_pct(m.recall)} | {_pct(m.recall_with_review)} "
        f"| {m.merged_sampled} ({m.merged_wrong} nhầm) | {m.merged_est:.0f} |"
    )


def cmd_score(args) -> int:
    rows, warnings = read_labels(args.labels)
    for w in warnings:
        print(f"cảnh báo: {w}", file=sys.stderr)
    if not rows:
        print("chưa có cặp nào gán nhãn 0/1", file=sys.stderr)
        return 2

    header = (
        "| Gộp ≥ | Chức danh ≥ | Số từ ≥ | Precision | Cận dưới 95% | Recall (gộp) "
        "| Recall (gộp + hàng chờ) | Cặp mẫu bị gộp | Cặp gộp ước tính toàn kho |\n"
        "|---|---|---|---|---|---|---|---|---|"
    )
    current = evaluate(rows, CURRENT_RULE)
    grid = [evaluate(rows, r) for r in rule_grid()]
    best = best_rule(grid, target=args.target)

    by_stratum: dict[str, list[int]] = {}
    for r in rows:
        s = by_stratum.setdefault(r.stratum, [0, 0])
        s[0] += 1
        s[1] += int(r.is_dup)

    lines = [
        f"Số cặp có nhãn: {len(rows)} · trùng thật: {sum(r.is_dup for r in rows)}",
        "",
        "| Tầng | Cặp có nhãn | Trùng thật | Tỷ lệ |",
        "|---|---|---|---|",
    ]
    for name, *_ in STRATA:
        n, d = by_stratum.get(name, [0, 0])
        lines.append(f"| {name} | {n} | {d} | {_pct(d / n if n else None)} |")
    baseline = evaluate(rows, BASELINE_RULE)
    lines += [
        "",
        "### Luật hiện tại và luật S3-T04",
        "",
        "| Luật " + header.split("\n")[0],
        "|---" + header.split("\n")[1],
        "| hiện tại " + _metrics_row(current),
        "| S3-T04 (gộp ≥ 0,85) " + _metrics_row(baseline),
        "",
    ]
    for name, m in (("hiện tại", current), ("S3-T04", baseline)):
        if m.fp_examples:
            pairs = ", ".join(f"#{p.job_a}~#{p.job_b} ({p.similarity:.2f})" for p in m.fp_examples)
            lines += [f"Gộp nhầm ({name}): {pairs}", ""]
    ok = sorted(
        (m for m in grid if m.precision is not None and m.precision >= args.target),
        key=lambda m: (-(m.recall or 0), -m.rule.merge, -m.rule.title, -m.rule.min_tokens),
    )
    lines += [
        f"### Các bộ ngưỡng đạt precision ≥ {args.target} (10 bộ recall cao nhất)",
        "",
        header,
        *[_metrics_row(m) for m in ok[:10]],
        "",
        "### Nới điều kiện chức danh (cùng ngưỡng gộp 0,85 và 0,45)",
        "",
        header,
    ]
    for merge in (0.85, 0.45):
        for title in TITLE_GRID:
            m = evaluate(rows, Rule(merge=merge, title=title))
            lines.append(_metrics_row(m))
    lines.append("")
    if best:
        lines.append(
            f"**Đề xuất:** {best.rule.label()} → precision {_pct(best.precision)}, "
            f"recall {_pct(best.recall)}"
        )
    else:
        lines.append(f"**Không bộ ngưỡng nào đạt precision ≥ {args.target}.**")
    text = "\n".join(lines)
    print(text)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    return 0 if current.precision is None or current.precision >= args.target else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sample = sub.add_parser("sample", help="lấy mẫu cặp từ DB (chỉ đọc)")
    p_sample.add_argument("--out", default="reports/s3_t05/pairs.csv")
    p_sample.add_argument("--n", type=int, default=100)
    p_sample.add_argument("--seed", type=int, default=20261118)
    p_score = sub.add_parser("score", help="tính precision/recall từ CSV đã gán nhãn")
    p_score.add_argument("labels", type=Path)
    p_score.add_argument("--target", type=float, default=0.95)
    p_score.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    return cmd_sample(args) if args.cmd == "sample" else cmd_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
