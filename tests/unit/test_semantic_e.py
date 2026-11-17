"""S4-D02: E · điểm Ngữ nghĩa = max-cosine trung bình theo đoạn, phân vị toàn kho."""

import time

import numpy as np
import pytest

from embedding.chunker import approx_tokens, cv_chunks
from embedding.embedder import FakeEmbedder
from ranking.percentile import percentile_rank
from ranking.semantic import CvVectorCache, SemanticIndex, cv_texts, maxsim


def _unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _brute(query, docs_by_job):
    out = []
    for docs in docs_by_job:
        out.append(np.mean([max(float(q @ d) for d in docs) for q in query]))
    return np.array(out)


def test_maxsim_matches_brute_force():
    rng = np.random.default_rng(1)
    q = rng.normal(size=(4, 16)).astype(np.float32)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    sizes = [1, 3, 15, 2]  # tin 1 đoạn, tin 15 đoạn
    docs = [rng.normal(size=(n, 16)).astype(np.float32) for n in sizes]
    docs = [d / np.linalg.norm(d, axis=1, keepdims=True) for d in docs]
    matrix = np.vstack(docs)
    starts = np.cumsum([0, *sizes[:-1]])
    assert np.allclose(maxsim(q, matrix, starts), _brute(q, docs), atol=1e-6)


def test_job_boundaries_and_best_chunk_at_end():
    """Đoạn giống nhất nằm cuối tin vẫn được lấy; không lẫn sang tin bên cạnh."""
    ids = [10, 10, 10, 20]
    vecs = np.stack([_unit(0, 1), _unit(0, 1), _unit(1, 0), _unit(0, 1)])
    index = SemanticIndex(ids, vecs)
    r = index.score(np.stack([_unit(1, 0)]))
    assert list(index.ids) == [10, 20]
    assert r.raw[0] == pytest.approx(1.0) and r.raw[1] == pytest.approx(0.0, abs=1e-6)
    assert r.e_of(10) > r.e_of(20)


def test_chunks_of_a_job_must_be_contiguous():
    with pytest.raises(ValueError):
        SemanticIndex([1, 2, 1], np.stack([_unit(1, 0)] * 3))


def test_percentile_shared_with_k_bounds_and_ties():
    p = percentile_rank(np.array([0.3, 0.5, 0.5, 0.9]))
    assert ((p >= 0) & (p <= 1)).all()
    assert p[3] > p[1] == p[2] > p[0] > 0  # cosine luôn dương: không ép điểm thấp về 0


def test_job_without_vectors_has_no_e():
    index = SemanticIndex([1], np.stack([_unit(1, 0)]))
    r = index.score(np.stack([_unit(1, 0)]))
    assert r.e_of(1) == 0.5 and r.e_of(999) is None  # 999 chưa có vector → None, không phải 0


def test_empty_cv_or_empty_index_gives_none():
    index = SemanticIndex([1], np.stack([_unit(1, 0)]))
    assert index.score(None) is None and index.score(np.zeros((0, 2))) is None
    assert SemanticIndex([], np.zeros((0, 2))).score(np.stack([_unit(1, 0)])) is None


def test_model_mismatch_refused():
    index = SemanticIndex([1], np.stack([_unit(1, 0)]), model="cf/baai/bge-m3")
    with pytest.raises(ValueError):
        index.score(np.stack([_unit(1, 0)]), model="hf/BAAI/bge-m3")


