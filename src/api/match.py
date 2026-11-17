"""POST /match/jobs (S4-D04, US-16): Top N việc còn hạn phù hợp nhất với một CV đã đọc.

Luồng: đọc hồ sơ CV bằng JWT người dùng (api.get_cv_for_match, RLS) → vector đoạn CV (đọc lại
app.cv_chunks; thiếu / đổi thì vector hóa rồi lưu) → ranking.rank trên snapshot kho tin trong RAM
(matcher_ro) → kiểm lại Top N còn mở NGAY LÚC NÀY → ghi app.match_requests/results
(api.save_match) → trả Top N. Schema: docs/api/match-jobs.md.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from api.auth import User, current_user
from api.cv import _RateLimiter
from api.settings import Settings, get_settings
from api.supabase import SupabaseClient, SupabaseError

log = logging.getLogger("api.match")
router = APIRouter()
limiter = _RateLimiter()
NOTE = "Điểm là mức phù hợp theo công thức, không phải xác suất trúng tuyển."


# ---- Schema -------------------------------------------------------------------------
class MatchFiltersIn(BaseModel):
    provinces: list[int] = Field(default_factory=list, max_length=34)
    work_modes: list[Literal["onsite", "hybrid", "remote"]] = Field(default_factory=list)


class MatchRequest(BaseModel):
    cv_id: uuid.UUID
    top_n: Literal[5, 10, 20, 50] = 10
    filters: MatchFiltersIn = Field(default_factory=MatchFiltersIn)


class Components(BaseModel):
    K: float | None  # Từ khóa
    M: float | None  # Kỹ năng
    E: float | None  # Ngữ nghĩa
    X: float | None  # Kinh nghiệm


class SkillMatched(BaseModel):
    skill_id: str
    skill: str
    level: Literal["required", "preferred"]
    via: str | None  # kỹ năng CV dùng để khớp khi không trùng hẳn (cha / con / anh em)
    relation: Literal["exact", "child", "parent_only", "sibling"]
    evidence: Literal["strong", "listed", "user_added"] | None


class SkillMissing(BaseModel):
    skill_id: str
    skill: str
    level: Literal["required", "preferred"]


class MatchResult(BaseModel):
    rank: int
    job_id: int
    public_id: str | None
    title: str
    company: str | None
    provinces: list[str]
    work_mode: str
    valid_through: date | None
    apply_url: str | None
    score: float = Field(ge=0, le=100)
    components: Components
    weights_used: dict[str, float]
    skills_matched: list[SkillMatched]
    skills_missing: list[SkillMissing]
    explanation: str


class MatchResponse(BaseModel):
    request_id: int | None  # None nếu ghi lịch sử lỗi (kết quả vẫn trả)
    cv_id: uuid.UUID
    top_n: int
    engine_version: str
    corpus_size: int
    candidates: int
    latency_ms: int
    note: str
    results: list[MatchResult]


# ---- Vector CV ----------------------------------------------------------------------
def cv_chunk_list(cv: dict):
    from embedding.chunker import cv_chunks

    names = [s.get("name") or s["skill_id"] for s in cv.get("skills") or []]
    return cv_chunks(cv.get("sections") or {}, cv.get("target_title"), names)


def cv_vectors(sb: SupabaseClient, cv: dict, cache, timings: dict) -> np.ndarray | None:
    """Đọc vector đã lưu nếu khớp nội dung đoạn hiện tại; nếu không thì vector hóa (cache trong
    RAM) rồi lưu lại. Đoạn tóm tắt dựng từ chức danh + kỹ năng ĐÃ XÁC NHẬN, nên sửa hồ sơ thì
    đoạn đó đổi và được vector hóa lại."""
    if cache is None:
        return None
    chunks = cv_chunk_list(cv)
    if not chunks:
        return None
    want = [(c.section, c.chunk_no, c.content) for c in chunks]
    t = time.perf_counter()
    try:
        stored = sb.rpc("get_cv_chunks", {"p_cv_id": cv["cv_id"], "p_model": cache.model}) or []
    except SupabaseError:
        stored = []
    by_key = {(r["section"], r["chunk_no"], r["content"]): r["embedding"] for r in stored}
    timings["cv_chunks_read"] = _ms(t)
    if len(stored) == len(want) and all(k in by_key for k in want):
        return np.asarray([json.loads(by_key[k]) for k in want], dtype=np.float32)
    t = time.perf_counter()
    vecs = cache.vectors_for_texts([c.content for c in chunks])
    timings["cv_embed"] = _ms(t)
    payload = [
        {"section": c.section, "chunk_no": c.chunk_no, "content": c.content,
         "embedding": [round(float(x), 6) for x in v]}
        for c, v in zip(chunks, vecs, strict=True)
    ]  # fmt: skip
    try:
        sb.rpc("save_cv_chunks", {"p_cv_id": cv["cv_id"], "p_model": cache.model,
                                  "p_chunks": payload})  # fmt: skip
    except SupabaseError as e:  # lưu lỗi không chặn kết quả: lần sau vector hóa lại
        log.warning("save_cv_chunks lỗi cv_id=%s code=%s", cv["cv_id"], e.code)
    return vecs


# ---- Endpoint -----------------------------------------------------------------------
def _client(request: Request, settings: Settings, user: User) -> SupabaseClient:
    return SupabaseClient(
        settings.supabase_url,
        settings.supabase_publishable_key,
        user.token,
        transport=getattr(request.app.state, "supabase_transport", None),
    )


def _match(request: Request, body: MatchRequest, user: User, settings: Settings) -> dict:
    from ranking.components import load_ranker_config
    from ranking.rank import CvInput, MatchFilters, rank, skill_rows
    from retrieval.bm25 import query_from_profile
    from skillkit.levels.pipeline import SKILLS_YAML
    from skillkit.taxonomy import load_taxonomy

    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    holder = getattr(request.app.state, "match_engine", None)
    if holder is None:
        raise HTTPException(503, {"error": "matcher_not_configured"})
    snapshot = holder.peek()
    if snapshot is None:
        raise HTTPException(503, {"error": "engine_warming"})
    cv_id = str(body.cv_id)

    with _client(request, settings, user) as sb:
        t = time.perf_counter()
        try:
            cv = sb.rpc("get_cv_for_match", {"p_cv_id": cv_id})
        except SupabaseError as e:
            if e.code == "P0002":
                raise HTTPException(404, {"error": "cv_not_found"}) from None
            if e.status in (401, 403) or e.code == "42501":
                raise HTTPException(401, {"error": "unauthorized"}) from None
            raise HTTPException(502, {"error": "supabase_error"}) from None
        timings["cv_read"] = _ms(t)
        if not cv or cv.get("parse_status") != "parsed":
            raise HTTPException(409, {"error": "cv_not_parsed"})

        cache = getattr(request.app.state, "cv_vectors", None)
        try:
            vectors = cv_vectors(sb, cv, cache, timings)
        except Exception:  # Workers AI lỗi / hết quota: vẫn trả kết quả, E không xác định
            log.exception("vector CV lỗi cv_id=%s", cv_id)
            vectors = None

        cfg = load_ranker_config()
        skills = {s["skill_id"]: s["evidence_level"] for s in cv.get("skills") or []}
        names = {s["skill_id"]: s.get("name") or s["skill_id"] for s in cv.get("skills") or []}
        cv_input = CvInput(
            skills=skills,
            skill_names=names,
            years_exp=None if cv.get("years_exp") is None else float(cv["years_exp"]),
            query_tokens=query_from_profile(
                {"target_title": cv.get("target_title"), "skills": cv.get("skills") or []}
            ),
            vectors=vectors,
            vectors_model=getattr(cache, "model", None),
        )
        filters = MatchFilters(
            tuple(body.filters.provinces), tuple(dict.fromkeys(body.filters.work_modes))
        )
        today = datetime.now(ZoneInfo(settings.timezone)).date()
        t = time.perf_counter()
        out = rank(snapshot, cv_input, filters, today, _taxonomy(SKILLS_YAML, load_taxonomy), cfg)
        timings["rank"] = _ms(t)

        # Snapshot có thể cũ ≤ 1 giờ: bỏ tin vừa đóng / hết hạn, lấy tin kế tiếp bù vào.
        t = time.perf_counter()
        pool = out.results[: body.top_n + 20]
        db = getattr(request.app.state, "matcher_db", None)
        if db is not None and pool:
            try:
                still = db.still_open([s.job.id for s in pool])
                pool = [s for s in pool if s.job.id in still]
            except Exception:
                log.exception("kiểm tin còn mở lỗi: dùng snapshot")
        top = pool[: body.top_n]
        timings["still_open"] = _ms(t)

        skill_names = {**names, **{slug: nm for s in top for slug, nm, _ in s.job.skills}}
        results = []
        for i, s in enumerate(top, start=1):
            matched, missing = skill_rows(s.match, skill_names)
            c = s.combined.components
            results.append(
                {
                    "rank": i,
                    "job_id": s.job.id,
                    "public_id": s.job.public_id,
                    "title": s.job.title,
                    "company": s.job.company,
                    "provinces": list(s.job.province_names),
                    "work_mode": s.job.work_mode,
                    "valid_through": s.job.valid_through,
                    "apply_url": s.job.apply_url,
                    "score": s.score,
                    "components": {k: None if c[k] is None else round(c[k], 4) for k in c},
                    "weights_used": {k: round(v, 4) for k, v in s.combined.weights_used.items()},
                    "skills_matched": matched,
                    "skills_missing": missing,
                    "explanation": s.explanation,
                }
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        request_id = None
        t = time.perf_counter()
        try:
            request_id = sb.rpc(
                "save_match",
                {
                    "p_cv_id": cv_id,
                    "p_top_n": body.top_n,
                    "p_filters": filters.as_json(),
                    "p_weights": cfg.weights,
                    "p_engine_version": cfg.version,
                    "p_corpus_size": out.corpus_size,
                    "p_latency_ms": latency_ms,
                    "p_results": [
                        {
                            "rank": r["rank"],
                            "job_id": r["job_id"],
                            "score": r["score"],
                            "k": r["components"]["K"],
                            "m": r["components"]["M"],
                            "e": r["components"]["E"],
                            "x": r["components"]["X"],
                            "gap": {"matched": r["skills_matched"], "missing": r["skills_missing"]},
                            "explanation": r["explanation"],
                        }
                        for r in results
                    ],
                },
            )
        except SupabaseError as e:  # không ghi được lịch sử: vẫn trả kết quả
            log.warning("save_match lỗi cv_id=%s code=%s", cv_id, e.code)
        timings["save"] = _ms(t)

    log.info(
        "match cv_id=%s top_n=%s allowed=%s candidates=%s results=%s latency_ms=%s timings=%s",
        cv_id, body.top_n, out.allowed, out.candidates, len(results), latency_ms, timings,
    )  # fmt: skip
    return MatchResponse(
        request_id=request_id,
        cv_id=body.cv_id,
        top_n=body.top_n,
        engine_version=cfg.version,
        corpus_size=out.corpus_size,
        candidates=out.candidates,
        latency_ms=latency_ms,
        note=NOTE,
        results=results,
    ).model_dump(mode="json")


_TAX = {}


def _taxonomy(path, loader):
    if path not in _TAX:
        _TAX[path] = loader(path)
    return _TAX[path]


@router.post("/match/jobs", response_model=MatchResponse)
async def match_jobs(
    body: MatchRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    if not limiter.check(user.id, settings.match_rate_limit_per_minute):
        raise HTTPException(429, {"error": "rate_limited"})
    return await run_in_threadpool(_match, request, body, user, settings)


def _ms(t: float) -> float:
    return round((time.perf_counter() - t) * 1000, 1)
