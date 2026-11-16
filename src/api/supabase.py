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
    ) -> None:
        self._http = httpx.Client(
            base_url=url.rstrip("/"),
            headers={"apikey": apikey, "Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> "SupabaseClient":
        return self

    def __exit__(self, *exc) -> None:
        self._http.close()

    def rpc(self, name: str, params: dict):
        r = self._http.post(
            f"/rest/v1/rpc/{name}",
            json=params,
            headers={"Content-Profile": "api", "Accept-Profile": "api"},
        )
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {}
            raise SupabaseError(r.status_code, body.get("code"), body.get("message", ""))
        return r.json() if r.content else None

    def download(self, path: str) -> bytes:
        r = self._http.get(f"/storage/v1/object/authenticated/{CV_BUCKET}/{quote(path)}")
        if r.status_code >= 400:
            raise SupabaseError(r.status_code, "storage", r.text[:200])
        return r.content