def test_float16_storage_keeps_cosine():
    rng = np.random.default_rng(2)
    m = rng.normal(size=(50, 1024)).astype(np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    q = m[:3]
    exact = SemanticIndex(range(50), m).score(q).raw
    half = SemanticIndex(range(50), m.astype(np.float16)).score(q).raw
    assert np.abs(exact - half).max() < 1e-3


def test_e_does_not_change_with_filters():
    index = SemanticIndex([1, 2, 3], np.stack([_unit(1, 0), _unit(1, 1), _unit(0, 1)]))
    r = index.score(np.stack([_unit(1, 0)]))
    before = r.e_of(2)
    assert [j for j, _ in index.top_k(r, 10, allowed={2, 3})] == [2, 3]
    assert index.top_k(r, 1) == [(1, pytest.approx(1.0))]
    assert r.e_of(2) == before


def test_cv_chunks_keep_professional_sections_only():
    sections = {
        "header": ["[HỌ_TÊN] · [EMAIL]"],
        "education": ["Đại học Bách khoa, Khoa học máy tính"],
        "experience": ["Backend Developer — Công ty A", "Xây dựng API Java Spring Boot"],
        "projects": ["Hệ thống thanh toán"],
        "skills": ["Java, Spring Boot, Docker"],
        "activities": ["Đội bóng đá"],
    }
    chunks = cv_chunks(sections, "Backend Developer", ["Java", "Docker"], count=approx_tokens)
    text = "\n".join(c.content for c in chunks)
    assert chunks[0].section == "summary" and "Chức danh mong muốn: Backend Developer" in text
    assert "CV — Kinh nghiệm:" in text and "CV — Dự án:" in text
    for hidden in ("Bách khoa", "bóng đá", "[EMAIL]"):
        assert hidden not in text
    assert all(approx_tokens(c.content) <= 300 for c in chunks)


def test_cv_texts_from_parse_cv_output():
    parsed = {
        "sections": {"experience": ["Phát triển ứng dụng React"]},
        "profile": {
            "target_title": "Frontend Developer",
            "skills": [{"skill_id": "react", "name": "React"}],
        },
    }
    texts = cv_texts(parsed)
    assert texts[0].startswith("Chức danh mong muốn: Frontend Developer · Kỹ năng: React")
    assert any(t.startswith("CV — Kinh nghiệm:") for t in texts)


class CountingEmbedder(FakeEmbedder):
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return super().embed(texts)


def test_cv_vectors_cached_by_content():
    emb = CountingEmbedder()
    cache = CvVectorCache(emb, max_items=2)
    a = cache.vectors_for_texts(["CV a"])
    assert (
        cache.vectors_for_texts(["CV a"]) is a and emb.calls == 1
    )  # đổi N / bộ lọc: không gọi lại
    cache.vectors_for_texts(["CV b"])
    cache.vectors_for_texts(["CV c"])  # vượt max_items: bỏ CV cũ nhất
    cache.vectors_for_texts(["CV a"])
    assert emb.calls == 4
    assert cache.vectors_for_texts([]) is None


def test_e_for_2000_jobs_within_500ms():
    """AC #492: E tính xong ≤ 500 ms với 2.000 tin (≈ 8.500 đoạn), CV 10 đoạn."""
    rng = np.random.default_rng(0)
    counts = rng.integers(1, 9, size=2000)
    ids = np.repeat(np.arange(2000), counts)
    vecs = rng.normal(size=(len(ids), 1024)).astype(np.float16)
    index = SemanticIndex(ids, vecs)
    cv = rng.normal(size=(10, 1024)).astype(np.float32)
    index.score(cv)  # làm nóng
    t = time.perf_counter()
    for _ in range(10):
        r = index.score(cv)
    per_call_ms = (time.perf_counter() - t) * 1000 / 10
    assert len(r.e) == 2000
    assert per_call_ms <= 500, per_call_ms


def test_register_halfvec_falls_back_to_extensions_schema(monkeypatch):
    """matcher_ro (0012) không có schema `extensions` trong search_path: tìm tên đầy đủ."""
    import pgvector.psycopg.halfvec as hv
    from psycopg.types import TypeInfo

    from ranking import semantic

    asked, registered = [], []

    class Conn:
        def rollback(self):
            pass

    def fetch(conn, name):
        asked.append(name)
        return "info" if name == "extensions.halfvec" else None

    monkeypatch.setattr(TypeInfo, "fetch", staticmethod(fetch))
    monkeypatch.setattr(hv, "register_halfvec_info", lambda conn, info: registered.append(info))
    semantic.register_halfvec(Conn())
    assert asked == ["halfvec", "extensions.halfvec"] and registered == ["info"]

    monkeypatch.setattr(TypeInfo, "fetch", staticmethod(lambda conn, name: None))
    with pytest.raises(RuntimeError):
        semantic.register_halfvec(Conn())
