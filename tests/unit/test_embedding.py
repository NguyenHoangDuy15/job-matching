"""S3-D07: cắt đoạn ≤ 300 token, gọi Workers AI (giả), FakeEmbedder."""

import json
import math

import httpx
import pytest

from embedding.chunker import JobText, approx_tokens, job_chunks, summary_text
from embedding.embedder import DIM, EmbedderError, FakeEmbedder, WorkersAIEmbedder, from_env


def words(text: str) -> int:
    """Bộ đếm dễ đoán cho test: 1 token/từ + 2 token đặc biệt."""
    return len(text.split()) + 2


JOB = JobText(
    title="Backend Developer",
    company="Công ty X",
    seniority="senior",
    work_mode="unknown",
    skills_required=("Java", "Spring Boot"),
    skills_preferred=("Kafka",),
    sections={
        "description": "Xây dựng API\nTối ưu truy vấn",
        "requirements": "\n".join(f"- dòng yêu cầu số {i} có năm từ" for i in range(40)),
        "preferred": None,
    },
)


def test_every_chunk_within_limit_and_sections():
    chunks = job_chunks(JOB, words, max_tokens=50)
    assert all(words(c.content) <= 50 for c in chunks)
    assert [c.section for c in chunks][:2] == ["summary", "description"]
    req = [c for c in chunks if c.section == "requirements"]
    assert len(req) > 1 and [c.chunk_no for c in req] == list(range(len(req)))
    assert all(c.content.startswith("Backend Developer — Yêu cầu: ") for c in req)
    assert not any(c.section in ("preferred", "benefits") for c in chunks)


def test_overlap_one_line_between_chunks():
    req = [c for c in job_chunks(JOB, words, max_tokens=50) if c.section == "requirements"]
    first_last = req[0].content.splitlines()[-1]
    assert first_last in req[1].content  # dòng cuối đoạn trước lặp lại ở đầu đoạn sau


def test_no_line_lost():
    req = [c for c in job_chunks(JOB, words, max_tokens=50) if c.section == "requirements"]
    joined = "\n".join(c.content for c in req)
    for i in range(40):
        assert f"dòng yêu cầu số {i} có" in joined


def test_very_long_line_split_by_sentence_then_words():
    long = "Câu một rất dài. " * 30 + " ".join(["từ"] * 200)
    job = JobText(title="Dev", sections={"description": long})
    chunks = job_chunks(job, words, max_tokens=40)
    assert all(words(c.content) <= 40 for c in chunks)


def test_summary_skips_unknown_and_jd_text_fallback():
    s = summary_text(JOB)
    assert "Cấp bậc: senior" in s and "Hình thức" not in s and "Kỹ năng ưu tiên: Kafka" in s
    job = JobText(title="Dev", jd_text="Toàn văn JD chưa tách section")
    assert [c.section for c in job_chunks(job, words)] == ["summary", "description"]


def test_approx_counter_overestimates():
    text = "Kinh nghiệm phát triển ứng dụng web bằng Java Spring Boot và PostgreSQL " * 5
    assert approx_tokens(text) >= len(text) / 3.5


def test_fake_embedder_deterministic_unit_vectors():
    a, b = FakeEmbedder().embed(["x", "y"])
    assert len(a) == DIM and a == FakeEmbedder().embed(["x"])[0] and a != b
    assert math.isclose(sum(v * v for v in a), 1.0, rel_tol=1e-6)


def _workers(handler, **kw):
    return WorkersAIEmbedder("acc", "tok", transport=httpx.MockTransport(handler), **kw)


def test_workers_ai_batches_retries_and_normalizes(monkeypatch):
    monkeypatch.setattr("embedding.embedder.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        texts = json.loads(request.content)["text"]
        calls.append(len(texts))
        assert request.url.path.endswith("/accounts/acc/ai/run/@cf/baai/bge-m3")
        assert request.headers["authorization"] == "Bearer tok"
        if len(calls) == 1:
            return httpx.Response(429)  # bị giới hạn lần đầu → thử lại
        return httpx.Response(200, json={"result": {"data": [[2.0] * DIM for _ in texts]}})

    out = _workers(handler, batch_size=3).embed([f"t{i}" for i in range(7)])
    assert calls == [3, 3, 3, 1] and len(out) == 7
    assert math.isclose(sum(v * v for v in out[0]), 1.0, rel_tol=1e-6)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401),
        httpx.Response(200, json={"result": {"data": [[1.0] * 10]}}),  # sai số chiều
        httpx.Response(200, json={"result": {}}),
    ],
)
def test_workers_ai_errors(response):
    with pytest.raises(EmbedderError):
        _workers(lambda r: response).embed(["a"])


def test_from_env(monkeypatch):
    for k in ("EMBEDDER", "CF_API_TOKEN", "CF_ACCOUNT_ID"):
        monkeypatch.delenv(k, raising=False)
    assert from_env() is None
    monkeypatch.setenv("EMBEDDER", "fake")
    assert isinstance(from_env(), FakeEmbedder)
    monkeypatch.setenv("EMBEDDER", "workers_ai")
    with pytest.raises(EmbedderError):
        from_env()
    monkeypatch.setenv("CF_ACCOUNT_ID", "a")
    monkeypatch.setenv("CF_API_TOKEN", "t")
    assert isinstance(from_env(), WorkersAIEmbedder)
