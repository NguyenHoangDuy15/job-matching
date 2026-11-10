"""Tách JD thành 4 section: Mô tả / Yêu cầu / Ưu tiên / Quyền lợi (S2-D03, US-10).

Ba tầng, ghi lại tầng đã dùng trong `method`:
  structured  JSON-LD JobPosting có trường riêng (responsibilities, qualifications, jobBenefits...).
  heading     Tách theo heading Việt–Anh trong text (config/jd_headings.yaml).
  fallback    Không thấy heading nào: cả văn bản vào description.

Kết quả ghi vào core.jobs.description / requirements / preferred / benefits.
"""

import html
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

Section = Literal["description", "requirements", "preferred", "benefits", "other"]
SECTIONS: tuple[Section, ...] = ("description", "requirements", "preferred", "benefits", "other")
Method = Literal["structured", "heading", "fallback"]

DEFAULT_HEADINGS = Path(__file__).resolve().parents[2] / "config" / "jd_headings.yaml"

# Ký tự đầu dòng, số thứ tự ("1.", "2)", "I.", "a)"), emoji, dấu nhấn markdown.
_BULLET = re.compile(r"^(?:[\W_]+|\d{1,2}[.)/]|[ivx]{1,4}[.)]|[a-e][.)])\s*", re.IGNORECASE)
_BLOCK_TAGS = re.compile(r"<\s*(?:br|/p|/div|/li|li|/h[1-6]|h[1-6][^>]*|/tr|/ul|/ol)\b[^>]*>", re.I)


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu (đ → d), gộp khoảng trắng."""
    decomposed = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def html_to_text(raw_html: str) -> str:
    """HTML mô tả JD (JSON-LD description) → các dòng text, giữ ranh giới khối."""
    text = _BLOCK_TAGS.sub("\n", raw_html)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


@dataclass(frozen=True)
class HeadingLexicon:
    phrases: tuple[tuple[str, Section], ...]  # dài trước ngắn sau
    max_heading_words: int
    max_extra_words: int
    preferred_starts: tuple[str, ...]
    preferred_contains: tuple[str, ...]
    preferred_parenthetical: tuple[str, ...] = ()
    unknown_max_words: int = 7
    unknown_min_hits: int = 2
    cues: tuple[tuple[Section, tuple[str, ...]], ...] = ()


def load_headings(path: str | Path = DEFAULT_HEADINGS) -> HeadingLexicon:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    phrases: dict[str, Section] = {}
    for section, items in data["sections"].items():
        if section not in SECTIONS:
            raise ValueError(f"section lạ trong {path}: {section}")
        for item in items:
            key = fold(item)
            if phrases.setdefault(key, section) != section:
                raise ValueError(f"heading '{item}' thuộc cả {phrases[key]} và {section}")
    markers = data.get("preferred_markers", {})
    unknown = data.get("unknown_heading", {})
    longest = max(len(p.split()) for p in phrases) + int(data.get("max_extra_words", 4))
    if int(data.get("max_heading_words", 14)) < longest:
        raise ValueError(
            f"max_heading_words phải ≥ {longest} (cụm heading dài nhất + max_extra_words)"
        )
    return HeadingLexicon(
        phrases=tuple(sorted(phrases.items(), key=lambda kv: -len(kv[0]))),
        max_heading_words=int(data.get("max_heading_words", 14)),
        max_extra_words=int(data.get("max_extra_words", 4)),
        preferred_starts=tuple(fold(m) for m in markers.get("starts", [])),
        preferred_contains=tuple(fold(m) for m in markers.get("contains", [])),
        preferred_parenthetical=tuple(fold(m) for m in markers.get("parenthetical", [])),
        unknown_max_words=int(unknown.get("max_words", 7)),
        unknown_min_hits=int(unknown.get("min_hits", 2)),
        cues=tuple(
            (sec, tuple(fold(c) for c in words)) for sec, words in unknown.get("cues", {}).items()
        ),
    )


@dataclass(frozen=True)
class JDSections:
    description: str = ""
    requirements: str = ""
    preferred: str = ""
    benefits: str = ""
    other: str = ""
    method: Method = "fallback"
    headings: tuple[str, ...] = field(default=())  # heading đã nhận ra, để báo cáo

    def columns(self) -> dict[str, str | None]:
        """Giá trị 4 cột core.jobs; section rỗng ghi NULL."""
        return {
            name: (getattr(self, name) or None)
            for name in ("description", "requirements", "preferred", "benefits")
        }


def _strip_bullet(line: str) -> str:
    previous = None
    while previous != line:
        previous, line = line, _BULLET.sub("", line, count=1)
    return line.strip().strip("*_").strip()


def _match_heading(key: str, lex: HeadingLexicon) -> tuple[Section, str] | None:
    """Section nếu `key` (đã fold, bỏ bullet) mở đầu bằng một heading; kèm phần còn lại."""
    for phrase, section in lex.phrases:
        if key == phrase or key.startswith(phrase + " ") or key.startswith(phrase + ":"):
            return section, key[len(phrase) :]
    return None


def classify_line(line: str, lex: HeadingLexicon) -> tuple[Section, str] | None:
    """Nếu dòng là heading: (section, nội dung cùng dòng sau dấu ':'), không thì None."""
    body = _strip_bullet(line)
    if not body:
        return None
    head, sep, rest = body.partition(":")
    key = fold(head).rstrip(" .-–")
    if len(key.split()) > lex.max_heading_words:
        return None
    found = _match_heading(key, lex)
    if found is None:
        return None
    section, extra = found
    extra_words = len(re.sub(r"[/&()\-–,]", " ", extra).split())
    if sep:  # "Yêu cầu:" hoặc "Yêu cầu: 3 năm Python" — heading (kèm nội dung)
        return (section, rest.strip()) if extra_words <= lex.max_extra_words else None
    # Không có ":" thì dễ nhầm với nội dung ("Trách nhiệm cao trong công việc",
    # "Ưu tiên biết Docker"): chỉ cho thêm tối đa 2 từ, không kết thúc bằng dấu chấm,
    # và heading Ưu tiên phải đứng một mình.
    if body.endswith(".") or extra_words > 2 or (section == "preferred" and extra_words):
        return None
    return section, ""


_PAREN = re.compile(r"\(([^()]*)\)")


def _is_preferred(line: str, lex: HeadingLexicon) -> bool:
    key = fold(_strip_bullet(line))
    # "(điểm cộng, không bắt buộc)", "(Plus)": cụm trong ngoặc chỉ gồm dấu hiệu → cả câu ưu tiên.
    for inner in _PAREN.findall(key):
        words = re.sub(r"[,;/]", " ", inner).split()
        rest = " ".join(words)
        for marker in sorted(lex.preferred_parenthetical, key=len, reverse=True):
            rest = re.sub(rf"\b{re.escape(marker)}\b", " ", rest)
        if words and not rest.strip():
            return True
    outside = " ".join(_PAREN.sub(" ", key).split())  # "(ưu tiên Python)" không tính
    return outside.startswith(lex.preferred_starts) or any(
        re.search(rf"(?<!\w){re.escape(m)}(?!\w)", outside) for m in lex.preferred_contains
    )


# Cắt đoạn văn thành câu: sau . ; ! ? và khoảng trắng, trước chữ hoa/số/gạch đầu dòng.
# "Node.js", "ASP.NET", "v.v." không bị cắt vì không có khoảng trắng hoặc chữ hoa theo sau.
_SENTENCE_END = re.compile(r"(?<=[.;!?])\s+(?=[\-–•*+]?\s*[A-ZĐÀ-Ỹ0-9])")


_NUMBERING = re.compile(r"^(?:\d{1,2}|[IVX]{1,4}|[a-e])[.)]$")


def explode(line: str) -> list[str]:
    """Một dòng dài nhiều câu → từng câu (JD hay dồn cả mục Yêu cầu vào một đoạn).

    Số thứ tự đứng riêng ("1.", "II.") được nối vào câu sau, không thành một câu.
    """
    parts: list[str] = []
    for part in (p.strip() for p in _SENTENCE_END.split(line)):
        if not part:
            continue
        if parts and _NUMBERING.match(parts[-1]):
            parts[-1] = f"{parts[-1]} {part}"
        else:
            parts.append(part)
    return parts


def _looks_like_heading(line: str, lex: HeadingLexicon) -> bool:
    """Heading lạ: ngắn, không gạch đầu dòng, không kết thúc bằng dấu chấm/chấm phẩy."""
    stripped = line.strip()
    if not stripped or stripped[0] in "-–•*+·●▪" or stripped.endswith((".", ";", ",")):
        return False
    words = fold(_strip_bullet(stripped)).rstrip(":").split()
    return 0 < len(words) <= lex.unknown_max_words and not any(ch.isdigit() for ch in stripped[:1])


def _infer_section(block: list[str], lex: HeadingLexicon) -> Section | None:
    """Đoán section của khối dưới một heading lạ theo từ gợi ý; None nếu không đủ chắc."""
    text = " " + " ".join(fold(line) for line in block) + " "
    scores = {
        sec: sum(len(re.findall(rf"(?<!\w){re.escape(c)}(?!\w)", text)) for c in cues)
        for sec, cues in lex.cues
    }
    best = max(scores, key=scores.get, default=None)
    if best is None or scores[best] < lex.unknown_min_hits:
        return None
    ranked = sorted(scores.values(), reverse=True)
    return best if len(ranked) < 2 or ranked[0] > ranked[1] else None


def assign_lines(text: str | None, lex: HeadingLexicon | None = None) -> list[tuple[str, str]]:
    """Từng dòng (đã cắt câu) kèm nhãn: một section, hoặc "heading" cho dòng chỉ có heading."""
    lex = lex or default_headings()
    raws = [r.strip() for r in (text or "").splitlines() if r.strip()]
    known = [classify_line(r, lex) for r in raws]
    current: Section = "other"
    out: list[tuple[str, str]] = []
    for i, raw in enumerate(raws):
        found = known[i]
        if found:
            current, inline = found
            out.append((raw[: len(raw) - len(inline)].rstrip() if inline else raw, "heading"))
            out.extend((part, _route(current, part, lex)) for part in explode(inline))
            continue
        if _looks_like_heading(raw, lex) and i + 1 < len(raws):
            block = []
            for j in range(i + 1, len(raws)):
                if known[j] or (_looks_like_heading(raws[j], lex) and block):
                    break
                block.append(raws[j])
            guess = _infer_section(block, lex) if len(block) >= 2 else None
            # Heading con trong Yêu cầu/Ưu tiên ("Kỹ năng mềm:") không kéo sang section khác
            # trừ khi nội dung rõ là Quyền lợi.
            if guess and not (current in ("requirements", "preferred") and guess != "benefits"):
                current = guess
                out.append((raw, "heading"))
                continue
        for line in explode(raw):
            out.append((line, _route(current, line, lex)))
    return out


def split_text(text: str | None, lex: HeadingLexicon | None = None) -> JDSections:
    """Tầng heading + fallback cho văn bản JD thô."""
    lex = lex or default_headings()
    assigned = assign_lines(text, lex)
    headings = tuple(line for line, label in assigned if label == "heading")
    if not headings:
        content = "\n".join(line for line, _ in assigned)
        return JDSections(description=content, method="fallback")
    buckets: dict[str, list[str]] = {s: [] for s in SECTIONS}
    for line, label in assigned:
        if label != "heading":
            buckets[label].append(line)
    return JDSections(
        **{s: "\n".join(buckets[s]) for s in SECTIONS}, method="heading", headings=headings
    )


def _route(current: Section, line: str, lex: HeadingLexicon) -> Section:
    # JD Việt hay viết "Ưu tiên ứng viên biết Docker" ngay trong mục Yêu cầu.
    if current == "requirements" and _is_preferred(line, lex):
        return "preferred"
    return current


_STRUCTURED_FIELDS: dict[str, Section] = {
    "responsibilities": "description",
    "qualifications": "requirements",
    "educationRequirements": "requirements",
    "skills": "requirements",
    "jobBenefits": "benefits",
}


def _as_text(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(_as_text(v) for v in value)
    if isinstance(value, Mapping):
        return _as_text(value.get("description") or value.get("name") or "")
    return html_to_text(str(value)) if value else ""


def split_jobposting(
    posting: Mapping[str, object], lex: HeadingLexicon | None = None
) -> JDSections:
    """JSON-LD JobPosting: dùng trường riêng nếu có, phần description vẫn tách theo heading."""
    lex = lex or default_headings()
    parsed = split_text(_as_text(posting.get("description")), lex)
    extra = {s: _as_text(posting.get(k)) for k, s in _STRUCTURED_FIELDS.items() if posting.get(k)}
    if not extra:
        return parsed
    merged = {s: getattr(parsed, s) for s in SECTIONS}
    for key, section in _STRUCTURED_FIELDS.items():
        text = _as_text(posting.get(key))
        if text and text not in merged[section]:
            merged[section] = "\n".join(filter(None, [merged[section], text]))
    if parsed.method == "fallback" and merged["description"] and "responsibilities" in posting:
        # description chỉ là đoạn giới thiệu khi đã có responsibilities riêng
        merged["other"], merged["description"] = (
            parsed.description,
            _as_text(posting["responsibilities"]),
        )
    return JDSections(**merged, method="structured", headings=parsed.headings)


_DEFAULT: HeadingLexicon | None = None


def default_headings() -> HeadingLexicon:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_headings()
    return _DEFAULT
