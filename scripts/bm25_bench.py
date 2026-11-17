"""S4-D01: đo K (điểm Từ khóa) trên tin đang mở thật + CV mẫu; AC #488 ≤ 300 ms với 2.000 tin.

    uv run python scripts/bm25_bench.py                  # cần DATABASE_URL (chỉ đọc)
    uv run python scripts/bm25_bench.py --target 2000 --repeat 20 --show 5

Kho thật ít hơn --target thì nhân bản tin (id mới) cho đủ số tin. In thời gian dựng index,
p50/p95 tính K cho từng CV mẫu (tests/fixtures/cv/samples) và top tin theo BM25 để kiểm bằng mắt.
"""

import argparse
import statistics
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cvparser.pipeline import parse_cv  # noqa: E402
from ingestion.crawl import _database_url  # noqa: E402
from retrieval.bm25 import JobDoc, KeywordIndex, load_open_jobs, query_from_profile  # noqa: E402
from retrieval.text import Analyzer  # noqa: E402

SAMPLES = ROOT / "tests" / "fixtures" / "cv" / "samples"


def pad(docs: list[JobDoc], target: int) -> list[JobDoc]:
    out, next_id = list(docs), max((d.id for d in docs), default=0) + 1
    while len(out) < target and docs:
        src = docs[len(out) % len(docs)]
        out.append(
            JobDoc(
                next_id, src.title, src.requirements, src.preferred, src.description, src.jd_text
            )
        )
        next_id += 1
    return out


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target", type=int, default=2000)
    p.add_argument("--repeat", type=int, default=20)
    p.add_argument("--show", type=int, default=5)
    args = p.parse_args(argv)

    import psycopg

    dsn = _database_url()
    if not dsn:
        p.error("thiếu DATABASE_URL")
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        real = load_open_jobs(conn)
    titles = {d.id: d.title for d in real}
    docs = pad(real, args.target)

    analyzer = Analyzer()
    t = time.perf_counter()
    index = KeywordIndex.build(docs, analyzer)
    build_s = time.perf_counter() - t
    print(f"Tin đang mở thật: {len(real)} · index: {len(index)} tin · dựng {build_s:.2f} s")

    all_ms = []
    for path in sorted(SAMPLES.glob("cv*.*")):
        out = parse_cv(path.read_bytes(), filename=path.name, as_of=date(2026, 11, 17))
        if out["status"] != "parsed":
            print(f"\n{path.name}: đọc lỗi {out['error']}")
            continue
        profile = out["profile"]
        q = query_from_profile(profile, analyzer)
        if not q:
            print(f"\n{path.name}: không có kỹ năng / chức danh → K không xác định")
            continue
        times = []
        for _ in range(args.repeat):
            t = time.perf_counter()
            result = index.score(q)
            times.append((time.perf_counter() - t) * 1000)
        all_ms += times
        nonzero = int((result.scores > 0).sum())
        print(
            f"\n{path.name} · {profile.get('target_title')!r} · {len(profile['skills'])} kỹ năng · "
            f"p50 {statistics.median(times):.1f} ms · max {max(times):.1f} ms · "
            f"{nonzero}/{len(index)} tin có điểm > 0"
        )
        real_ids = set(titles)
        for job_id, score in index.top_k(result, args.show, allowed=real_ids):
            print(f"   K={result.k_of(job_id):.3f}  bm25={score:6.2f}  {titles[job_id][:70]}")

    if all_ms:
        all_ms.sort()
        p95 = all_ms[int(0.95 * (len(all_ms) - 1))]
        print(
            f"\nTổng {len(all_ms)} lần: p50 {statistics.median(all_ms):.1f} ms · "
            f"p95 {p95:.1f} ms · AC ≤ 300 ms: {'ĐẠT' if p95 <= 300 else 'CHƯA ĐẠT'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
