"""S4-D02: đo E (điểm Ngữ nghĩa) trên ma trận vector tin thật + CV mẫu; AC #492 ≤ 500 ms.

    uv run python scripts/semantic_bench.py   # DATABASE_URL (chỉ đọc) + khóa Workers AI

Kho thật ít hơn --target tin thì nhân bản đoạn (id tin mới). In: thời gian nạp ma trận (binary),
thời gian vector hóa từng CV (Workers AI, gọi 1 lần nhờ cache), p50/p95 tính E, top tin theo E
cạnh top theo K (S4-D01) để kiểm bằng mắt.
"""

import argparse
import statistics
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cvparser.pipeline import parse_cv  # noqa: E402
from embedding.embedder import from_env  # noqa: E402
from ingestion.crawl import _database_url, load_env_file  # noqa: E402
from ranking.semantic import CvVectorCache, SemanticIndex, cv_texts  # noqa: E402
from retrieval.bm25 import KeywordIndex, load_open_jobs, query_from_profile  # noqa: E402

SAMPLES = ROOT / "tests" / "fixtures" / "cv" / "samples"


def pad(index: SemanticIndex, target: int) -> SemanticIndex:
    if len(index) >= target:
        return index
    ends = np.append(index.starts[1:], index.n_chunks)
    ids, rows, next_id = [], [], int(index.ids.max()) + 1
    for i in range(len(index)):
        ids += [int(index.ids[i])] * int(ends[i] - index.starts[i])
        rows.append(index.matrix[index.starts[i] : ends[i]])
    k = 0
    while len(index) + k < target:
        i = k % len(index)
        n = int(ends[i] - index.starts[i])
        ids += [next_id + k] * n
        rows.append(index.matrix[index.starts[i] : ends[i]])
        k += 1
    return SemanticIndex(ids, np.vstack(rows), index.model)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target", type=int, default=2000)
    p.add_argument("--repeat", type=int, default=20)
    p.add_argument("--show", type=int, default=5)
    args = p.parse_args(argv)
    load_env_file()
    embedder = from_env()
    if embedder is None:
        p.error("thiếu CF_ACCOUNT_ID / CF_API_TOKEN để vector hóa CV")

    import psycopg

    with psycopg.connect(_database_url(), options="-c default_transaction_read_only=on") as conn:
        t = time.perf_counter()
        real = SemanticIndex.from_db(conn)
        load_s = time.perf_counter() - t
        jobs = load_open_jobs(conn)
    titles = {d.id: d.title for d in jobs}
    keyword = KeywordIndex.build(jobs)
    index = pad(real, args.target)
    print(
        f"Ma trận thật: {len(real)} tin · {real.n_chunks} đoạn · nạp binary {load_s:.2f} s · "
        f"{real.matrix.nbytes / 1e6:.0f} MB (float32) · đo trên {len(index)} tin · "
        f"{index.n_chunks} đoạn · model {index.model}"
    )

    cache = CvVectorCache(embedder)
    e_ms, embed_ms = [], []
    for path in sorted(SAMPLES.glob("cv*.*")):
        parsed = parse_cv(path.read_bytes(), filename=path.name, as_of=date(2026, 11, 17))
        if parsed["status"] != "parsed":
            print(f"\n{path.name}: đọc lỗi")
            continue
        texts = cv_texts(parsed)
        t = time.perf_counter()
        vecs = cache.vectors_for_texts(texts)
        embed_ms.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        cache.vectors_for_texts(texts)
        cached_ms = (time.perf_counter() - t) * 1000
        times = []
        for _ in range(args.repeat):
            t = time.perf_counter()
            result = index.score(vecs, model=cache.model)
            times.append((time.perf_counter() - t) * 1000)
        e_ms += times
        print(
            f"\n{path.name} · {parsed['profile'].get('target_title')!r} · {len(texts)} đoạn CV · "
            f"vector hóa {embed_ms[-1]:.0f} ms (lần 2 từ cache {cached_ms:.2f} ms) · "
            f"E p50 {statistics.median(times):.1f} ms"
        )
        kw = keyword.score(query_from_profile(parsed["profile"]))
        top_k_ids = {j for j, _ in keyword.top_k(kw, args.show)} if kw else set()
        for job_id, raw in index.top_k(result, args.show, allowed=set(titles)):
            mark = "  (cũng trong top K)" if job_id in top_k_ids else ""
            print(f"   E={result.e_of(job_id):.3f}  cos={raw:.3f}  {titles[job_id][:65]}{mark}")

    if e_ms:
        e_ms.sort()
        p95 = e_ms[int(0.95 * (len(e_ms) - 1))]
        print(
            f"\nTính E: {len(e_ms)} lần · p50 {statistics.median(e_ms):.1f} ms · "
            f"p95 {p95:.1f} ms · AC ≤ 500 ms: {'ĐẠT' if p95 <= 500 else 'CHƯA ĐẠT'}"
        )
        print(
            f"Vector hóa CV (Workers AI, lần đầu): p50 {statistics.median(embed_ms):.0f} ms · "
            f"max {max(embed_ms):.0f} ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
