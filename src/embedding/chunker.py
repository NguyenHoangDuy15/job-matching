"""Cắt tin tuyển dụng thành đoạn ≤ 300 token để embedding (S3-D07). Dùng lại cho CV ở S6-D03.

Mỗi tin:
  summary       "Tiêu đề · Công ty · Cấp bậc · Hình thức · Kỹ năng bắt buộc / ưu tiên" (thẻ D04)
  description   } cắt theo dòng / gạch đầu dòng, gộp đến ≤ max_tokens, chồng lấn 1 dòng giữa hai
  requirements  } đoạn liền nhau; dòng quá dài cắt theo câu, câu quá dài cắt theo từ.
  preferred     }
Không lấy benefits: lương, thưởng, bảo hiểm không giúp so khớp kỹ năng, lại tốn quota.
Mỗi đoạn (trừ summary) có tiền tố "Tiêu đề — Mục:" để vector có ngữ cảnh. Giới hạn tính CẢ tiền tố.

Đếm token: tokenizer của BAAI/bge-m3 (thư viện `tokenizers`, tải tokenizer.json một lần rồi
cache). Không tải được (máy không mạng, CI) thì dùng ước lượng THẬN TRỌNG (đếm dư, không bao giờ để
đoạn vượt giới hạn thật).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

MAX_TOKENS = 300
SECTIONS = ("description", "requirements", "preferred")
SECTION_VI = {"description": "Mô tả", "requirements": "Yêu cầu", "preferred": "Ưu tiên"}
TOKENIZER_ID = "BAAI/bge-m3"
_SENTENCE = re.compile(r"(?<=[.;!?])\s+")

TokenCounter = Callable[[str], int]


@dataclass(frozen=True)
class JobText:
    title: str
    company: str | None = None
    seniority: str | None = None
    work_mode: str | None = None
    skills_required: tuple[str, ...] = ()
    skills_preferred: tuple[str, ...] = ()
    sections: dict[str, str | None] = field(default_factory=dict)  # description/requirements/...
    jd_text: str | None = None  # khi chưa tách section


@dataclass(frozen=True)
class Chunk:
    section: str
    chunk_no: int
    content: str


def approx_tokens(text: str) -> int:
    """Ước lượng dư cho tiếng Việt/Anh với tokenizer XLM-R của bge-m3 (khoảng 3,5 ký tự/token)."""
    return len(text) // 2 + 2


@lru_cache(maxsize=1)
def bge_m3_counter() -> TokenCounter:
    """Bộ đếm token đúng của bge-m3 (gồm 2 token đặc biệt); lỗi tải thì dùng ước lượng dư."""
    try:
        from tokenizers import Tokenizer

        tok = Tokenizer.from_pretrained(TOKENIZER_ID)
    except Exception:
        return approx_tokens

    def count(text: str) -> int:
        return len(tok.encode(text, add_special_tokens=False).ids) + 2

    return count


def _split_long(unit: str, budget: int, count: TokenCounter) -> list[str]:
    """Dòng vượt ngân sách → câu → nhóm từ."""
    if count(unit) <= budget:
        return [unit]
    out: list[str] = []
    for sentence in _SENTENCE.split(unit):
        if count(sentence) <= budget:
            out.append(sentence)
            continue
        words, cur = sentence.split(), []
        for w in words:
            if cur and count(" ".join([*cur, w])) > budget:
                out.append(" ".join(cur))
                cur = []
            cur.append(w)
        if cur:
            out.append(" ".join(cur))
    return out


def _pack(units: list[str], prefix: str, max_tokens: int, count: TokenCounter) -> list[str]:
    """Gộp các dòng thành đoạn ≤ max_tokens (tính cả tiền tố), chồng lấn 1 dòng."""
    budget = max_tokens - count(prefix) + 2  # +2: token đặc biệt đã tính ở cả hai lần đếm
    pieces = [p for u in units for p in _split_long(u, budget, count)]
    chunks: list[list[str]] = []
    cur: list[str] = []
    for piece in pieces:
        if cur and count(prefix + "\n".join([*cur, piece])) > max_tokens:
            chunks.append(cur)
            last = cur[-1]
            # chồng lấn: mang dòng cuối sang đoạn mới nếu vẫn còn chỗ cho dòng tiếp theo
            cur = [last] if count(prefix + "\n".join([last, piece])) <= max_tokens else []
        cur.append(piece)
    if cur:
        chunks.append(cur)
    return [prefix + "\n".join(c) for c in chunks]


def _units(text: str) -> list[str]:
    return [" ".join(line.split()) for line in (text or "").splitlines() if line.strip()]


def summary_text(job: JobText) -> str:
    parts = [job.title]
    if job.company:
        parts.append(job.company)
    if job.seniority and job.seniority != "unknown":
        parts.append(f"Cấp bậc: {job.seniority}")
    if job.work_mode and job.work_mode != "unknown":
        parts.append(f"Hình thức: {job.work_mode}")
    if job.skills_required:
        parts.append("Kỹ năng bắt buộc: " + ", ".join(job.skills_required))
    if job.skills_preferred:
        parts.append("Kỹ năng ưu tiên: " + ", ".join(job.skills_preferred))
    return " · ".join(parts)


def job_chunks(
    job: JobText, count: TokenCounter | None = None, max_tokens: int = MAX_TOKENS
) -> list[Chunk]:
    count = count or bge_m3_counter()
    out: list[Chunk] = []
    summary = summary_text(job)
    out += [Chunk("summary", i, c) for i, c in enumerate(_pack([summary], "", max_tokens, count))]
    sections = {s: job.sections.get(s) for s in SECTIONS}
    if not any(sections.values()) and job.jd_text:
        sections = {"description": job.jd_text}  # chưa tách section: cả JD là mô tả
    for section, text in sections.items():
        units = _units(text or "")
        if not units:
            continue
        prefix = f"{job.title} — {SECTION_VI.get(section, section)}: "
        for i, content in enumerate(_pack(units, prefix, max_tokens, count)):
            out.append(Chunk(section, i, content))
    return out


# ---- CV (S4-D02) -------------------------------------------------------------------
# Chỉ các mục nghề nghiệp. Bỏ header (tên, liên hệ), học vấn, ngoại ngữ, hoạt động, khác: chúng
# giống nhau ở mọi tin nên chỉ kéo điểm Ngữ nghĩa (E) của mọi tin lại gần nhau.
CV_SECTIONS = ("summary", "experience", "projects", "skills", "certifications")
CV_SECTION_VI = {
    "summary": "Giới thiệu",
    "experience": "Kinh nghiệm",
    "projects": "Dự án",
    "skills": "Kỹ năng",
    "certifications": "Chứng chỉ",
}


def cv_summary_text(target_title: str | None, skill_names: list[str] | tuple[str, ...]) -> str:
    """Đoạn tóm tắt CV, đối xứng với đoạn summary của tin: chức danh mong muốn + kỹ năng."""
    parts = []
    if target_title:
        parts.append(f"Chức danh mong muốn: {target_title}")
    if skill_names:
        parts.append("Kỹ năng: " + ", ".join(skill_names))
    return " · ".join(parts)


def cv_chunks(
    sections: dict[str, list[str] | str],
    target_title: str | None = None,
    skill_names: list[str] | tuple[str, ...] = (),
    count: TokenCounter | None = None,
    max_tokens: int = MAX_TOKENS,
) -> list[Chunk]:
    """CV đã che PII (sections như `CvSections.to_jsonb()` / `parse_cv()["sections"]`) → đoạn
    ≤ max_tokens, tiền tố "CV — Mục:", chồng lấn 1 dòng như tin."""
    count = count or bge_m3_counter()
    out: list[Chunk] = []
    summary = cv_summary_text(target_title, skill_names)
    if summary:
        out += [
            Chunk("summary", i, c) for i, c in enumerate(_pack([summary], "", max_tokens, count))
        ]
    for section in CV_SECTIONS:
        raw = sections.get(section) or []
        text = "\n".join(raw) if isinstance(raw, list) else raw
        units = _units(text)
        if not units:
            continue
        name = "summary_text" if section == "summary" else section
        prefix = f"CV — {CV_SECTION_VI[section]}: "
        for i, content in enumerate(_pack(units, prefix, max_tokens, count)):
            out.append(Chunk(name, i, content))
    return out
