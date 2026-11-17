"""Gọi Supabase (PostgREST RPC + Storage) BẰNG JWT NGƯỜI DÙNG: RLS quyết định họ thấy gì.

API không giữ service_role key hay mật khẩu DB. `transport` thay được trong test (MockTransport).
"""

from urllib.parse import quote

import httpx

CV_BUCKET = "cvs"


class SupabaseError(Exception):
    def __init__(self, status: int, code: str | None, message: str = "") -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.message = message


class SupabaseClient:
    def __init__(
        self,
        url: str,
        apikey: str,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
        http: httpx.Client | None = None,
    ) -> None:
        """`http`: client dùng chung giữa các request (giữ kết nối HTTPS, không bắt tay TLS lại
        mỗi lượt, S4-D05). Khi đó token gửi theo từng request và client không bị đóng ở đây."""
        self._auth = {"apikey": apikey, "Authorization": f"Bearer {token}"}
        self._shared = http is not None
        self._new_connection = not self._shared
        self._http = http or httpx.Client(
            base_url=url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> "SupabaseClient":
        return self

    def __exit__(self, *exc) -> None:
        if not self._shared:
            self._http.close()

    def rpc(self, name: str, params: dict):
        r = self._http.post(
            f"/rest/v1/rpc/{name}",
            json=params,
            headers={**self._auth, "Content-Profile": "api", "Accept-Profile": "api"},
        )
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {}
            raise SupabaseError(r.status_code, body.get("code"), body.get("message", ""))
        return r.json() if r.content else None

    def download(self, path: str) -> bytes:
        r = self._http.get(
            f"/storage/v1/object/authenticated/{CV_BUCKET}/{quote(path)}", headers=self._auth
        )
        if r.status_code >= 400:
            raise SupabaseError(r.status_code, "storage", r.text[:200])
        return r.content
