"""E · điểm Ngữ nghĩa (S4-D02, US-16): max-cosine trung bình theo đoạn, phân vị toàn kho (numpy).

    index = SemanticIndex.from_db(conn)            # ma trận vector tin đang mở, nạp binary
    cv_vecs = CvVectorCache(embedder).vectors(parsed_cv)   # vector đoạn CV, gọi model 1 lần/CV
    result = index.score(cv_vecs)                  # None nếu CV không có đoạn nào
    result.e_of(job_id)                            # 0–1; None nếu tin chưa có vector
    index.top_k(result, 100, allowed_ids)          # S4-D04: top 100 theo vector

E_raw(j) = (1/n) Σᵢ maxₖ cos(cᵢ, dₖ): mỗi đoạn CV cᵢ tìm đoạn dₖ giống nhất của tin j, rồi lấy
trung bình theo đoạn CV (chiều CV → JD: mọi tin chấm bằng cùng một tập đoạn CV nên so được với
nhau). E = phân vị của E_raw trên MỌI tin có vector (ranking.percentile). Luồng HR đảo đầu vào
của `maxsim` (1 JD so với nhiều CV).
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ranking.percentile import percentile_rank

_MATRIX_SQL = """
select c.job_id, c.embedding
  from core.job_chunks c
  join core.jobs j on j.id = c.job_id
 where j.origin = 'crawled' and j.status = 'open'
   and (j.valid_through is null or j.valid_through >= current_date)
   and c.model = %(model)s
 order by c.job_id, c.id
