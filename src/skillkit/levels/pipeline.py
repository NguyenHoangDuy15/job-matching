"""Pipeline 2 tầng cho một JD: tách câu → Tầng 1 (từ điển) → luật → Tầng 2 → gộp.

labeler = SkillLabeler.default()
rows = labeler.label_text("123", jd_text)               # toàn văn JD
rows = labeler.label_columns("123", {"requirements": ...})  # 4 cột section trong core.jobs
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from skillkit.levels.cascade import (
    CascadeConfig,
    JobSkill,
    Mention,
    aggregate,
    label_mention,
    load_cascade_config,
)
from skillkit.levels.rules import Cues, Decision, Sec, load_cues
from skillkit.levels.tier2 import Tier2Classifier, load_tier2
from skillkit.matcher import SkillMatcher, prepare
from skillkit.sections import _is_preferred, assign_lines, default_headings
from skillkit.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[3]
RULES_VERSION = "rules-v1"
_SECTION = {
    "description": "DESC",
    "requirements": "REQ",
    "preferred": "PREF",
    "benefits": "BEN",
    "other": "IGNORE",
}
SECTION_COLUMNS = ("description", "requirements", "preferred", "benefits")
_PARENS = re.compile(r"\([^()]*\)")


def rule_section(label: str, line: str, has_sections: bool) -> Sec:
    """Section dùng cho luật, theo heading GỐC của dòng.

    D03 chuyển cả dòng "Biết Java là bắt buộc, Spring Boot là lợi thế" từ Yêu cầu sang
    Ưu tiên. Nếu luật đọc section đã chuyển, Java sẽ thành preferred. Dòng nào bị chuyển vì
    có dấu hiệu ưu tiên thì trả về REQ để luật xét cue theo từng vế. Riêng dòng bị chuyển chỉ
    vì cụm trong ngoặc "(điểm cộng, không bắt buộc)" thì cả dòng là ưu tiên → giữ PREF.
    """
    if not has_sections:
        return "NONE"
    lex = default_headings()
    if label == "preferred" and _is_preferred(line, lex):
        return "REQ" if _is_preferred(_PARENS.sub(" ", line), lex) else "PREF"
    return _SECTION[label]


@dataclass
class SkillLabeler:
    matcher: SkillMatcher
    clf: Tier2Classifier | None = None
    config: CascadeConfig | None = None
    cues: Cues | None = None

    @classmethod
    def default(cls, with_model: bool = True) -> "SkillLabeler":
        config = load_cascade_config()
        clf = load_tier2(ROOT / config.model_path) if with_model else None
        matcher = SkillMatcher(load_taxonomy(ROOT / "config" / "skills.yaml"))
        return cls(matcher, clf, config, load_cues())

    @property
    def model_version(self) -> str:
        return f"dict+{RULES_VERSION}+{self.clf.version if self.clf else 'no-model'}"

    def mentions(
        self, jd_id: str, lines: Iterable[tuple[str, str]], has_sections: bool
    ) -> list[Mention]:
        """lines: (dòng, nhãn D03: description/requirements/preferred/benefits/other/heading)."""
        out = []
        for line, label in lines:
            if label == "heading":
                continue
            sentence = prepare(line)[0]  # vị trí của SkillMatcher tính trên bản này
            section = rule_section(label, line, has_sections)
            for hit in self.matcher.find(sentence):
                out.append(
                    Mention(
                        jd_id,
                        hit.skill_id,
                        hit.surface,
                        section,
                        sentence,
                        hit.start,
                        hit.end,
                        has_sections,
                    )
                )
        return out

    def decide_all(self, mentions: list[Mention]) -> list[tuple[Mention, Decision]]:
        return [(m, label_mention(m, self.clf, self.config, self.cues)) for m in mentions]

    def text_mentions(self, jd_id: str, jd_text: str) -> list[Mention]:
        lines = assign_lines(jd_text)
        return self.mentions(jd_id, lines, any(label == "heading" for _, label in lines))

    def column_mentions(self, jd_id: str, columns: Mapping[str, str | None]) -> list[Mention]:
        lines = [
            (line, name)
            for name in SECTION_COLUMNS
            for line in (columns.get(name) or "").splitlines()
            if line.strip()
        ]
        has_sections = any(columns.get(n) for n in ("requirements", "preferred", "benefits"))
        return self.mentions(jd_id, lines, has_sections)

    def label_text(self, jd_id: str, jd_text: str) -> list[JobSkill]:
        return aggregate(self.decide_all(self.text_mentions(jd_id, jd_text)))

    def label_columns(self, jd_id: str, columns: Mapping[str, str | None]) -> list[JobSkill]:
        return aggregate(self.decide_all(self.column_mentions(jd_id, columns)))
