"""Suy cấp bậc tin tuyển dụng (core.seniority) cho bộ lọc "Cấp bậc" trên web.

Trước đây không bước nào ghi core.jobs.seniority nên mọi tin là 'unknown' và lọc theo cấp bậc
luôn ra 0 kết quả. Luật nằm ở config/seniority.yaml; thứ tự tín hiệu:
  1. source  ô cấp bậc của nguồn (TopCV job_level; VietnamWorks jobLevelId 3/7)
  2. title   từ khóa trong tiêu đề (Senior, Lead, Trưởng phòng, Intern...), cấp cao xét trước
  3. years   số năm kinh nghiệm tối thiểu (TopCV "2 năm", VietnamWorks monthsOfExperience)
Không có tín hiệu → 'unknown'.
"""

import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from skillkit.sections import fold

Level = Literal["intern", "fresher", "junior", "middle", "senior", "lead", "manager", "unknown"]
Method = Literal["source", "title", "years", "none"]
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "seniority.yaml"


class _Rules:
    def __init__(self, data: dict) -> None:
        self.title = [
            (level, re.compile("|".join(patterns))) for level, patterns in data["title"].items()
        ]
        self.ignore = (
            re.compile("|".join(data.get("title_ignore", []))) if data.get("title_ignore") else None
        )
        self.source_text = [
            (level, [fold(x) for x in words]) for level, words in data["source_text"].items()
        ]
        self.vnw = {int(k): v for k, v in data.get("vietnamworks_level_id", {}).items()}
        self.years = [(float(lo), float(hi), level) for lo, hi, level in data["years"]]


@lru_cache(maxsize=4)
def load_rules(path: str | Path = DEFAULT_CONFIG) -> _Rules:
    return _Rules(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def from_title(title: str | None, rules: _Rules | None = None) -> Level | None:
    rules = rules or load_rules()
    key = fold(title or "").replace("/", " / ")
    if rules.ignore:
        key = rules.ignore.sub(" ", key)
    for level, pattern in rules.title:
        if pattern.search(key):
            return level
    return None


def from_source(
    level_text: str | None, vnw_level_id: Any = None, rules: _Rules | None = None
) -> Level | None:
    rules = rules or load_rules()
    try:
        vnw = rules.vnw.get(int(vnw_level_id)) if vnw_level_id not in (None, "") else None
    except (TypeError, ValueError):
        vnw = None
    if vnw:
        return vnw
    key = fold(level_text or "")
    if not key:
        return None
    for level, words in rules.source_text:
        if any(w in key for w in words):
            return level
    return None


def from_years(years: float | None, rules: _Rules | None = None) -> Level | None:
    rules = rules or load_rules()
    if years is None:
        return None
    for lo, hi, level in rules.years:
        if lo <= float(years) < hi:
            return level
    return None


def infer_seniority(
    title: str | None,
    years_exp_min: float | None = None,
    source_level_text: str | None = None,
    vnw_level_id: Any = None,
) -> tuple[Level, Method]:
    rules = load_rules()
    if level := from_source(source_level_text, vnw_level_id, rules):
        return level, "source"
    if level := from_title(title, rules):
        return level, "title"
    if level := from_years(years_exp_min, rules):
        return level, "years"
    return "unknown", "none"


def source_signals(payload: Mapping[str, Any] | None) -> tuple[str | None, Any]:
    """(ô cấp bậc dạng chữ, jobLevelId VietnamWorks) từ payload gốc (raw.job_snapshots)."""
    payload = payload or {}
    vnw = payload.get("vnw") if isinstance(payload.get("vnw"), dict) else {}
    return payload.get("job_level") or None, vnw.get("jobLevelId")
