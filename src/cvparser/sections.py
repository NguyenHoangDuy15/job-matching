"""Tách section CV Việt–Anh (S3-D02, US-12): dòng nào thuộc mục nào.

    from cvparser.sections import split_sections
    secs = split_sections(result.text, result.blocks)   # result: ExtractionResult của D01
    secs.section_at(offset)        # S3-D04: kỹ năng ở offset này nằm ở mục nào → strong/listed
    secs.to_jsonb()                # S3-D05: app.cvs.parsed_sections

Chạy bằng luật + từ điển config/cv_headings.yaml, không gọi dịch vụ ngoài. Thứ tự:
  1. Dòng khớp từ điển tên mục (bỏ ký tự đầu dòng, số thứ tự, dấu; ngắn, không có dấu chấm cuối).
     "Kỹ năng: Python, SQL" là heading kèm nội dung.
  2. Đang ở Kinh nghiệm/Dự án mà gặp "Dự án: …", "Công nghệ: …" (có nội dung sau ":") thì là mục
     con của một việc, KHÔNG mở mục mới (cả hai đều là bằng chứng strong ở D04).
  3. Heading lạ (ngắn, IN HOA hoặc style Heading của DOCX, sau đó ≥ 2 dòng nội dung) → đoán theo
     nội dung (khoảng thời gian, từ học vấn...). Không đủ chắc → other.
  4. Dòng trước heading đầu tiên → header (tên, chức danh, liên hệ). Không thấy heading nào →
     cả CV là other, method="fallback".

Offset dùng chung với text truyền vào. S3-D05 nên gọi hàm này trên văn bản ĐÃ che PII
(heading không chứa PII nên kết quả như nhau) để offset khớp app.cvs.text_redacted.
"""

import bisect
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from skillkit.sections import fold

SectionName = Literal[
    "header", "summary", "experience", "projects", "education", "skills",
    "certifications", "languages", "activities", "other",
]  # fmt: skip
Method = Literal["lexicon", "inferred", "preamble", "fallback"]
SECTION_NAMES: tuple[str, ...] = SectionName.__args__
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "cv_headings.yaml"
# Mục mà mọi "Tên: nội dung" bên trong được coi là mục con (dự án, công nghệ của một việc).
_KEEP_INLINE = {"experience", "projects"}

_BULLET = re.compile(
    r"^(?:[-–—•●▪■◦*+►▶➢✓✔#|]+|[-]|(?:\d{1,2}|[IVX]{1,4}|[A-E])[.)/]|\d{2}(?=\s))\s*"
)
_DATE_RANGE = re.compile(
    r"(?:\d{1,2}\s*/\s*)?(?:19|20)\d{2}\s*[-–—~]+\s*"
    r"(?:(?:\d{1,2}\s*/\s*)?(?:19|20)\d{2}|nay|hien tai|present|now|current|today)"
)
_SENTENCE_END = (".", ",", ";", "!", "?")


class CvSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: SectionName
    heading: str | None = None  # tiêu đề gốc trong CV
    method: Method
    start: int  # nội dung (không gồm dòng heading), offset trong text
    end: int
    text: str


