"""S3-D05: POST /cv/parse với Supabase giả (httpx.MockTransport) và JWT ES256 tự ký."""

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from api import cv as cv_module
from api.main import app
from api.settings import Settings, get_settings
from api.worker import ParsePool

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "cv"
URL = "https://test-ref.supabase.co"
UID = "00000000-0000-0000-0000-00000000000a"
CV_ID = "11111111-1111-1111-1111-111111111111"
KEY = ec.generate_private_key(ec.SECP256R1())


class _FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


def token(**overrides) -> str:
    claims = {
        "sub": UID,
        "aud": "authenticated",
        "iss": f"{URL}/auth/v1",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "user_role": "seeker",
        "account_status": "active",
        "user_metadata": {"full_name": "Nguyễn Văn Hùng"},
        **overrides,
    }
    return jwt.encode(claims, KEY, algorithm="ES256")


class FakeSupabase:
    """Ghi lại các lệnh gọi; trả lời như PostgREST/Storage."""

    def __init__(self, file: bytes, claim_error: str | None = None) -> None:
        self.file = file
        self.claim_error = claim_error
        self.calls: list[tuple[str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")  # luôn bằng JWT người dùng
        assert request.headers["apikey"] == "sb_publishable_test"
        path = request.url.path
        if path.startswith("/rest/v1/rpc/"):
            name = path.rsplit("/", 1)[-1]
            body = json.loads(request.content or b"{}")
            self.calls.append((name, body))
            if name == "claim_cv_parse":
                if self.claim_error:
                    return httpx.Response(400, json={"code": self.claim_error, "message": "x"})
                return httpx.Response(
                    200,
                    json=[{"storage_path": f"u/{UID}/{CV_ID}.pdf", "mime": "application/pdf",
                           "size_bytes": len(self.file)}],
                )  # fmt: skip
            if name == "save_cv_profile":
                return httpx.Response(200, json=len(body["p_skills"]))
            if name == "fail_cv_parse":
                return httpx.Response(204)
        if path.startswith("/storage/v1/object/authenticated/cvs/"):
            self.calls.append(("download", {"path": path}))
            return httpx.Response(200, content=self.file)
        return httpx.Response(404)


@pytest.fixture
def make_client():
    clients = []

    def _make(file: bytes, claim_error: str | None = None, pool: ParsePool | None = None):
        fake = FakeSupabase(file, claim_error)
        settings = Settings(
            supabase_url=URL, supabase_publishable_key="sb_publishable_test", parse_workers=0
        )
        app.dependency_overrides[get_settings] = lambda: settings
        app.state.pool = pool or ParsePool(size=0)
        app.state.jwks = _FakeJwks()
        app.state.supabase_transport = httpx.MockTransport(fake.handler)
        cv_module.limiter._hits.clear()
        client = TestClient(app)
        clients.append(client)
        return client, fake

    yield _make
    app.dependency_overrides.clear()
    for attr in ("jwks", "supabase_transport", "pool"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


def _post(client, tok=None, cv_id=CV_ID):
    headers = {"Authorization": f"Bearer {tok or token()}"}
    return client.post("/cv/parse", json={"cv_id": cv_id}, headers=headers)


def test_parse_returns_profile_and_saves_with_user_jwt(make_client):
    client, fake = make_client((FIX / "samples" / "cv01.pdf").read_bytes())
    started = time.perf_counter()
    r = _post(client)
    elapsed = time.perf_counter() - started
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "parsed" and body["cv_id"] == CV_ID
    profile = body["profile"]
    assert profile["target_title"] == "Lập trình viên Backend" and profile["years_exp"] >= 5
    assert {"java", "docker"} <= {s["skill_id"] for s in profile["skills"]}
    assert [c[0] for c in fake.calls] == ["claim_cv_parse", "download", "save_cv_profile"]
    saved = fake.calls[-1][1]
    assert "Nguyễn Văn Hùng" not in saved["p_text_redacted"]  # chỉ văn bản đã che PII đi ra
    assert "hung.nguyen@example.com" not in json.dumps(saved, ensure_ascii=False)
    assert saved["p_skills"][0].keys() == {"skill_id", "evidence_level", "evidence", "years"}
    assert elapsed < 15


@pytest.mark.parametrize(
    ("tok", "status"),
    [
        ("not-a-jwt", 401),
        (token(exp=datetime.now(UTC) - timedelta(minutes=1)), 401),
        (token(aud="anon"), 401),
        (token(iss="https://other.supabase.co/auth/v1"), 401),
        (token(account_status="locked"), 403),
    ],
)
def test_bad_or_locked_token(make_client, tok, status):
    client, fake = make_client(b"")
    assert _post(client, tok).status_code == status
    assert fake.calls == []  # không gọi Supabase khi token sai


def test_missing_token(make_client):
    client, _ = make_client(b"")
    assert client.post("/cv/parse", json={"cv_id": CV_ID}).status_code == 401


@pytest.mark.parametrize(
    ("code", "status", "error"),
    [("P0002", 404, "cv_not_found"), ("55P03", 409, "parse_in_progress")],
)
def test_claim_errors(make_client, code, status, error):
    client, _ = make_client(b"", claim_error=code)
    r = _post(client)
    assert r.status_code == status and r.json()["error"] == error


def test_bad_file_marks_failed_with_vietnamese_message(make_client):
    client, fake = make_client((FIX / "edge" / "scan_image_only.pdf").read_bytes())
    r = _post(client)
    assert r.status_code == 422
    assert r.json()["error"] == "ocr_required" and "scan" in r.json()["message_vi"]
    assert fake.calls[-1] == ("fail_cv_parse", {"p_cv_id": CV_ID, "p_code": "ocr_required"})


def test_invalid_cv_id_is_422(make_client):
    client, fake = make_client(b"")
    assert _post(client, cv_id="khong-phai-uuid").status_code == 422
    assert fake.calls == []


def test_rate_limit(make_client):
    client, _ = make_client(b"", claim_error="P0002")
    codes = [_post(client).status_code for _ in range(11)]
    assert codes[:10] == [404] * 10 and codes[10] == 429


def test_hard_timeout_kills_worker_and_marks_failed(make_client):
    pool = ParsePool(size=1, timeout=0.001)  # tiến trình thật, hạn cực ngắn
    try:
        assert pool.warm(timeout=120)
        client, fake = make_client((FIX / "samples" / "cv05.pdf").read_bytes(), pool=pool)
        r = _post(client)
        assert r.status_code == 504 and r.json()["error"] == "timeout"
        assert fake.calls[-1] == ("fail_cv_parse", {"p_cv_id": CV_ID, "p_code": "timeout"})
        # Worker treo đã được thay: lần sau với hạn bình thường vẫn chạy được
        pool.timeout = 30
        result = pool.run(
            (FIX / "samples" / "cv01.pdf").read_bytes(),
            filename="cv01.pdf",
            known_names=(),
            as_of=datetime(2026, 11, 18).date(),
        )
        assert result["status"] == "parsed"
    finally:
        pool.close()
