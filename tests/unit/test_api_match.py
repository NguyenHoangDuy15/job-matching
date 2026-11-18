"""S4-D04: POST /match/jobs với Supabase giả (MockTransport), kho tin giả trong RAM, JWT tự ký.

AC #498 "API trả Top N đúng schema": response khớp MatchResponse (docs/api/match-jobs.md).
"""

import json
from datetime import date, timedelta

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import match as match_module
from api.main import app
from api.match import MatchResponse
from api.settings import Settings, get_settings
from api.worker import ParsePool
from ranking.engine import JobMeta, Snapshot
from ranking.semantic import CvVectorCache, SemanticIndex
from retrieval.bm25 import JobDoc, KeywordIndex
from tests.unit.test_api_cv import URL, _FakeJwks, token

CV_ID = "22222222-2222-2222-2222-222222222222"
FUTURE = date.today() + timedelta(days=30)


def _unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _snapshot(n_extra: int = 0) -> Snapshot:
    jobs, docs, vecs = [], [], []
    base = [
        (1, "Data Engineer", "Python, SQL, Airflow", 3, [("python", "Python", "required"),
         ("sql", "SQL", "required"), ("spark", "Spark", "preferred")], _unit(1, 0.1)),
        (2, "Backend Developer (Java)", "Java, Spring Boot", 2,
         [("java", "Java", "required")], _unit(0.3, 1)),
        (3, "Data Analyst", "SQL, Excel", None, [("sql", "SQL", "required")], _unit(1, 0.4)),
    ]  # fmt: skip
    base += [
        (100 + i, f"Data Engineer {i}", "Python", 1, [("python", "Python", "required")],
         _unit(1, 0.2 + i / 100))
        for i in range(n_extra)
    ]  # fmt: skip
    for i, title, req, years, skills, v in base:
        jobs.append(JobMeta(i, f"pub-{i}", title, f"Công ty {i}", "onsite", FUTURE,
                            f"https://x/{i}", years, (1,), ("Hà Nội",), tuple(skills)))  # fmt: skip
        docs.append(JobDoc(i, title, req, None, "Mô tả"))
        vecs.append(v)
    return Snapshot(
        {j.id: j for j in jobs},
        KeywordIndex.build(docs),
        SemanticIndex([j.id for j in jobs], np.stack(vecs), model="fake/2d"),
    )


class Holder:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def peek(self):
        return self.snapshot


class FakeDB:
    def __init__(self, closed=()):
        self.closed = set(closed)
        self.asked = []

    def still_open(self, ids):
        self.asked.append(list(ids))
        return {i for i in ids if i not in self.closed}


class TwoDimEmbedder:
    model = "fake/2d"

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[1.0, 0.0] for _ in texts]


