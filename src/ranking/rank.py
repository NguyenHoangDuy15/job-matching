"""Top N việc phù hợp cho một CV (S4-D04, US-16). Hàm thuần: không gọi DB hay mạng.

1. Lọc cứng: tỉnh/thành (tin remote hoặc không ghi tỉnh luôn qua), hình thức, còn hạn.
2. Ứng viên: top `per_source` theo BM25 ∪ top `per_source` theo vector, trong tập đã lọc.
3. Chấm K, E (phân vị TOÀN kho), M, X → H (chia lại trọng số khi thiếu thành phần).
4. Sắp H giảm dần (hòa: E rồi id), kèm kỹ năng khớp / chưa thể hiện và giải thích ngắn.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from ranking.components import Combined, MatchDetail, RankerConfig, combine, m_score, x_score
from ranking.engine import JobMeta, Snapshot

WORK_MODES = ("onsite", "hybrid", "remote")


@dataclass(frozen=True)
class MatchFilters:
    provinces: tuple[int, ...] = ()
    work_modes: tuple[str, ...] = ()

    def as_json(self) -> dict:
        return {"provinces": list(self.provinces), "work_modes": list(self.work_modes)}


@dataclass(frozen=True)
class CvInput:
    skills: dict[str, str]  # slug → strong | listed | user_added
    skill_names: dict[str, str]  # slug → tên hiển thị
    years_exp: float | None
    query_tokens: list[str]  # truy vấn BM25 (retrieval.bm25.query_from_profile)
    vectors: np.ndarray | None  # vector các đoạn CV; None → E không xác định
    vectors_model: str | None = None


@dataclass(frozen=True)
class ScoredJob:
    job: JobMeta
    combined: Combined
    match: MatchDetail | None
    explanation: str

    @property
    def score(self) -> float:
        return self.combined.h if self.combined.h is not None else 0.0


@dataclass(frozen=True)
class RankOutput:
    results: list[ScoredJob]  # đã sắp, dài hơn top_n để API bù tin vừa đóng
    allowed: int  # số tin qua bộ lọc
    candidates: int
    corpus_size: int
    notes: list[str] = field(default_factory=list)


def allowed_jobs(snapshot: Snapshot, filters: MatchFilters, today: date) -> set[int]:
    provinces = set(filters.provinces)
    modes = set(filters.work_modes)
    out = set()
    for job in snapshot.jobs.values():
        if job.valid_through is not None and job.valid_through < today:
            continue
        if modes and job.work_mode not in modes:
            continue
        # Tin remote hoặc không ghi tỉnh luôn qua bộ lọc tỉnh.
        outside = provinces and job.work_mode != "remote" and job.provinces
        if outside and not provinces.intersection(job.provinces):
            continue
        out.add(job.id)
    return out


def _fmt_years(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def explain(job: JobMeta, combined: Combined, match: MatchDetail | None, cv_years) -> str:
    parts = []
    if match is not None:
        req = [r for r in match.rows if r.level == "required"]
        pref = [r for r in match.rows if r.level == "preferred"]
        if req:
            parts.append(f"Khớp {sum(r.credit > 0 for r in req)}/{len(req)} kỹ năng bắt buộc")
        if pref:
            parts.append(f"{sum(r.credit > 0 for r in pref)}/{len(pref)} kỹ năng ưu tiên")
    else:
        parts.append("Tin không ghi kỹ năng bắt buộc/ưu tiên")
    x = combined.components.get("X")
    if x is not None:
        if x >= 1:
            parts.append(f"đủ kinh nghiệm (yêu cầu {_fmt_years(job.years_exp_min)} năm)")
        else:
            parts.append(
                f"kinh nghiệm {_fmt_years(cv_years)}/{_fmt_years(job.years_exp_min)} năm yêu cầu"
            )
    elif job.years_exp_min is None:
        parts.append("tin không ghi số năm kinh nghiệm")
    e = combined.components.get("E")
    if e is not None:
        parts.append(f"nội dung CV gần với tin này hơn {e * 100:.0f}% tin đang mở")
    return " · ".join(parts)


class SignalsCache:
    """K, E trên TOÀN kho của một CV (BM25 mọi tin + nhân ma trận mọi đoạn), nhớ theo snapshot +
    nội dung truy vấn: đổi N hay bộ lọc cho cùng CV không tính lại (S4-D05: trên 0,1 CPU phép
    nhân ma trận chiếm phần lớn thời gian một lượt)."""

    def __init__(self, max_items: int = 64):
        self.max_items = max_items
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
            if hit is not None:
                self._data.move_to_end(key)
            return hit

    def put(self, key, value) -> None:
        with self._lock:
            self._data[key] = value
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)


def _signals(snapshot: Snapshot, cv: CvInput, cache: SignalsCache | None):
    key = None
    if cache is not None:
        h = hashlib.sha256(" ".join(cv.query_tokens).encode())
        if cv.vectors is not None:
            h.update(np.ascontiguousarray(cv.vectors, dtype=np.float32).tobytes())
        key = (id(snapshot), snapshot.built_at, cv.vectors_model, h.hexdigest())
        hit = cache.get(key)
        if hit is not None:
            return hit
    kw = snapshot.keyword.score(cv.query_tokens) if cv.query_tokens else None
    sem = None
    if cv.vectors is not None and len(cv.vectors):
        sem = snapshot.semantic.score(cv.vectors, model=cv.vectors_model)
    if cache is not None:
        cache.put(key, (kw, sem))
    return kw, sem


def rank(
    snapshot: Snapshot,
    cv: CvInput,
    filters: MatchFilters,
    today: date,
    tax,
    cfg: RankerConfig,
    per_source: int = 100,
    keep: int = 60,
    signals_cache: SignalsCache | None = None,
) -> RankOutput:
    allowed = allowed_jobs(snapshot, filters, today)
    notes: list[str] = []
    kw, sem = _signals(snapshot, cv, signals_cache)
    if kw is None:
        notes.append("K không xác định: CV không có kỹ năng và chức danh")
    if sem is None:
        notes.append("E không xác định: chưa có vector CV")

    candidates: set[int] = set()
    if kw is not None:
        candidates.update(j for j, _ in snapshot.keyword.top_k(kw, per_source, allowed))
    if sem is not None:
        candidates.update(j for j, _ in snapshot.semantic.top_k(sem, per_source, allowed))
    if not candidates and kw is None and sem is None:
        candidates = set(allowed)  # không có tín hiệu tìm kiếm: chấm tất cả bằng M, X

    scored: list[ScoredJob] = []
    for job_id in candidates:
        job = snapshot.jobs[job_id]
        match = m_score([(s, lvl) for s, _, lvl in job.skills], cv.skills, tax, cfg)
        comps = {
            "K": kw.k_of(job_id) if kw is not None else None,
            "M": match.score if match is not None else None,
            "E": sem.e_of(job_id) if sem is not None else None,
            "X": x_score(cv.years_exp, job.years_exp_min),
        }
        combined = combine(comps, cfg)
        if combined.h is None:
            continue
        scored.append(ScoredJob(job, combined, match, explain(job, combined, match, cv.years_exp)))
    scored.sort(key=lambda s: (-s.score, -(s.combined.components.get("E") or 0.0), s.job.id))
    return RankOutput(scored[:keep], len(allowed), len(candidates), snapshot.corpus_size, notes)


def skill_rows(match: MatchDetail | None, names: dict[str, str]) -> tuple[list, list]:
    """(kỹ năng khớp, kỹ năng CV chưa thể hiện) cho thẻ kết quả, bắt buộc trước."""
    if match is None:
        return [], []

    def name(slug: str | None) -> str | None:
        return None if slug is None else names.get(slug, slug)

    matched = [
        {
            "skill_id": r.skill_id,
            "skill": name(r.skill_id),
            "level": r.level,
            "via": name(r.cv_skill) if r.relation != "exact" else None,
            "relation": r.relation,
            "evidence": r.evidence,
        }
        for r in match.matched
    ]
    missing = [
        {"skill_id": r.skill_id, "skill": name(r.skill_id), "level": r.level} for r in match.missing
    ]
    return matched, missing


def job_skill_names(jobs: Iterable[JobMeta]) -> dict[str, str]:
    return {slug: nm for j in jobs for slug, nm, _ in j.skills}
