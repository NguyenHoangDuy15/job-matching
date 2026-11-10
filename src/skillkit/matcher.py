"""Tầng 1 trích kỹ năng: FlashText trên từ điển + quy tắc từ nhập nhằng (S2-D03, US-10).

Điểm then chốt: so khớp trên bản chữ thường nhưng đọc lại đúng đoạn gốc (giữ chữ hoa)
để phân biệt "Go" (ngôn ngữ) với "go live", "R" với "R&D", "C" với "hạng C".
Hai bản `cased` và `lower` luôn dài bằng nhau nên vị trí khớp dùng chung được.
"""

import re
import unicodedata
from dataclasses import dataclass

from flashtext import KeywordProcessor

from skillkit.taxonomy import Skill, Taxonomy

# flashtext coi chữ có dấu là ranh giới từ; thêm vào để "cơ" không khớp "c".
# Không thêm "." để "C#." và "Go." ở cuối câu vẫn khớp.
_LETTERS_WITH_MARKS = {chr(c) for c in range(0xC0, 0x2000) if chr(c).isalpha()}
_NON_WORD_BOUNDARIES = {"+", "#"} | _LETTERS_WITH_MARKS
# Khoảng giữa hai kỹ năng trong một danh sách: "Python, R", "C/C++", "Java và Go".
_LIST_GAP = re.compile(r"^\s*(?:[,/;|&+()\[\]•·-]\s*)*(?:(?:and|or|và|hoặc)\s*)?(?:[,/;|&()]\s*)*$")


@dataclass(frozen=True)
class SkillMatch:
    skill_id: str
    term: str  # cách viết trong từ điển đã khớp (chữ thường)
    start: int  # vị trí trong văn bản đã chuẩn hóa khoảng trắng
    end: int
    surface: str  # đoạn gốc, giữ chữ hoa


def prepare(text: str) -> tuple[str, str]:
    """(cased, lower): NFC + gộp khoảng trắng; lower giữ nguyên độ dài từng ký tự."""
    cased = " ".join(unicodedata.normalize("NFC", text).split())
    lower = "".join(ch.lower() if len(ch.lower()) == 1 else ch for ch in cased)
    return cased, lower


def _norm(term: str) -> str:
    return prepare(term)[1]


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(phrase)}(?![\w])", text) is not None


class SkillMatcher:
    def __init__(self, taxonomy: Taxonomy) -> None:
        self._processor = KeywordProcessor()
        for char in _NON_WORD_BOUNDARIES:
            self._processor.add_non_word_boundary(char)
        self._owner: dict[str, Skill] = {}
        for skill in taxonomy:
            if skill.level == 1:
                continue
            for term in skill.terms():
                key = _norm(term)
                self._owner[key] = skill
                self._processor.add_keyword(key, key)

    def find(self, text: str | None) -> list[SkillMatch]:
        """Mọi lần khớp được chấp nhận, theo thứ tự xuất hiện."""
        if not text:
            return []
        cased, lower = prepare(text)
        raw = [
            SkillMatch(self._owner[key].id, key, start, end, cased[start:end])
            for key, start, end in self._processor.extract_keywords(lower, span_info=True)
        ]
        certain = [m for m in raw if not self._needs_check(m)]
        accepted = {(m.start, m.end) for m in certain}
        # Hai lượt: kỹ năng nhập nhằng đã nhận ở lượt 1 làm hàng xóm cho lượt 2 ("R, Go").
        for _ in range(2):
            anchors = [m for m in raw if (m.start, m.end) in accepted]
            for m in raw:
                if (m.start, m.end) not in accepted and self._accept(m, cased, lower, anchors):
                    accepted.add((m.start, m.end))
        return [m for m in raw if (m.start, m.end) in accepted]

    def skills(self, text: str | None) -> list[str]:
        """Id kỹ năng không trùng, theo thứ tự xuất hiện đầu tiên."""
        return list(dict.fromkeys(m.skill_id for m in self.find(text)))

    def match_list(self, items: list[str]) -> list[list[str]]:
        """Kỹ năng của từng mục trong một danh sách kỹ năng có sẵn (JSON-LD `skills`,
        cột technical_skills), cùng thứ tự với `items`.

        Mỗi mục đã là một kỹ năng, nên từ nhập nhằng được nhận khi nó là CẢ mục ("Go", "R")
        mà không cần đúng chữ hoa hay từ ngữ cảnh. Cụm loại và từ veto vẫn áp dụng trên cả
        danh sách ("Photoshop, AI, Illustrator" không ra Trí tuệ nhân tạo).
        """
        cleaned = [prepare(str(i))[0] for i in items]
        cased, lower = prepare(", ".join(cleaned))
        spans, pos = [], 0
        for item in cleaned:
            spans.append((pos, pos + len(item)))
            pos += len(item) + 2
        accepted = {(m.start, m.end) for m in self.find(cased)}
        result: list[list[str]] = [[] for _ in cleaned]
        for key, start, end in self._processor.extract_keywords(lower, span_info=True):
            m = SkillMatch(self._owner[key].id, key, start, end, cased[start:end])
            whole_item = (start, end) in spans and not self._rejected(m, lower)
            if (start, end) in accepted or whole_item:
                for idx, (lo, hi) in enumerate(spans):
                    if lo <= start and end <= hi and m.skill_id not in result[idx]:
                        result[idx].append(m.skill_id)
        return result

    def skills_from_list(self, items: list[str]) -> list[str]:
        """Id kỹ năng không trùng của cả danh sách (xem match_list)."""
        return list(dict.fromkeys(sid for per_item in self.match_list(items) for sid in per_item))

    def _needs_check(self, match: SkillMatch) -> bool:
        return match.term in self._owner[match.term].ambiguous_terms()

    def _accept(self, m: SkillMatch, cased: str, lower: str, anchors: list[SkillMatch]) -> bool:
        skill = self._owner[m.term]
        rule = skill.rule
        if rule and rule.forms and m.surface not in rule.forms:
            return False
        if self._rejected(m, lower):
            return False
        if any(self._is_list_neighbour(m, a, lower) for a in anchors if a.skill_id != m.skill_id):
            return True
        return any(_contains_phrase(self._window(m, lower), _norm(w)) for w in skill.context)

    def _window(self, m: SkillMatch, lower: str) -> str:
        rule = self._owner[m.term].rule
        window = rule.window if rule else 6
        before = lower[: m.start].split()[-window:]
        after = lower[m.end :].split()[:window]
        return " ".join([*before, "|", *after])

    def _rejected(self, m: SkillMatch, lower: str) -> bool:
        """Nằm trong cụm loại ("R&D", "go live") hoặc có từ veto trong cửa sổ."""
        rule = self._owner[m.term].rule
        if rule is None:
            return False
        for phrase in rule.reject:
            p = _norm(phrase)
            lo, hi = max(0, m.start - len(p)), m.end + len(p)
            for hit in re.finditer(re.escape(p), lower[lo:hi]):
                if lo + hit.start() <= m.start and lo + hit.end() >= m.end:
                    return True
        around = self._window(m, lower)
        return any(_contains_phrase(around, _norm(v)) for v in rule.veto)

    @staticmethod
    def _is_list_neighbour(m: SkillMatch, other: SkillMatch, lower: str) -> bool:
        if other.end <= m.start:
            gap = lower[other.end : m.start]
        elif other.start >= m.end:
            gap = lower[m.end : other.start]
        else:
            return False
        return len(gap) <= 6 and _LIST_GAP.match(gap) is not None
