"""Xác thực JWT Supabase (ES256, khóa công khai lấy từ JWKS; không cần JWT secret).

Kiểm: chữ ký, hạn (`exp`), `iss` = <SUPABASE_URL>/auth/v1, `aud` = authenticated, và claim tùy
biến `account_status` = active (custom_access_token_hook của migration 0001). Token chỉ dùng trong
request, không ghi log.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request

from api.settings import Settings, get_settings

ALGORITHMS = ["ES256", "RS256"]


@dataclass(frozen=True)
class User:
    id: str
    token: str = field(repr=False)
    role: str | None = None
    account_status: str | None = None
    names: tuple[str, ...] = ()  # tên trong tài khoản: che chắc chắn trong CV (S3-D03)


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def verify_token(token: str, settings: Settings, jwks: jwt.PyJWKClient | None = None) -> User:
    """User nếu token hợp lệ; HTTPException 401/403 nếu không."""
    try:
        client = jwks or _jwks_client(settings.jwks_url)
        key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience="authenticated",
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(401, {"error": "unauthorized"}) from None
    status = claims.get("account_status")
    if status not in (None, "active"):
        raise HTTPException(403, {"error": "forbidden", "account_status": status})
    meta = claims.get("user_metadata") or {}
    names = tuple(
        dict.fromkeys(
            str(meta[k]).strip() for k in ("full_name", "name") if isinstance(meta.get(k), str)
        )
    )
    return User(
        id=claims["sub"],
        token=token,
        role=claims.get("user_role"),
        account_status=status,
        names=tuple(n for n in names if n),
    )


def current_user(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> User:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, {"error": "unauthorized"})
    return verify_token(token, settings, getattr(request.app.state, "jwks", None))
