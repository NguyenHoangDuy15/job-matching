"""S4-D04: đo Top N đầu cuối trên kho tin thật qua role matcher_ro + 10 CV mẫu (không ghi DB).

    uv run python scripts/match_bench.py      # MATCHER_DATABASE_URL + khóa Workers AI trong .env

In: thời gian nạp snapshot, RAM tiến trình (gồm cả mô hình đọc CV như API thật), thời gian từng
bước cho mỗi CV và Top 5 để kiểm bằng mắt.
"""

import resource
import statistics
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api.match import cv_chunk_list  # noqa: E402
from api.settings import Settings  # noqa: E402
from cvparser.pipeline import parse_cv, warm_up  # noqa: E402
from embedding.embedder import from_env  # noqa: E402
from ingestion.crawl import load_env_file  # noqa: E402
from ranking.components import load_ranker_config  # noqa: E402
from ranking.engine import MatcherDB  # noqa: E402
from ranking.rank import CvInput, MatchFilters, rank  # noqa: E402
from ranking.semantic import CvVectorCache  # noqa: E402
from retrieval.bm25 import query_from_profile  # noqa: E402
from skillkit.levels.pipeline import SKILLS_YAML  # noqa: E402
from skillkit.taxonomy import load_taxonomy  # noqa: E402

SAMPLES = ROOT / "tests" / "fixtures" / "cv" / "samples"


def rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3  # macOS: byte, Linux: KB


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env_file()
    settings = Settings()
    if not settings.matcher_database_url:
        print("thiếu MATCHER_DATABASE_URL")
        return 2
    warm_up()  # như API thật: Presidio/spaCy, từ điển
    print(f"RAM sau khi nạp mô hình đọc CV: {rss_mb():.0f} MB")
    db = MatcherDB(settings.matcher_database_url)
    t = time.perf_counter()
    snap = db.build_snapshot()
    print(
        f"Snapshot: {snap.corpus_size} tin · {snap.semantic.n_chunks} đoạn · "
        f"nạp {time.perf_counter() - t:.1f} s · RAM {rss_mb():.0f} MB"
    )
    cache = CvVectorCache(from_env())
    tax, cfg = load_taxonomy(SKILLS_YAML), load_ranker_config()
    totals = []
    for path in sorted(SAMPLES.glob("cv*.*")):
        parsed = parse_cv(path.read_bytes(), filename=path.name, as_of=date.today())
        prof = parsed["profile"]
        skills = [{"skill_id": s["skill_id"], "name": s["name"],
                   "evidence_level": s["evidence_level"]} for s in prof["skills"]]  # fmt: skip
        cv = {"sections": parsed["sections"], "target_title": prof["target_title"],
              "skills": skills}  # fmt: skip
        t = time.perf_counter()
        vecs = cache.vectors_for_texts([c.content for c in cv_chunk_list(cv)])
        embed_ms = (time.perf_counter() - t) * 1000
        cv_in = CvInput(
            {s["skill_id"]: s["evidence_level"] for s in skills},
            {s["skill_id"]: s["name"] for s in skills},
            prof["years_exp"],
            query_from_profile(cv),
            np.asarray(vecs),
            cache.model,
        )
        t = time.perf_counter()
        out = rank(snap, cv_in, MatchFilters(), date.today(), tax, cfg)
        rank_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        still = db.still_open([s.job.id for s in out.results[:30]])
        open_ms = (time.perf_counter() - t) * 1000
        top = [s for s in out.results if s.job.id in still][:5]
        totals.append(embed_ms + rank_ms + open_ms)
        print(
            f"\n{path.name} · {prof['target_title']!r} · vector CV {embed_ms:.0f} ms · rank "
            f"{rank_ms:.0f} ms ({out.candidates} ứng viên) · kiểm còn mở {open_ms:.0f} ms"
        )
        for s in top:
            c = s.combined.components
            fmt = {k: "–" if v is None else f"{v:.2f}" for k, v in c.items()}
            print(
                f"   {s.score:5.1f}  K {fmt['K']} M {fmt['M']} E {fmt['E']} X {fmt['X']}  "
                f"{s.job.title[:55]}"
            )
    print(
        f"\nTổng (vector CV lần đầu + rank + kiểm còn mở): p50 {statistics.median(totals):.0f} ms"
        f" · max {max(totals):.0f} ms · RAM đỉnh {rss_mb():.0f} MB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
