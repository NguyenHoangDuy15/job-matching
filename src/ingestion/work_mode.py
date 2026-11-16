"""Suy hình thức làm việc (core.work_mode) từ tiêu đề, địa điểm VÀ nội dung JD.

Trước đây ingestion.location.detect_work_mode chỉ đọc chuỗi địa điểm + tiêu đề, nên tin ghi
"Chế độ làm việc: Hybrid, remote 1 ngày/tuần" trong phần Quyền lợi vẫn là onsite. Luật nằm ở
config/work_mode.yaml; thứ tự:
  1. JSON-LD TELECOMMUTE → remote
  2. bỏ thuật ngữ kỹ thuật (Hybrid Cloud, remote access...) và câu phủ định ("không remote")
  3. remote toàn phần → remote; ngày làm từ xa hằng tuần / "hybrid working" → hybrid
  4. có tỉnh → onsite (mặc định, đúng với phần lớn tin); không có gì → unknown
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

from skillkit.sections import fold

WorkMode = Literal["onsite", "hybrid", "remote", "unknown"]
Method = Literal["telecommute", "text", "province", "none"]
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "work_mode.yaml"


class _Rules:
    def __init__(self, data: dict) -> None:
        def join(key: str) -> re.Pattern | None:
            items = data.get(key) or []
            return re.compile("|".join(f"(?:{p})" for p in items)) if items else None

        self.exclude = join("exclude")
        self.negation = join("negation")
        self.remote = join("remote")
        self.hybrid = join("hybrid")
        head = data.get("head") or {}
        self.head = [
            (mode, re.compile(head[mode])) for mode in ("hybrid", "remote") if mode in head
        ]


@lru_cache(maxsize=4)
def load_rules(path: str | Path = DEFAULT_CONFIG) -> _Rules:
    return _Rules(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _clean(text: str, rules: _Rules) -> str:
    key = " ".join(fold(text).replace("–", "-").replace("—", "-").split())
    for pattern in (rules.exclude, rules.negation):
        if pattern:
            key = pattern.sub(" ", key)
    return key


def mode_from_text(text: str | None, rules: _Rules | None = None) -> WorkMode | None:
    """remote / hybrid nếu văn bản nói rõ, không thì None."""
    rules = rules or load_rules()
    key = _clean(text or "", rules)
    if rules.remote and rules.remote.search(key):
        return "remote"
    if rules.hybrid and rules.hybrid.search(key):
        return "hybrid"
    return None


def mode_from_head(title: str | None, location: str | None, rules: _Rules | None = None):
    """Tiêu đề / địa điểm: "(Remote)", "Hybrid Work" là đủ (sau khi bỏ thuật ngữ kỹ thuật)."""
    rules = rules or load_rules()
    key = _clean(f"{title or ''} \n {location or ''}", rules)
    for mode, pattern in rules.head:
        if pattern.search(key):
            return mode
    return None


def evidence(text: str | None, rules: _Rules | None = None) -> str | None:
    """Đoạn văn bản đã khớp (để kiểm tay và báo cáo)."""
    rules = rules or load_rules()
    key = _clean(text or "", rules)
    for pattern in (rules.remote, rules.hybrid):
        m = pattern.search(key) if pattern else None
        if m:
            return key[max(0, m.start() - 40) : m.end() + 40]
    return None


def infer_work_mode(
    title: str | None,
    location: str | None,
    jd_text: str | None,
    *,
    has_province: bool,
    telecommute: bool = False,
) -> tuple[WorkMode, Method]:
    if telecommute:
        return "remote", "telecommute"
    head = mode_from_head(title, location)
    if head:
        return head, "text"
    body = mode_from_text(jd_text)
    if body:
        return body, "text"
    if has_province:
        return "onsite", "province"
    return "unknown", "none"
