"""M · khớp kỹ năng và X · kinh nghiệm (S4-D03, US-16); gộp K, M, E, X thành H.

    m = m_score(jd_skills, cv_evidence, taxonomy, cfg)   # MatchDetail | None
    x = x_score(cv_years, jd_years)                      # float | None
    h = combine({"K": k, "M": m.score, "E": e, "X": x}, cfg)

M = Σ r_s · f_s · b_s / Σ r_s trên các kỹ năng bắt buộc / ưu tiên của JD:
  r_s  bắt buộc 2, ưu tiên 1 (kỹ năng "chỉ nhắc" không tính)
  f_s  độ khớp theo cây kỹ năng (đúng / con = 1, chỉ có cha = 0,5, anh em cùng cha cấp 2 = 0,3)
  b_s  bằng chứng trong CV (strong 1, listed 0,7, user_added 0,7), 0 nếu CV không có
M = None khi JD không có kỹ năng bắt buộc / ưu tiên nào.
X = min(1, năm kinh nghiệm CV / năm JD yêu cầu); None khi JD không ghi số năm hoặc ghi 0, hoặc
CV không tính được số năm.
H = 100 × Σ wᵢ·điểmᵢ / Σ wᵢ chỉ trên thành phần xác định: trọng số còn lại chia lại cho đủ 1.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RANKER_CONFIG = ROOT / "config" / "ranker_config.yaml"
COMPONENTS = ("K", "M", "E", "X")


@dataclass(frozen=True)
class RankerConfig:
    version: str
    weights: dict[str, float]
    req_weight: dict[str, float]
    evidence: dict[str, float]
    tree: dict[str, float]


@lru_cache(maxsize=4)
def load_ranker_config(path: str | Path = RANKER_CONFIG) -> RankerConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    skill = data["skill"]
    return RankerConfig(
        version=str(data["version"]),
        weights={k: float(v) for k, v in data["weights"].items()},
        req_weight={k: float(v) for k, v in skill["req_weight"].items()},
        evidence={k: float(v) for k, v in skill["evidence"].items()},
        tree={k: float(v) for k, v in skill["tree"].items()},
    )


# ---- M ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SkillMatchRow:
    """Một kỹ năng của JD và cách CV đáp ứng (để giải thích trên thẻ kết quả)."""

    skill_id: str
    level: str  # required | preferred
    weight: float  # r_s
    cv_skill: str | None  # kỹ năng CV dùng để khớp (có thể là cha / con / anh em)
    relation: str | None  # exact | child | parent_only | sibling
    factor: float  # f_s
    evidence: str | None  # strong | listed | user_added
    credit: float  # f_s × b_s, 0–1


@dataclass(frozen=True)
class MatchDetail:
    score: float  # M, 0–1
    rows: list[SkillMatchRow] = field(default_factory=list)

    @property
    def matched(self) -> list[SkillMatchRow]:
        return [r for r in self.rows if r.credit > 0]

    @property
    def missing(self) -> list[SkillMatchRow]:
        """Kỹ năng JD mà CV chưa thể hiện (bắt buộc trước)."""
        return [r for r in self.rows if r.credit == 0]


def _candidates(skill_id: str, tax) -> tuple[tuple[str, str], ...]:
    """Mọi kỹ năng có thể đáp ứng `skill_id` và quan hệ, theo thứ tự ưu tiên. Chỉ phụ thuộc từ
    điển nên tính một lần rồi nhớ trên chính đối tượng taxonomy (S4-D05: duyệt cây ở mỗi lượt
    chiếm 64% thời gian rank())."""
    cache = tax.__dict__.setdefault("_m_candidates", {}) if hasattr(tax, "__dict__") else {}
    hit = cache.get(skill_id)
    if hit is not None:
        return hit
    out: list[tuple[str, str]] = [(skill_id, "exact")]
    if skill_id in tax:
        # Kỹ năng con và cháu (JD Java, CV Spring Boot).
        stack = list(tax.children(skill_id))
        while stack:
            child = stack.pop()
            out.append((child, "child"))
            stack.extend(tax.children(child))
        parent = tax.get(skill_id).parent
        if parent is not None and tax.get(parent).level >= 2:
            out.append((parent, "parent_only"))
            # Anh em chỉ khi cùng cha cấp 2 (Spring Boot ↔ Hibernate); cùng nhóm cấp 1 không tính.
            out += [(sib, "sibling") for sib in tax.children(parent) if sib != skill_id]
    result = tuple(out)
    cache[skill_id] = result
    return result


def _relations(skill_id: str, cv: Mapping[str, str], tax) -> list[tuple[str, str]]:
    """(kỹ năng CV, quan hệ với kỹ năng JD) theo thứ tự ưu tiên."""
    return [(s, rel) for s, rel in _candidates(skill_id, tax) if s in cv]


def m_score(
    jd_skills: Iterable[tuple[str, str]],
    cv_evidence: Mapping[str, str],
    tax,
    cfg: RankerConfig | None = None,
) -> MatchDetail | None:
    """jd_skills: (skill_id, level) với level required / preferred / mentioned.
    cv_evidence: skill_id → strong / listed / user_added."""
    cfg = cfg or load_ranker_config()
    rows: list[SkillMatchRow] = []
    seen: set[str] = set()
    for skill_id, level in jd_skills:
        r = cfg.req_weight.get(level)
        if r is None or skill_id in seen:  # "chỉ nhắc" không tính; một kỹ năng tính một lần
            continue
        seen.add(skill_id)
        best: tuple | None = None  # (credit, kỹ năng CV, quan hệ, f, bằng chứng)
        for cv_skill, relation in _candidates(skill_id, tax):
            ev = cv_evidence.get(cv_skill)
            if ev is None:
                continue
            factor = cfg.tree[relation]
            credit = factor * cfg.evidence.get(ev, 0.0)
            if best is None or credit > best[0]:
                best = (credit, cv_skill, relation, factor, ev)
        if best is None or best[0] <= 0:
            rows.append(SkillMatchRow(skill_id, level, r, None, None, 0.0, None, 0.0))
        else:
            credit, cv_skill, relation, factor, ev = best
            rows.append(SkillMatchRow(skill_id, level, r, cv_skill, relation, factor, ev, credit))
    if not rows:
        return None
    rows.sort(key=lambda x: (x.level != "required", -x.credit, x.skill_id))
    total = sum(x.weight for x in rows)
    return MatchDetail(sum(x.weight * x.credit for x in rows) / total, rows)


# ---- X ---------------------------------------------------------------------------
def x_score(cv_years: float | None, jd_years: float | None) -> float | None:
    if jd_years is None or jd_years <= 0:
        return None  # JD không yêu cầu: bỏ X, không tự cho 1
    if cv_years is None:
        return None  # CV không tính được số năm: không đoán
    return min(1.0, max(0.0, cv_years) / jd_years)


# ---- H ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Combined:
    h: float | None  # 0–100, làm tròn 1 chữ số; None nếu không thành phần nào xác định
    components: dict[str, float | None]
    weights_used: dict[str, float]  # trọng số sau khi chia lại (tổng = 1)
    missing: list[str]  # thành phần không xác định, vd ["X"]


def combine(components: Mapping[str, float | None], cfg: RankerConfig | None = None) -> Combined:
    cfg = cfg or load_ranker_config()
    comps = {k: components.get(k) for k in COMPONENTS}
    avail = {k: v for k, v in comps.items() if v is not None and cfg.weights.get(k, 0) > 0}
    missing = [k for k, v in comps.items() if v is None]
    wsum = sum(cfg.weights[k] for k in avail)
    if not avail or wsum <= 0:
        return Combined(None, comps, {}, missing)
    used = {k: cfg.weights[k] / wsum for k in avail}
    h = 100 * sum(used[k] * min(1.0, max(0.0, v)) for k, v in avail.items())
    return Combined(round(h + 1e-9, 1), comps, used, missing)
