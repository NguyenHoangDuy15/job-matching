"""POST /cv/parse (S3-D05, US-12): đọc CV đã tải lên Storage, ghi hồ sơ, trả hồ sơ JSON.

Luồng (mọi lệnh gọi Supabase dùng JWT người dùng → RLS chặn CV người khác):
  1. api.claim_cv_parse(cv_id)   → đường dẫn file; CV người khác/không có → 404; đang đọc → 409
  2. tải file từ Storage
  3. cvparser.pipeline.parse_cv trong tiến trình có timeout cứng
  4. api.save_cv_profile(...)    hoặc api.fail_cv_parse(cv_id, mã lỗi)
Log chỉ ghi cv_id, mã lỗi, thời gian; không ghi nội dung CV hay token.
"""

import contextlib
import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from api.auth import User, current_user
from api.settings import Settings, get_settings
from api.supabase import SupabaseClient, SupabaseError

log = logging.getLogger("api.cv")
router = APIRouter()


class ParseRequest(BaseModel):
    cv_id: uuid.UUID


class _RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


limiter = _RateLimiter()


def _client(request: Request, settings: Settings, user: User) -> SupabaseClient:
    return SupabaseClient(
        settings.supabase_url,
        settings.supabase_publishable_key,
        user.token,
        transport=getattr(request.app.state, "supabase_transport", None),
    )


def _parse(request: Request, cv_id: str, user: User, settings: Settings) -> dict:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    with _client(request, settings, user) as sb:
        try:
            rows = sb.rpc("claim_cv_parse", {"p_cv_id": cv_id})
        except SupabaseError as e:
            if e.code == "P0002":
                raise HTTPException(404, {"error": "cv_not_found"}) from None
            if e.code == "55P03":
                raise HTTPException(409, {"error": "parse_in_progress"}) from None
            if e.status in (401, 403):
                raise HTTPException(401, {"error": "unauthorized"}) from None
            raise HTTPException(502, {"error": "supabase_error"}) from None
        row = rows[0] if isinstance(rows, list) and rows else None
        if row is None:
            raise HTTPException(404, {"error": "cv_not_found"})
        timings["claim"] = _ms(t0)

        def fail(code: str, status: int, extra: dict | None = None):
            with contextlib.suppress(SupabaseError):
                sb.rpc("fail_cv_parse", {"p_cv_id": cv_id, "p_code": code})
            log.info("cv_parse cv_id=%s status=failed code=%s", cv_id, code)
            raise HTTPException(status, {"error": code, **(extra or {})})

        t = time.perf_counter()
        try:
            data = sb.download(row["storage_path"])
        except SupabaseError:
            fail("file_not_found", 404)
        timings["download"] = _ms(t)

        t = time.perf_counter()
        as_of = datetime.now(ZoneInfo(settings.timezone)).date()
        try:
            result = request.app.state.pool.run(
                data,
                filename=row["storage_path"].rsplit("/", 1)[-1],
                known_names=user.names,
                as_of=as_of,
            )
        except TimeoutError:
            fail("timeout", 504)
        except Exception:
            fail("internal_error", 500)
        timings["parse"] = _ms(t)

        if result["status"] == "failed":
            err = result["error"]
            fail(err["code"], 422, {"message_vi": err["message_vi"]})

        profile = result["profile"]
        t = time.perf_counter()
        try:
            saved = sb.rpc(
                "save_cv_profile",
                {
                    "p_cv_id": cv_id,
                    "p_text_redacted": result["text_redacted"],
                    "p_sections": result["sections"],
                    "p_years_exp": profile["years_exp"],
                    "p_target_title": profile["target_title"],
                    "p_skills": [
                        {k: s[k] for k in ("skill_id", "evidence_level", "evidence", "years")}
                        for s in profile["skills"]
                    ],
                    "p_parser_version": result["parser_version"],
                },
            )
        except SupabaseError:
            fail("save_failed", 502)
        timings["save"] = _ms(t)
    timings["total"] = _ms(t0)
    log.info(
        "cv_parse cv_id=%s status=parsed skills=%s total_ms=%s",
        cv_id,
        len(profile["skills"]),
        timings["total"],
    )
    return {
        "cv_id": cv_id,
        "status": "parsed",
        "skills_saved": saved,
        "profile": profile,
        "warnings": result.get("warnings", []),
        "timings_ms": {**result.get("timings_ms", {}), **timings},
    }


@router.post("/cv/parse")
async def parse_cv_endpoint(
    body: ParseRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    if not limiter.check(user.id, settings.rate_limit_per_minute):
        raise HTTPException(429, {"error": "rate_limited"})
    return await run_in_threadpool(_parse, request, str(body.cv_id), user, settings)


def _ms(t: float) -> float:
    return round((time.perf_counter() - t) * 1000, 1)
