"""K · điểm Từ khóa (S4-D01, US-16): BM25 trong bộ nhớ (bm25s) trên tin đang mở.

    index = KeywordIndex.build(load_open_jobs(conn))
    result = index.score(query_from_profile(cv_profile))   # None nếu CV không có gì để hỏi
    result.k_of(job_id)                                     # 0–1, phân vị trên toàn kho
    index.top_k(result, 100, allowed_ids)                   # S4-D04: top 100 theo BM25

K_j = (số tin có điểm < s_j + 0,5 × số tin có điểm = s_j) / N, với N = MỌI tin đang mở (không
phải tập sau bộ lọc), nên K cùng thang khi đổi bộ lọc, khi chấm 1 JD và khi chấm phía HR.
Tin không khớp từ nào (s_j = 0) có K = 0, không nhận "phân vị giữa" của nhóm điểm 0.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import bm25s
import numpy as np

from retrieval.text import Analyzer, KeywordConfig, skill_token


@dataclass(frozen=True)
class JobDoc:
    id: int
    title: str | None = None
    requirements: str | None = None
    preferred: str | None = None
    description: str | None = None
    jd_text: str | None = None  # dùng khi tin chưa tách được section


def job_tokens(doc: JobDoc, analyzer: Analyzer) -> list[str]:
    """Trọng số trường = số lần lặp token (bm25s không có BM25F). Quyền lợi không đưa vào."""
    w = analyzer.cfg.field_weights
    fields = {
        "title": doc.title,
        "requirements": doc.requirements,
        "preferred": doc.preferred,
        "description": doc.description,
    }
    if not any(fields[f] for f in ("requirements", "preferred", "description")):
        fields["description"] = doc.jd_text
    out: list[str] = []
    for name, text in fields.items():
        out += analyzer.tokens(text) * w.get(name, 1)
    return out


def query_from_profile(profile, analyzer: Analyzer | None = None) -> list[str]:
    """Hồ sơ CV (cvparser.profile.CvProfile) → token truy vấn: kỹ năng (strong ×2, listed ×1)
    + chức danh mong muốn ×2. Rỗng nếu CV không có kỹ năng lẫn chức danh."""
    analyzer = analyzer or Analyzer()
    w = analyzer.cfg.query_weights
    data = profile if isinstance(profile, dict) else profile.model_dump()  # dict từ parse_cv
    out: list[str] = []
    for s in data.get("skills") or []:
        out += [skill_token(s["skill_id"])] * w.get(s.get("evidence_level"), 1)
    if data.get("target_title"):
        out += analyzer.tokens(data["target_title"]) * w.get("target_title", 1)
    return out


def percentile_k(scores: np.ndarray) -> np.ndarray:
    """Phân vị (0–1) của từng điểm trong chính mảng đó; điểm ≤ 0 → 0."""
    n = len(scores)
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    ordered = np.sort(scores)
    below = np.searchsorted(ordered, scores, side="left")
    at_or_below = np.searchsorted(ordered, scores, side="right")
    k = (below + 0.5 * (at_or_below - below)) / n
    k[scores <= 0] = 0.0
    return k


@dataclass(frozen=True)
class KeywordResult:
    ids: np.ndarray  # id tin, cùng thứ tự với scores / k
    scores: np.ndarray  # điểm BM25 thô
    k: np.ndarray  # phân vị toàn kho, 0–1
    _pos: dict[int, int]

    def k_of(self, job_id: int) -> float | None:
        i = self._pos.get(job_id)
        return None if i is None else float(self.k[i])

    def as_dict(self) -> dict[int, float]:
        return {int(i): float(v) for i, v in zip(self.ids, self.k, strict=True)}


class KeywordIndex:
    def __init__(self, ids: Sequence[int], corpus: list[list[str]], cfg: KeywordConfig):
        self.ids = np.asarray(ids, dtype=np.int64)
        self._pos = {int(j): i for i, j in enumerate(self.ids)}
        self.cfg = cfg
        self._bm25 = bm25s.BM25(k1=cfg.k1, b=cfg.b, method=cfg.method)
        if corpus:
            # Tin không có token nào vẫn giữ chỗ (điểm 0) để vị trí khớp với ids.
            self._bm25.index([t or [""] for t in corpus], show_progress=False)
        self._vocab = set(getattr(self._bm25, "vocab_dict", {}) or {}) - {""}
        self.built_at = time.time()

    @classmethod
    def build(cls, docs: Iterable[JobDoc], analyzer: Analyzer | None = None) -> KeywordIndex:
        analyzer = analyzer or Analyzer()
        docs = list(docs)
        return cls([d.id for d in docs], [job_tokens(d, analyzer) for d in docs], analyzer.cfg)

    def __len__(self) -> int:
        return len(self.ids)

    def raw_scores(self, query: list[str]) -> np.ndarray:
        known = [t for t in query if t in self._vocab]
        if not known:  # bm25s lỗi với truy vấn rỗng
            return np.zeros(len(self.ids), dtype=np.float32)
        return np.asarray(self._bm25.get_scores(known), dtype=np.float32)

    def score(self, query: list[str]) -> KeywordResult | None:
        """K của mọi tin cho một truy vấn. None nếu truy vấn rỗng (K không xác định → S4-D03
        chia lại trọng số)."""
        if not query:
            return None
        scores = self.raw_scores(query)
        return KeywordResult(self.ids, scores, percentile_k(scores), self._pos)

    def top_k(
        self, result: KeywordResult, k: int = 100, allowed: set[int] | None = None
    ) -> list[tuple[int, float]]:
        """(id, điểm BM25) cao nhất, chỉ trong `allowed` nếu có; bỏ tin điểm 0."""
        mask = result.scores > 0
        if allowed is not None:
            mask &= np.isin(self.ids, np.fromiter(allowed, dtype=np.int64, count=len(allowed)))
        idx = np.flatnonzero(mask)
        if len(idx) > k:
            idx = idx[np.argpartition(-result.scores[idx], k - 1)[:k]]
        idx = idx[np.lexsort((self.ids[idx], -result.scores[idx]))]
        return [(int(self.ids[i]), float(result.scores[i])) for i in idx]


class RefreshingIndex:
    """Giữ index trong RAM của API, dựng lại ở luồng nền khi quá `refresh_seconds`; request
    luôn dùng bản đang có (đổi con trỏ khi bản mới xong), không chờ dựng lại."""

    def __init__(
        self,
        build: Callable[[], KeywordIndex],
        refresh_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._build = build
        self._every = refresh_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._index: KeywordIndex | None = None
        self._at = 0.0
        self._building = False

    def get(self) -> KeywordIndex:
        if self._index is None:
            with self._lock:
                if self._index is None:
                    self._index, self._at = self._build(), self._clock()
            return self._index
        if self._clock() - self._at >= self._every:
            self._refresh_in_background()
        return self._index

    def _refresh_in_background(self) -> None:
        with self._lock:
            if self._building:
                return
            self._building = True

        def run():
            try:
                index = self._build()
                with self._lock:
                    self._index, self._at = index, self._clock()
            except Exception:  # giữ bản cũ, lần get sau thử lại
                with self._lock:
                    self._at = self._clock()
            finally:
                with self._lock:
                    self._building = False

        threading.Thread(target=run, daemon=True).start()


_OPEN_JOBS_SQL = """
select j.id, j.title, j.requirements, j.preferred, j.description, j.jd_text
  from core.jobs j
 where j.origin = 'crawled' and j.status = 'open'
   and (j.valid_through is null or j.valid_through >= current_date)
 order by j.id
"""


def load_open_jobs(conn) -> list[JobDoc]:
    """Tin đang mở (cùng điều kiện với api.v_open_jobs và bước gắn kỹ năng). Chỉ đọc."""
    return [JobDoc(*row) for row in conn.execute(_OPEN_JOBS_SQL).fetchall()]
