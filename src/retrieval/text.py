"""Cắt từ cho BM25, dùng chung cho tin và cho CV (S4-D01).

1. Kỹ năng trong từ điển (SkillMatcher, S2-D03) → một token chuẩn "sk:<skill_id>": "ReactJS",
   "React.js", "react" cùng ra "sk:react", nên CV chỉ cần hỏi đúng token đó.
2. Phần còn lại: chữ thường, bỏ dấu (đ → d), cắt theo âm tiết, bỏ stopword.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from skillkit.matcher import SkillMatcher, prepare
from skillkit.sections import fold

ROOT = Path(__file__).resolve().parents[2]
RANKER_CONFIG = ROOT / "config" / "ranker_config.yaml"
SKILL_PREFIX = "sk:"
_WORD = re.compile(r"[a-z0-9]+(?:[+#][+#]?)?")


@dataclass(frozen=True)
class KeywordConfig:
    k1: float
    b: float
    method: str
    field_weights: dict[str, int]
    query_weights: dict[str, int]
    min_token_len: int
    refresh_seconds: int
    stopwords: frozenset[str]


@lru_cache(maxsize=4)
def load_keyword_config(path: str | Path = RANKER_CONFIG) -> KeywordConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["keyword"]
    return KeywordConfig(
        k1=float(data["bm25"]["k1"]),
        b=float(data["bm25"]["b"]),
        method=str(data["bm25"]["method"]),
        field_weights={k: int(v) for k, v in data["field_weights"].items()},
        query_weights={k: int(v) for k, v in data["query_weights"].items()},
        min_token_len=int(data["min_token_len"]),
        refresh_seconds=int(data["refresh_seconds"]),
        stopwords=frozenset(data["stopwords"]),
    )


@lru_cache(maxsize=1)
def default_matcher() -> SkillMatcher:
    from skillkit.levels.pipeline import SKILLS_YAML
    from skillkit.taxonomy import load_taxonomy

    return SkillMatcher(load_taxonomy(SKILLS_YAML))


def skill_token(skill_id: str) -> str:
    return f"{SKILL_PREFIX}{skill_id}"


class Analyzer:
    """Văn bản → danh sách token. Một đối tượng dùng cho cả index và truy vấn."""

    def __init__(self, cfg: KeywordConfig | None = None, matcher: SkillMatcher | None = None):
        self.cfg = cfg or load_keyword_config()
        self.matcher = matcher or default_matcher()

    def _words(self, text: str) -> list[str]:
        out = []
        for w in _WORD.findall(fold(text)):
            if w in self.cfg.stopwords:
                continue
            if len(w) < self.cfg.min_token_len and not w.isdigit():
                continue
            out.append(w)
        return out

    def tokens(self, text: str | None) -> list[str]:
        if not text or not text.strip():
            return []
        cased, _ = prepare(text)
        out: list[str] = []
        pos = 0
        for m in self.matcher.find(text):  # vị trí tính trên chuỗi đã prepare()
            out += self._words(cased[pos : m.start])
            out.append(skill_token(m.skill_id))
            pos = m.end
        out += self._words(cased[pos:])
        return out
