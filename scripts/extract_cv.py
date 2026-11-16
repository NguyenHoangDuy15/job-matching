"""Trích văn bản nhiều CV song song và báo cáo chỉ số (S3-D01). Không in nội dung CV.

    uv run python scripts/extract_cv.py run tests/fixtures/cv/samples
    uv run python scripts/extract_cv.py run data/cv_real --workers 4 --out data/interim/cv_text
    uv run python scripts/extract_cv.py run tests/fixtures/cv/samples --repeat 5   # đo lô 50 CV
    uv run python scripts/extract_cv.py run file.pdf --print                         # xem văn bản

--out ghi văn bản và JSON từng file vào thư mục đó (nên để trong data/, không lên git).
--report ghi bảng chỉ số (markdown) ra file. Exit code 1 nếu có file lỗi.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cvparser.extract.batch import extract_many  # noqa: E402
from cvparser.extract.models import ExtractionResult, ExtractOptions  # noqa: E402

SUFFIXES = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}


def collect(paths: list[str]) -> list[Path]:
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(x for x in p.iterdir() if x.suffix.lower() in SUFFIXES)
        elif p.exists():
            out.append(p)
    return out


def row(name: str, r: ExtractionResult) -> dict:
    q = r.quality
    return {
        "file": name,
        "status": r.status,
        "error": r.error.code.value if r.error else "",
        "kind": r.file.kind or "",
        "pages": r.file.page_count if r.file.page_count is not None else "",
        "chars": q.char_count if q else 0,
        "garbled": q.garbled_ratio if q else "",
        "vi_dau": q.vi_diacritic_ratio if q else "",
        "tables": len(r.tables),
        "warnings": ",".join(w.code for w in r.warnings),
        "ms": r.timings_ms.get("total", ""),
    }


def to_markdown(rows: list[dict]) -> str:
    cols = list(rows[0])
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join(lines)


def cmd_run(args) -> int:
    files = collect(args.paths)
    if not files:
        print("không có file PDF/DOCX nào")
        return 2
    items = [
        (f"{f.name}#{i}" if args.repeat > 1 else f.name, f)
        for i in range(args.repeat)
        for f in files
    ]
    options = ExtractOptions(extract_tables=not args.no_tables)
    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    rows = []
    for key, r in extract_many(items, workers=args.workers, options=options):
        rows.append(row(key, r))
        if out and "#" not in key or (out and key.endswith("#0")):
            stem = Path(key.split("#")[0]).stem
            (out / f"{stem}.txt").write_text(r.text, encoding="utf-8")
            (out / f"{stem}.json").write_text(
                r.model_dump_json(indent=2, exclude={"text"}), encoding="utf-8"
            )
        if args.print and "#" not in key:
            print(f"===== {key} ({r.status})\n{r.text}\n")
    elapsed = time.perf_counter() - t0

    rows.sort(key=lambda r: r["file"])
    shown = rows if args.repeat == 1 else [r for r in rows if r["file"].endswith("#0")]
    table = to_markdown(shown)
    failed = sum(r["status"] == "failed" for r in rows)
    summary = (
        f"{len(rows)} file · {len(rows) - failed} đọc được · {failed} lỗi · "
        f"{elapsed:.2f} giây · {len(rows) / elapsed:.1f} file/giây · "
        f"workers={args.workers or 'auto'}"
    )
    print(table)
    print(summary)
    if args.report:
        Path(args.report).write_text(f"{table}\n\n{summary}\n", encoding="utf-8")
    if args.json:
        print(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="trích văn bản file hoặc thư mục")
    run.add_argument("paths", nargs="+")
    run.add_argument("--workers", type=int, default=None, help="số tiến trình (mặc định: số CPU)")
    run.add_argument("--repeat", type=int, default=1, help="nhân bộ file N lần để đo lô")
    run.add_argument("--no-tables", action="store_true", help="bỏ bước bảng (nhanh hơn)")
    run.add_argument("--out", help="thư mục ghi .txt/.json (nên trong data/)")
    run.add_argument("--report", help="ghi bảng chỉ số markdown ra file")
    run.add_argument("--print", action="store_true", help="in văn bản ra màn hình")
    run.add_argument("--json", action="store_true", help="in thêm JSON chỉ số")
    args = parser.parse_args(argv)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
