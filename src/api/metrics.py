"""S4-T04 (US-18): đo độ trễ mỗi request API, ghi vào ops.api_metrics.

- MetricsMiddleware: ASGI thuần, bọc ngoài cùng. Mỗi request HTTP (trừ /health và OPTIONS) ghi một
  dòng: endpoint = phương thức + mẫu đường dẫn ("POST /match/jobs", không chứa id), latency_ms,
  status, user_role (đọc claim user_role trong JWT, KHÔNG kiểm chữ ký: chỉ để phân loại số đo,
  việc xác thực vẫn do từng route làm).
- MetricsRecorder: hàng đợi trong RAM + một luồng nền ghi theo lô qua role api_metrics_writer
  (migration 0019). Request không bao giờ chờ DB; hàng đợi đầy hoặc DB lỗi thì bỏ số đo.
  METRICS_DATABASE_URL trống thì không ghi gì.
"""

import base64
import json
import logging
import queue
import threading
import time

log = logging.getLogger("api.metrics")

ROLES = {"seeker", "hr", "admin"}
SKIP_PATHS = {"/health"}
INSERT_SQL = (
    "insert into ops.api_metrics(endpoint, latency_ms, status, user_role) "
    "values (%s, %s, %s, %s::app.app_role)"
)


def role_from_auth(header: bytes | None) -> str | None:
    """Claim user_role trong Bearer JWT (không kiểm chữ ký). Không đọc được thì None."""
    if not header:
        return None
    try:
        scheme, _, tok = header.decode("latin-1").partition(" ")
        if scheme.lower() != "bearer":
            return None
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        role = json.loads(base64.urlsafe_b64decode(payload)).get("user_role")
    except Exception:  # noqa: BLE001 - token hỏng: vẫn ghi số đo, chỉ thiếu vai trò
        return None
    return role if role in ROLES else None


def endpoint_of(scope: dict) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None) or scope.get("path", "")
    return f"{scope.get('method', '')} {path}"[:200]


class MetricsRecorder:
    """Ghi số đo theo lô ở luồng nền. url trống: record() không làm gì."""

    def __init__(self, url: str, batch: int = 200, flush_seconds: float = 1.0,
                 maxsize: int = 10_000):  # fmt: skip
        self.url = url
        self.batch = batch
        self.flush_seconds = flush_seconds
        self.dropped = 0
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)
        self._stop = threading.Event()
        self._conn = None
        self._thread = None
        if url:
            self._thread = threading.Thread(target=self._run, name="api-metrics", daemon=True)
            self._thread.start()

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def record(self, endpoint: str, latency_ms: int, status: int, role: str | None) -> None:
        if not self.url:
            return
        try:
            self._q.put_nowait((endpoint, latency_ms, status, role))
        except queue.Full:
            self.dropped += 1

    def _take(self) -> list[tuple]:
        rows = []
        deadline = time.monotonic() + self.flush_seconds
        while len(rows) < self.batch:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                break
            try:
                rows.append(self._q.get(timeout=timeout))
            except queue.Empty:
                break
        return rows

    def _write(self, rows: list[tuple]) -> None:
        import psycopg  # import muộn: test và API không bật số đo khỏi cần driver

        try:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self.url, autocommit=True, prepare_threshold=None)
            with self._conn.cursor() as cur:
                cur.executemany(INSERT_SQL, rows)
        except Exception as exc:  # noqa: BLE001 - mất vài số đo còn hơn làm hỏng API
            self.dropped += len(rows)
            log.warning("không ghi được %d số đo: %s", len(rows), exc)
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:  # noqa: BLE001
                    pass
            self._conn = None

    def _run(self) -> None:
        while not self._stop.is_set() or not self._q.empty():
            rows = self._take()
            if rows:
                self._write(rows)

    def close(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass


class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("method") == "OPTIONS"
            or scope.get("path") in SKIP_PATHS
        ):
            await self.app(scope, receive, send)
            return
        status = 500
        started = time.perf_counter()

        async def _send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            self._record(scope, status, started)

    @staticmethod
    def _record(scope, status: int, started: float) -> None:
        try:
            app = scope.get("app")
            recorder = getattr(getattr(app, "state", None), "metrics", None)
            if recorder is None:
                return
            latency_ms = round((time.perf_counter() - started) * 1000)
            headers = dict(scope.get("headers") or [])
            recorder.record(
                endpoint_of(scope), latency_ms, status, role_from_auth(headers.get(b"authorization"))
            )
        except Exception:  # noqa: BLE001 - đo lỗi không được làm hỏng request
            log.exception("lỗi ghi số đo")
