"""Lớp luật: quyết định mức của một lần nhắc kỹ năng từ section và cue trong câu.

Thứ tự (bậc trong spec S2-D04):
  0  section benefits / other           → DROP
  1  cue phủ định ("không bắt buộc")    → PREFERRED 0.95
  2  section preferred (heading gốc)    → PREFERRED 0.95
  3  chỉ có cue ưu tiên                 → PREFERRED 0.9
  4  có cả hai loại cue                 → cue cùng mục 0.8, không thì cue gần nhất 0.65
  5  section requirements, không cue    → REQUIRED 0.85
  5b chỉ có cue bắt buộc                → REQUIRED 0.75
  -  còn lại                            → None (cascade quyết)
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

from skillkit.levels.norm import norm

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "skill_levels.yaml"
_PAREN = re.compile(r"\([^()]*\)")

# Section dùng trong luật. NONE = JD không có heading (không biết câu thuộc mục nào).
Sec = Literal["DESC", "REQ", "PREF", "BEN", "IGNORE", "NONE"]
Level = Literal["REQUIRED", "PREFERRED", "MENTIONED", "DROP"]


@dataclass(frozen=True)
class Decision:
    level: Level
    conf: float
    source: str  # rule_neg | rule_section | rule_cue | rule_mixed | rule_desc | model | fallback


@dataclass(frozen=True)
class Cues:
    negation: re.Pattern
    preferred: re.Pattern
    required: re.Pattern
    preferred_prefix: re.Pattern
    segment: re.Pattern


@lru_cache(maxsize=4)
def load_cues(path: str | Path = DEFAULT_CONFIG) -> Cues:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["cues"]
    return Cues(**{name: re.compile("|".join(raw[name])) for name in Cues.__annotations__})


def _item_bounds(seg: str, ls: int, le: int) -> tuple[int, int]:
    """Mục chứa kỹ năng trong đoạn: giữa dấu phẩy / ngoặc / "và" / "and" gần nhất hai bên."""
    seps = (",", "(", " va ", " and ")
    left = max(seg.rfind(sep, 0, ls) for sep in seps) + 1
    rights = [x for x in (seg.find(sep, le) for sep in seps) if x >= 0]
    return left, min(rights or [len(seg)])


def _only_later_prefix_cues(
    seg: str, pref: list[tuple[int, int]], ls: int, le: int, cues: Cues
) -> bool:
    """Mọi cue ưu tiên đều là cue đứng trước ("ưu tiên ...") và nằm ở mục SAU kỹ năng.

    "Kinh nghiệm Kubernetes, ưu tiên đã dùng RKE2": "ưu tiên" chỉ áp cho RKE2.
    """
    _, item_end = _item_bounds(seg, ls, le)
    prefix = [m.span() for m in cues.preferred_prefix.finditer(seg)]

    def is_prefix(x: int, y: int) -> bool:
        return any(px < y and x < py for px, py in prefix)  # hai đoạn giao nhau

    return all(x >= item_end and is_prefix(x, y) for x, y in pref)


def decide(
    section: Sec, sentence: str, s: int, e: int, cues: Cues | None = None
) -> Decision | None:
    """[s, e) là vị trí kỹ năng trong `sentence`. None = luật không đủ chắc."""
    if section in ("BEN", "IGNORE"):
        return Decision("DROP", 1.0, "rule_section")
    cues = cues or load_cues()
    text = norm(sentence)
    a, b = 0, len(text)
    for m in cues.segment.finditer(text):
        if m.end() <= s:
            a = m.end()
        elif m.start() >= e:
            b = m.start()
            break
    seg, ls, le = text[a:b], s - a, e - a

    if cues.negation.search(seg):
        return Decision("PREFERRED", 0.95, "rule_neg")
    if section == "PREF":
        return Decision("PREFERRED", 0.95, "rule_section")
    # Cụm trong ngoặc có cue ưu tiên chỉ áp cho kỹ năng trong ngoặc:
    # "ít nhất một ngôn ngữ (ưu tiên Python, JavaScript) hoặc scripting (Bash)".
    for m in _PAREN.finditer(seg):
        x, y = m.span()
        if not cues.preferred.search(seg[x:y]):
            continue
        if x < ls and le <= y:
            return Decision("PREFERRED", 0.9, "rule_cue")
        seg = seg[:x] + " " * (y - x) + seg[y:]  # che đi, giữ nguyên vị trí
    pref = [m.span() for m in cues.preferred.finditer(seg)]
    # "ưu tiên thành thạo X": "thành thạo" nằm trong cue ưu tiên, không tính là cue bắt buộc.
    req = [
        (x, y)
        for x, y in (m.span() for m in cues.required.finditer(seg))
        if not any(px < y and x < py for px, py in pref)
    ]
    if pref and not req:
        if _only_later_prefix_cues(seg, pref, ls, le, cues) and section == "REQ":
            return Decision("REQUIRED", 0.8, "rule_cue")
        return Decision("PREFERRED", 0.9, "rule_cue")
    if pref:  # câu trộn hai mức
        ia, ib = _item_bounds(seg, ls, le)
        in_pref = any(x >= ia and y <= ib for x, y in pref)
        in_req = any(x >= ia and y <= ib for x, y in req)
        if in_pref != in_req:
            return Decision("PREFERRED" if in_pref else "REQUIRED", 0.8, "rule_mixed")

        def dist(spans: list[tuple[int, int]]) -> int:
            return min(min(abs(x - le), abs(y - ls)) for x, y in spans)

        return Decision("PREFERRED" if dist(pref) < dist(req) else "REQUIRED", 0.65, "rule_mixed")
    if section == "REQ":
        return Decision("REQUIRED", 0.85, "rule_section")
    if req:
        return Decision("REQUIRED", 0.75, "rule_cue")
    return None
