"""S4-T04 (US-18): middleware đo độ trễ mỗi request API, ghi vào ops.api_metrics.

Bộ ghi giả thay MetricsRecorder: kiểm endpoint (mẫu đường dẫn), status, vai trò lấy từ JWT, bỏ qua
/health và OPTIONS. MetricsRecorder thật không cần DB khi url trống.
"""

import base64
import json

import pytest

from api.main import app
from api.metrics import MetricsRecorder, endpoint_of, role_from_auth
from tests.unit.test_api_cv import token
from tests.unit.test_api_match import _post, make_client  # noqa: F401 - fixture dùng lại


class FakeRecorder:
    def __init__(self):
        self.rows: list[tuple] = []

    def record(self, endpoint, latency_ms, status, role):
        self.rows.append((endpoint, latency_ms, status, role))

    def close(self):
        pass


@pytest.fixture
def recorder():
    rec = FakeRecorder()
    app.state.metrics = rec
    yield rec
    if hasattr(app.state, "metrics"):
        delattr(app.state, "metrics")


def test_records_match_request_with_role(make_client, recorder):  # noqa: F811
    client, _ = make_client()
    assert _post(client).status_code == 200
    assert len(recorder.rows) == 1
    endpoint, latency_ms, status, role = recorder.rows[0]
    assert endpoint == "POST /match/jobs"
    assert status == 200 and role == "seeker"
    assert isinstance(latency_ms, int) and latency_ms >= 0


def test_role_from_token_and_errors_recorded(make_client, recorder):  # noqa: F811
    client, _ = make_client()
    _post(client, tok=token(user_role="hr"))
    client.post("/match/jobs", json={"cv_id": "x", "top_n": 5})  # không đăng nhập
    assert [(r[2], r[3]) for r in recorder.rows] == [(200, "hr"), (401, None)]


def test_path_template_has_no_ids(make_client, recorder):  # noqa: F811
    client, _ = make_client()
    client.get("/khong-co-route/123")
    assert recorder.rows[0][0] == "GET /khong-co-route/123"[:200]  # 404: không có mẫu, dùng path
    assert recorder.rows[0][2] == 404


def test_health_and_options_skipped(make_client, recorder):  # noqa: F811
    client, _ = make_client()
    client.get("/health")
    client.options(
        "/match/jobs",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert recorder.rows == []


def test_unhandled_error_recorded_as_500(make_client, recorder):  # noqa: F811
    client, _ = make_client()

    @app.get("/__boom")
    def _boom():
        raise RuntimeError("boom")

    try:
        from fastapi.testclient import TestClient

        r = TestClient(app, raise_server_exceptions=False).get("/__boom")
        assert r.status_code == 500
        assert recorder.rows[-1][:1] == ("GET /__boom",) and recorder.rows[-1][2] == 500
    finally:
        app.router.routes[:] = [
            rt for rt in app.router.routes if getattr(rt, "path", "") != "/__boom"
        ]


def test_recorder_failure_does_not_break_request(make_client):  # noqa: F811
    class Broken:
        def record(self, *a):
            raise RuntimeError("db down")

        def close(self):
            pass

    app.state.metrics = Broken()
    try:
        client, _ = make_client()
        assert _post(client).status_code == 200
    finally:
        delattr(app.state, "metrics")


def test_empty_url_recorder_is_noop():
    rec = MetricsRecorder("")
    assert not rec.enabled and rec._thread is None
    rec.record("GET /x", 1, 200, None)
    assert rec._q.empty()
    rec.close()


def test_full_queue_counts_dropped():
    rec = MetricsRecorder("postgresql://khong-ket-noi", maxsize=1)
    rec._stop.set()  # dừng luồng nền trước khi nó lấy hàng
    rec._thread.join(2)
    rec._q.put_nowait(("a", 1, 200, None))
    rec.record("GET /x", 1, 200, None)
    assert rec.dropped == 1


def _jwt(payload: dict) -> bytes:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"Bearer h.{body}.s".encode()


@pytest.mark.parametrize(
    ("header", "role"),
    [
        (_jwt({"user_role": "admin"}), "admin"),
        (_jwt({"user_role": "root"}), None),
        (_jwt({}), None),
        (b"Basic abc", None),
        (b"Bearer khong-phai-jwt", None),
        (b"Bearer a.%%%.c", None),
        (None, None),
    ],
)
def test_role_from_auth(header, role):
    assert role_from_auth(header) == role


def test_endpoint_of_truncates():
    assert endpoint_of({"method": "GET", "path": "/" + "a" * 500}) == ("GET /" + "a" * 500)[:200]
