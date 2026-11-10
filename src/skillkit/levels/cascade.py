"""Ghép luật + Tầng 2 cho từng lần nhắc kỹ năng, rồi gộp về một nhãn cho mỗi (job, skill)."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from skillkit.levels.rules import DEFAULT_CONFIG, Cues, Decision, Sec, decide
from skillkit.levels.tier2 import Tier2Classifier

# Cùng một kỹ năng nhắc nhiều lần: nguồn mạnh hơn thắng; cùng hạng thì required thắng.
SOURCE_RANK = {
    "human": 6,
    "rule_neg": 5,
    "rule_section": 5,
    "rule_cue": 4,
    "model": 3,
    "rule_mixed": 3,
    "fallback": 1,
    "rule_desc": 0,
}


@dataclass(frozen=True)
class CascadeConfig:
    tau: float = 0.7
    flip_required: float = 0.9
    model_path: str = "models/jev_local_v1.joblib"


@lru_cache(maxsize=4)
def load_cascade_config(path: str | Path = DEFAULT_CONFIG) -> CascadeConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")).get("cascade", {})
    return CascadeConfig(**raw)


@dataclass(frozen=True)
class Mention:
    jd_id: str
    skill_id: str  # slug trong config/skills.yaml (= ref.skills.slug)
    skill_text: str  # đoạn gốc trong câu
    section: Sec
    sentence: str
    s: int
    e: int
    jd_has_sections: bool = True


@dataclass(frozen=True)
class JobSkill:
    jd_id: str
    skill_id: str
    level: str  # required | preferred | mentioned (khớp enum core.req_level)
    confidence: float
    source: str  # nguồn chi tiết (rule_cue, model, ...)
    section: Sec
    evidence: str
    mention_count: int

    @property
    def extractor(self) -> str:
        """Giá trị enum core.extractor: model → jev, luật → dict."""
        return "jev" if self.source == "model" else "dict"


def _from_model(p: float) -> Decision:
    return Decision("PREFERRED" if p >= 0.5 else "REQUIRED", max(p, 1 - p), "model")


def label_mention(
    m: Mention,
    clf: Tier2Classifier | None,
    config: CascadeConfig | None = None,
    cues: Cues | None = None,
) -> Decision:
    config = config or load_cascade_config()
    d = decide(m.section, m.sentence, m.s, m.e, cues)
    req_by_section = d is not None and d.source == "rule_section" and m.section == "REQ"
    if d is not None and d.source != "rule_mixed" and not req_by_section:
        return d  # bậc 0–3, 5b: luật đủ chắc
    if d is None and m.section == "DESC":
        # Chỉ được nhắc trong mô tả công việc, không có cue: không coi là yêu cầu.
        return Decision("MENTIONED", 0.6, "rule_desc")
    p = clf.prob_preferred(m.section, m.sentence, m.skill_text) if clf else None
    if d is not None and d.source == "rule_mixed":  # bậc 4
        # Silver chưa có câu trộn (chưa gán ca khó) nên model chỉ thay luật "cue gần nhất"
        # (conf < τ); luật "cue cùng mục" (0.8) giữ nguyên.
        sure = d.conf < config.tau and p is not None and max(p, 1 - p) >= config.tau
        return _from_model(p) if sure else d
    if d is not None:  # bậc 5: model chỉ lật khi rất chắc
        return (
            Decision("PREFERRED", p, "model") if p is not None and p >= config.flip_required else d
        )
    if p is not None and max(p, 1 - p) >= config.tau:  # bậc 6, JD không heading
        return _from_model(p)
    return Decision("REQUIRED", 0.5, "fallback")


def aggregate(labeled: list[tuple[Mention, Decision]]) -> list[JobSkill]:
    """Mỗi (jd_id, skill_id) một dòng. mentioned luôn thua mọi mức khác."""
    best: dict[tuple[str, str], tuple[tuple, Mention, Decision]] = {}
    counts: dict[tuple[str, str], int] = {}
    for m, d in labeled:
        if d.level == "DROP":
            continue
        key = (m.jd_id, m.skill_id)
        counts[key] = counts.get(key, 0) + 1
        rank = (d.level != "MENTIONED", SOURCE_RANK[d.source], d.level == "REQUIRED", d.conf)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, m, d)
    return [
        JobSkill(
            jd_id=m.jd_id,
            skill_id=m.skill_id,
            level=d.level.lower(),
            confidence=round(d.conf, 3),
            source=d.source,
            section=m.section,
            evidence=m.sentence,
            mention_count=counts[key],
        )
        for key, (_, m, d) in best.items()
    ]