class FakeSupabase:
    def __init__(self, cv=None, cv_error=None, save_error=None, stored_chunks=None, merged=True):
        self.cv = cv if cv is not None else {
            "cv_id": CV_ID, "parse_status": "parsed", "target_title": "Data Engineer",
            "years_exp": 5, "profile_confirmed_at": None,
            "sections": {"experience": ["Xây dựng pipeline Python, Airflow"]},
            "skills": [{"skill_id": "python", "name": "Python", "evidence_level": "strong"},
                       {"skill_id": "sql", "name": "SQL", "evidence_level": "listed"}],
        }  # fmt: skip
        self.cv_error = cv_error
        self.save_error = save_error
        self.stored = stored_chunks or []
        self.merged = merged  # False: Supabase chưa chạy migration 0014
        self.calls: list[tuple[str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")  # JWT người dùng
        name = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        self.calls.append((name, body))
        if name == "get_cv_match_input":
            if not self.merged:  # PostgREST: hàm không tồn tại
                return httpx.Response(404, json={"code": "PGRST202", "message": "x"})
            if self.cv_error:
                return httpx.Response(400, json={"code": self.cv_error, "message": "x"})
            return httpx.Response(200, json={**self.cv, "chunks": self.stored})
        if name == "get_cv_for_match":
            if self.cv_error:
                return httpx.Response(400, json={"code": self.cv_error, "message": "x"})
            return httpx.Response(200, json=self.cv)
        if name == "get_cv_chunks":
            return httpx.Response(200, json=self.stored)
        if name == "save_cv_chunks":
            self.stored = [{**c, "embedding": json.dumps(c["embedding"])} for c in body["p_chunks"]]
            return httpx.Response(200, json=len(body["p_chunks"]))
        if name == "save_match":
            if self.save_error:
                return httpx.Response(500, json={"code": "XX000", "message": "x"})
            return httpx.Response(200, json=77)
        return httpx.Response(404)


@pytest.fixture
def make_client():
    def _make(fake=None, snapshot=None, db=None, embedder=None, ready=True):
        fake = fake or FakeSupabase()
        settings = Settings(supabase_url=URL, supabase_publishable_key="sb_publishable_test",
                            parse_workers=0)  # fmt: skip
        app.dependency_overrides[get_settings] = lambda: settings
        app.state.pool = ParsePool(size=0)
        app.state.jwks = _FakeJwks()
        app.state.supabase_transport = httpx.MockTransport(fake.handler)
        app.state.match_engine = Holder(snapshot or _snapshot() if ready else None)
        if not ready:
            app.state.match_engine = Holder(None)
        app.state.matcher_db = db if db is not None else FakeDB()
        app.state.cv_vectors = CvVectorCache(embedder or TwoDimEmbedder())
        match_module.limiter._hits.clear()
        return TestClient(app), fake

    yield _make
    app.dependency_overrides.clear()
    for attr in (
        "jwks",
        "supabase_transport",
        "pool",
        "match_engine",
        "matcher_db",
        "cv_vectors",
        "supabase_http",
        "supabase_http_key",
    ):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


def _post(client, payload=None, tok=None):
    body = {"cv_id": CV_ID, "top_n": 5, **(payload or {})}
    return client.post(
        "/match/jobs", json=body, headers={"Authorization": f"Bearer {tok or token()}"}
    )


def test_returns_top_n_with_schema(make_client):
    client, fake = make_client()
    r = _post(client)
    assert r.status_code == 200, r.text
    body = MatchResponse.model_validate(r.json())  # AC: đúng schema
    assert body.request_id == 77 and body.corpus_size == 3 and body.engine_version == "ranker-v1"
    assert len(body.results) == 3  # kho chỉ có 3 tin: ít hơn N
    assert [x.rank for x in body.results] == [1, 2, 3]
    assert body.results[0].job_id == 1 and body.results[0].title == "Data Engineer"
    scores = [x.score for x in body.results]
    assert scores == sorted(scores, reverse=True)
    top = body.results[0]
    assert {s.skill_id for s in top.skills_matched} == {"python", "sql"}
    assert [s.skill_id for s in top.skills_missing] == ["spark"]
    assert top.apply_url == "https://x/1" and top.valid_through == FUTURE
    assert "không phải xác suất" in body.note
    assert [c[0] for c in fake.calls] == [
        "get_cv_match_input", "save_cv_chunks", "save_match"]  # fmt: skip
    assert "rank;dur=" in r.headers["server-timing"]  # thời gian từng bước cho web / DevTools


def test_falls_back_when_merged_rpc_missing(make_client):
    """Supabase chưa chạy 0014: dùng lại get_cv_for_match + get_cv_chunks, kết quả như cũ."""
    client, fake = make_client(fake=FakeSupabase(merged=False))
    r = _post(client)
    assert r.status_code == 200 and len(r.json()["results"]) == 3
    assert [c[0] for c in fake.calls] == [
        "get_cv_match_input", "get_cv_for_match", "get_cv_chunks",
        "save_cv_chunks", "save_match"]  # fmt: skip


def test_top_n_cut_and_saved_payload(make_client):
    client, fake = make_client(snapshot=_snapshot(n_extra=30))
    r = _post(client, {"top_n": 10, "filters": {"provinces": [1], "work_modes": ["onsite"]}})
    assert r.status_code == 200 and len(r.json()["results"]) == 10
    saved = dict(fake.calls)["save_match"]
    assert saved["p_top_n"] == 10 and len(saved["p_results"]) == 10
    assert saved["p_filters"] == {"provinces": [1], "work_modes": ["onsite"]}
    assert saved["p_weights"] == {"K": 0.25, "M": 0.35, "E": 0.3, "X": 0.1}
    assert saved["p_results"][0].keys() >= {"rank", "job_id", "score", "k", "m", "e", "x", "gap"}


def test_closed_jobs_dropped_and_backfilled(make_client):
    db = FakeDB(closed={1})
    client, _ = make_client(snapshot=_snapshot(n_extra=10), db=db)
    r = _post(client)
    ids = [x["job_id"] for x in r.json()["results"]]
    assert 1 not in ids and len(ids) == 5  # tin vừa đóng bị bỏ, tin kế tiếp bù vào
    assert db.asked


def test_cv_vectors_reused_from_db(make_client):
    emb = TwoDimEmbedder()
    client, fake = make_client(embedder=emb)
    _post(client)
    match_module.limiter._hits.clear()
    app.state.cv_vectors = CvVectorCache(emb)  # API khởi động lại: mất cache RAM
    fake.calls.clear()
    _post(client)
    assert emb.calls == 1  # lần 2 đọc vector đã lưu, không gọi model
    assert "save_cv_chunks" not in [c[0] for c in fake.calls]


def test_no_embedder_still_returns_results(make_client):
    client, _ = make_client()
    app.state.cv_vectors = None
    r = _post(client)
    assert r.status_code == 200
    assert all(x["components"]["E"] is None for x in r.json()["results"])


def test_save_failure_still_returns_results(make_client):
    client, _ = make_client(fake=FakeSupabase(save_error=True))
    r = _post(client)
    assert r.status_code == 200 and r.json()["request_id"] is None and r.json()["results"]


@pytest.mark.parametrize(
    ("fake", "status", "error"),
    [
        (FakeSupabase(cv_error="P0002"), 404, "cv_not_found"),
        (FakeSupabase(cv={"cv_id": CV_ID, "parse_status": "queued"}), 409, "cv_not_parsed"),
    ],
)
def test_cv_errors(make_client, fake, status, error):
    client, _ = make_client(fake=fake)
    r = _post(client)
    assert r.status_code == status and r.json() == {"error": error}


def test_engine_warming(make_client):
    client, _ = make_client(ready=False)
    r = _post(client)
    assert r.status_code == 503 and r.json() == {"error": "engine_warming"}


@pytest.mark.parametrize(
    "payload",
    [{"top_n": 7}, {"cv_id": "khong-phai-uuid"}, {"filters": {"work_modes": ["office"]}}],
)
def test_invalid_request(make_client, payload):
    client, _ = make_client()
    assert _post(client, payload).status_code == 422


def test_requires_login(make_client):
    client, _ = make_client()
    r = client.post("/match/jobs", json={"cv_id": CV_ID, "top_n": 5})
    assert r.status_code == 401


def test_rate_limited(make_client):
    client, _ = make_client()
    codes = [_post(client).status_code for _ in range(21)]
    assert codes[-1] == 429 and set(codes[:20]) == {200}


def test_warm_rank_prepares_snapshot_before_ready():
    snap = _snapshot()
    assert match_module.warm_rank(snap) is snap  # chạy thử rank() không lỗi, trả lại snapshot