class CvSections(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    sections: list[CvSection]
    headings: list[tuple[int, int, SectionName]] = []  # (start, end, mục) của dòng heading

    def section_at(self, offset: int) -> SectionName:
        """Mục chứa vị trí `offset` (dòng heading thuộc mục nó mở)."""
        for start, end, name in self.headings:
            if start <= offset < end:
                return name
        starts = [s.start for s in self.sections]
        i = bisect.bisect_right(starts, offset) - 1
        return self.sections[i].name if i >= 0 else "header"

    def by_name(self, name: SectionName) -> list[CvSection]:
        return [s for s in self.sections if s.name == name]

    def to_jsonb(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for s in self.sections:
            if s.text.strip():
                out.setdefault(s.name, []).append(s.text.strip())
        return out


class _Lexicon(BaseModel):
    version: str
    phrases: list[tuple[str, str]]  # (cụm đã chuẩn hóa, section), dài trước
    max_extra_words: int
    max_heading_words: int
    unknown_max_words: int
    unknown_min_hits: int
    cues: dict[str, list[str]]
    date_points: int


def _key(text: str) -> str:
    """fold() + '&'/'and' → 'va', bỏ dấu câu thừa: dạng so khớp của heading."""
    k = fold(text).replace("&", " va ").replace("+", " va ")
    k = re.sub(r"\band\b", "va", k)
    k = re.sub(r"[^\w\s/]", " ", k).replace("/", " va ")
    return " ".join(k.split())


@lru_cache(maxsize=4)
def load_lexicon(path: str | Path = DEFAULT_CONFIG) -> _Lexicon:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    phrases: dict[str, str] = {}
    for name, items in data["sections"].items():
        if name not in SECTION_NAMES:
            raise ValueError(f"section lạ trong {path}: {name}")
        for item in items:
            key = _key(item)
            if phrases.setdefault(key, name) != name:
                raise ValueError(f"heading '{item}' thuộc cả {phrases[key]} và {name}")
    unknown = data.get("unknown_heading", {})
    return _Lexicon(
        version=data["version"],
        phrases=sorted(phrases.items(), key=lambda kv: -len(kv[0].split())),
        max_extra_words=int(data.get("max_extra_words", 2)),
        max_heading_words=int(data.get("max_heading_words", 8)),
        unknown_max_words=int(unknown.get("max_words", 6)),
        unknown_min_hits=int(unknown.get("min_hits", 2)),
        cues={k: [_key(c) for c in v] for k, v in unknown.get("cues", {}).items()},
        date_points=int(unknown.get("date_range_points", 1)),
    )


def strip_bullet(line: str) -> str:
    previous = None
    line = line.strip()
    while previous != line:
        previous, line = line, _BULLET.sub("", line, count=1).strip()
    return line.strip("*_ ")


def match_heading(line: str, lex: _Lexicon | None = None) -> tuple[str, int] | None:
    """(section, vị trí bắt đầu nội dung cùng dòng trong `line`; -1 nếu không có) hoặc None."""
    lex = lex or load_lexicon()
    body = strip_bullet(line)
    if not body:
        return None
    colon = re.search(r"[:：]", body)
    head, sep, rest = (
        (body[: colon.start()], colon.group(), body[colon.end() :]) if colon else (body, "", "")
    )
    key = _key(head)
    words = key.split()
    if not words or len(words) > lex.max_heading_words:
        return None
    for phrase, name in lex.phrases:
        if key != phrase and not key.startswith(phrase + " "):
            continue
        extra = key[len(phrase) :].split()
        joined = bool(extra) and extra[0] == "va"  # "Học vấn & Chứng chỉ"
        if sep:
            if extra and not joined:  # "Kinh nghiệm làm việc với Java: …" là câu
                return None
            content = rest.strip()
            return name, (line.rfind(content) if content else -1)
        if (len(extra) > lex.max_extra_words and not joined) or body.endswith(_SENTENCE_END):
            return None
        if any(ch.isdigit() for ch in " ".join(extra)):  # "Kinh nghiệm 3 năm Java"
            return None
        return name, -1
    return None


def _looks_like_heading(line: str, styled: bool, lex: _Lexicon) -> bool:
    body = strip_bullet(line)
    if not body or body.endswith(_SENTENCE_END) or "@" in body or any(c.isdigit() for c in body):
        return False
    if len(body.split()) > lex.unknown_max_words:
        return False
    return styled or _is_caps(body)


def _is_caps(line: str) -> bool:
    letters = [c for c in strip_bullet(line) if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def _infer(block: list[str], lex: _Lexicon) -> str | None:
    text = " " + " ".join(_key(x) for x in block) + " "
    scores = {
        name: sum(len(re.findall(rf"(?<!\w){re.escape(c)}(?!\w)", text)) for c in cues)
        for name, cues in lex.cues.items()
    }
    dates = sum(bool(_DATE_RANGE.search(fold(x))) for x in block) * lex.date_points
    scores["experience"] = scores.get("experience", 0) + dates
    if scores.get("education", 0):
        scores["education"] += dates  # khoảng thời gian cũng có ở học vấn
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, top = ranked[0]
    if top < lex.unknown_min_hits or (len(ranked) > 1 and ranked[1][1] == top):
        return None
    return best


def split_sections(text: str, blocks=None, lex: _Lexicon | None = None) -> CvSections:
    """`blocks`: ExtractionResult.blocks (tùy chọn) để dùng style Heading của DOCX."""
    lex = lex or load_lexicon()
    styled = {b.start for b in blocks or [] if getattr(b, "kind", None) == "heading"}
    lines: list[tuple[int, int, str]] = []
    pos = 0
    for raw in text.split("\n"):
        if raw.strip():
            lines.append((pos, pos + len(raw), raw))
        pos += len(raw) + 1

    # (offset bắt đầu nội dung, section, heading gốc, method, (start, end) dòng heading)
    marks: list[tuple[int, str, str | None, str, tuple[int, int]]] = []
    current: str | None = None
    for i, (start, end, raw) in enumerate(lines):
        found = match_heading(raw, lex)
        if found:
            name, inline = found
            strong = _is_caps(raw[:inline] if inline >= 0 else raw) or start in styled
            if inline >= 0 and current in _KEEP_INLINE and not strong:
                continue  # "Dự án: …", "Công nghệ: …": mục con của một việc/dự án
            if name == current and not strong:
                continue  # "Kỹ năng | Mức độ" (tiêu đề bảng) trong mục Kỹ năng: không mở mục mới
            content_at = start + inline if inline >= 0 else end + 1
            head_end = start + inline if inline >= 0 else end
            heading = raw[:inline].strip() if inline >= 0 else raw.strip()
            marks.append((content_at, name, heading.rstrip(":： "), "lexicon", (start, head_end)))
            current = name
            continue
        if current is None or not _looks_like_heading(raw, start in styled, lex):
            continue
        block = []
        for _, _, nxt in lines[i + 1 :]:
            if match_heading(nxt, lex) or (block and _looks_like_heading(nxt, False, lex)):
                break
            block.append(nxt)
        name = _infer(block, lex) if len(block) >= 2 else None
        if name is None or name == current:
            continue  # "BPMN", "SQL" IN HOA trong mục Kỹ năng: nội dung, không phải heading
        marks.append((end + 1, name, raw.strip(), "inferred", (start, end)))
        current = name

    if not marks:
        return CvSections(
            version=lex.version,
            sections=[
                CvSection(name="other", method="fallback", start=0, end=len(text), text=text)
            ],
        )
    sections: list[CvSection] = []
    first_head = marks[0][4][0]
    if text[:first_head].strip():
        sections.append(
            CvSection(name="header", method="preamble", start=0, end=first_head,
                      text=text[:first_head])
        )  # fmt: skip
    for j, (content_at, name, heading, method, _) in enumerate(marks):
        end = marks[j + 1][4][0] if j + 1 < len(marks) else len(text)
        content_at = min(content_at, end)
        sections.append(
            CvSection(name=name, heading=heading, method=method, start=content_at, end=end,
                      text=text[content_at:end])
        )  # fmt: skip
    headings = [(hs, he, name) for _, name, _, _, (hs, he) in marks]
    return CvSections(version=lex.version, sections=sections, headings=headings)
