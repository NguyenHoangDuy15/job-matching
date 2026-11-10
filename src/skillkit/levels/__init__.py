"""S2-D04: gắn mức required / preferred / mentioned cho kỹ năng trong JD (US-10).

Tầng 1 là SkillMatcher (từ điển, S2-D03). Lớp luật xét section và cue trong câu.
Tầng 2 "JEV-local" (TF-IDF + LogReg) chỉ quyết các ca luật không chắc.
"""

from skillkit.levels.cascade import JobSkill, Mention, aggregate, label_mention
from skillkit.levels.pipeline import SkillLabeler
from skillkit.levels.rules import Decision, decide
from skillkit.levels.tier2 import JevLocal, Tier2Classifier, build_model, prep

__all__ = [
    "Decision",
    "JevLocal",
    "JobSkill",
    "Mention",
    "SkillLabeler",
    "Tier2Classifier",
    "aggregate",
    "build_model",
    "decide",
    "label_mention",
    "prep",
]