"""
DEFAULT_MODEL = "cf/baai/bge-m3"


def _l2(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def register_halfvec(conn) -> None:
    """Đăng ký kiểu halfvec (đọc binary → numpy) cho kết nối. Trên Supabase kiểu nằm ở schema
    `extensions`, ngoài search_path của role matcher_ro (migration 0012), nên tìm cả tên đầy đủ.
    Không dùng pgvector.register_vector: hàm đó đòi kiểu `vector` nằm trong search_path."""
    from pgvector.psycopg.halfvec import register_halfvec_info
    from psycopg.types import TypeInfo

    for name in ("halfvec", "extensions.halfvec"):
        try:
            info = TypeInfo.fetch(conn, name)
        except Exception:  # schema không tồn tại (Postgres thường): thử tên tiếp theo
            conn.rollback()
            info = None
        if info is not None:
            register_halfvec_info(conn, info)
            return
    raise RuntimeError("không tìm thấy kiểu halfvec (cài extension pgvector chưa?)")


def maxsim(query: np.ndarray, docs: np.ndarray, starts: np.ndarray) -> np.ndarray:
    """query (n × d), docs (m × d) đã chuẩn hóa L2, đoạn của mỗi tài liệu nằm liền nhau bắt đầu
    ở `starts` → mảng (số tài liệu,): trung bình theo n đoạn query của max cosine trong tài liệu."""
    sims = query @ docs.T  # n × m
    best = np.maximum.reduceat(sims, starts, axis=1)  # n × số tài liệu
    return best.mean(axis=0)


@dataclass(frozen=True)
class SemanticResult:
    ids: np.ndarray
    raw: np.ndarray  # E_raw: max-cosine trung bình
    e: np.ndarray  # phân vị toàn kho, 0–1
    _pos: dict[int, int]

    def e_of(self, job_id: int) -> float | None:
        """None nếu tin chưa có vector (S4-D03 chia lại trọng số, không coi là 0)."""
        i = self._pos.get(job_id)
        return None if i is None else float(self.e[i])

    def as_dict(self) -> dict[int, float]:
        return {int(i): float(v) for i, v in zip(self.ids, self.e, strict=True)}


class SemanticIndex:
    def __init__(
        self, chunk_job_ids: Sequence[int], vectors: np.ndarray, model: str = DEFAULT_MODEL
    ):
        """chunk_job_ids[i] là tin của vectors[i]; các đoạn của một tin phải liền nhau."""
        job_ids = np.asarray(chunk_job_ids, dtype=np.int64)
        if len(job_ids) != len(vectors):
            raise ValueError("số job_id khác số vector")
        if len(job_ids):
            change = np.flatnonzero(np.diff(job_ids)) + 1
            self.starts = np.concatenate(([0], change)).astype(np.int64)
            self.ids = job_ids[self.starts]
            if len(np.unique(self.ids)) != len(self.ids):
                raise ValueError("đoạn của cùng một tin phải nằm liền nhau (order by job_id)")
        else:
            self.starts = np.zeros(0, dtype=np.int64)
            self.ids = np.zeros(0, dtype=np.int64)
        self.matrix = _l2(np.asarray(vectors, dtype=np.float32))  # float16 → float32 → L2
        self.model = model
        self._pos = {int(j): i for i, j in enumerate(self.ids)}

    @classmethod
    def from_db(cls, conn, model: str = DEFAULT_MODEL) -> SemanticIndex:
        """Nạp ma trận vector tin đang mở dạng BINARY (pgvector → numpy float16): khoảng 3 s cho
        6.130 đoạn, so với 24 s khi đọc dạng text. Chỉ đọc."""
        register_halfvec(conn)
        with conn.cursor(binary=True) as cur:
            cur.execute(_MATRIX_SQL, {"model": model})
            rows = cur.fetchall()
        if not rows:
            return cls([], np.zeros((0, 1024), dtype=np.float32), model)
        ids = [r[0] for r in rows]
        vectors = np.stack([r[1].to_numpy() for r in rows])
        return cls(ids, vectors, model)

    def __len__(self) -> int:
        return len(self.ids)

    @property
    def n_chunks(self) -> int:
        return len(self.matrix)

    def score(
        self, cv_vectors: np.ndarray | None, model: str | None = None
    ) -> SemanticResult | None:
        """`model`: model đã sinh vector CV; khác model của ma trận tin thì báo lỗi (không so
        vector của hai model khác nhau, kể cả cùng bge-m3 chạy ở hai nơi)."""
        if model is not None and model != self.model:
            raise ValueError(f"vector CV ({model}) khác model của kho tin ({self.model})")
        if cv_vectors is None or len(cv_vectors) == 0 or not len(self.ids):
            return None
        q = _l2(np.asarray(cv_vectors, dtype=np.float32))
        raw = maxsim(q, self.matrix, self.starts)
        return SemanticResult(self.ids, raw, percentile_rank(raw), self._pos)

    def top_k(
        self, result: SemanticResult, k: int = 100, allowed: set[int] | None = None
    ) -> list[tuple[int, float]]:
        """(id, E_raw) cao nhất, chỉ trong `allowed` nếu có."""
        idx = np.arange(len(self.ids))
        if allowed is not None:
            idx = idx[np.isin(self.ids, np.fromiter(allowed, dtype=np.int64, count=len(allowed)))]
        if len(idx) > k:
            idx = idx[np.argpartition(-result.raw[idx], k - 1)[:k]]
        idx = idx[np.lexsort((self.ids[idx], -result.raw[idx]))]
        return [(int(self.ids[i]), float(result.raw[i])) for i in idx]


def cv_texts(parsed: dict) -> list[str]:
    """`parse_cv()` (status parsed) → nội dung các đoạn CV cần vector hóa."""
    from embedding.chunker import cv_chunks

    profile = parsed.get("profile") or {}
    names = [s.get("name") or s["skill_id"] for s in profile.get("skills") or []]
    chunks = cv_chunks(parsed.get("sections") or {}, profile.get("target_title"), names)
    return [c.content for c in chunks]


class CvVectorCache:
    """Vector đoạn CV, nhớ trong RAM theo nội dung (sha256 các đoạn + model): mỗi CV chỉ gọi
    Workers AI một lần, các lượt Top N sau (đổi N, đổi bộ lọc) dùng lại."""

    def __init__(self, embedder, max_items: int = 256):
        self.embedder = embedder
        self.model = getattr(embedder, "model", "unknown")
        self.max_items = max_items
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()

    def _key(self, texts: list[str]) -> str:
        h = hashlib.sha256(self.model.encode())
        for t in texts:
            h.update(b"\x00" + t.encode("utf-8"))
        return h.hexdigest()

    def vectors_for_texts(self, texts: list[str]) -> np.ndarray | None:
        if not texts:
            return None
        key = self._key(texts)
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        vecs = np.asarray(self.embedder.embed(texts), dtype=np.float32)
        self._cache[key] = vecs
        if len(self._cache) > self.max_items:
            self._cache.popitem(last=False)
        return vecs

    def vectors(self, parsed: dict) -> np.ndarray | None:
        return self.vectors_for_texts(cv_texts(parsed))
