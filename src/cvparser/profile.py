"""Hồ sơ CV (S3-D04, US-12): kỹ năng + mức bằng chứng + câu trích, số năm kinh nghiệm,
chức danh mong muốn. Nội dung màn "Xác nhận hồ sơ" (docs/ui/wireframe_cv.html, S3-H02).

    red = redact(extraction.text)                       # S3-D03: chạy trên văn bản ĐÃ che PII
    secs = split_sections(red.text)                     # S3-D02
    profile = build_profile(red.text, secs, extraction.tables, as_of=date.today())
    profile.model_dump_json()                           # hồ sơ JSON
    to_db_rows(profile, skill_ids)                      # S3-D05: app.cvs + app.cv_skills

Mức bằng chứng theo section (config/cv_profile.yaml): Kinh nghiệm/Dự án → strong; Kỹ năng, Tóm tắt,
Chứng chỉ, Ngoại ngữ, Học vấn, Hoạt động → listed; phần đầu CV và mục khác → bỏ qua.
Số năm: chỉ khoảng thời gian trong mục Kinh nghiệm, gộp chồng nhau, không tính thực tập.
Chức danh mong muốn: dòng chức danh ở phần đầu CV, không có thì việc làm gần nhất.
Hàm thuần: không DB, không mạng; `as_of` là ngày tính "nay".
"""

import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from cvparser.dates import DateRange, find_ranges, has_date, total_months
from cvparser.redact import fold_keep_length
from cvparser.sections import CvSections, match_heading

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "cv_profile.yaml"
_BULLET = re.compile(r"^\s*(?:[-–•●▪*+#]|\d{1,2}[.)])\s+")
_PARTS = re.compile(r"\s*(?:\||·|•|\s[–—-]\s)\s*")
_TRANSITION = re.compile(r"(?<![\w])(?:roi|sau do|len|then|->|→)(?![\w])")


class Entry(BaseModel):
    """Một việc làm (Kinh nghiệm) hoặc một dự án."""

    model_config = ConfigDict(frozen=True)

    section: Literal["experience", "projects"]
    org: str | None = None  # công ty (Kinh nghiệm) / tên dự án (Dự án)
    title: str | None = None  # chức danh
    start: str | None = None  # "2021-07"
    end: str | None = None  # "2023-02" | "present"
    months: int | None = None
    is_internship: bool = False
    text_start: int = 0  # vị trí trong văn bản
    text_end: int = 0


class SkillEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_id: str
    name: str
    evidence_level: Literal["strong", "listed"]
    evidence: str  # câu trích ≤ snippet_max_chars, đã che PII
    highlight: tuple[int, int]  # vị trí tên kỹ năng trong evidence (UI in đậm)
    section: str
    context: str | None = None  # "Công ty Cổ phần Công nghệ Sao Mai" / tên dự án
    mentions: int
    years: float | None = None  # thời gian các việc làm có dùng kỹ năng này


class CvProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    as_of: date
    target_title: str | None = None
    target_title_source: Literal["header", "latest_job"] | None = None
    years_exp: float | None = None
    years_ranges: list[tuple[str, str]] = []  # khoảng đã tính, để UI ghi "Tính từ các mốc…"
    internship_months: int = 0  # thời gian thực tập không tính vào years_exp
    entries: list[Entry] = []
    skills: list[SkillEvidence] = []
    warnings: list[str] = []


class _Config:
    def __init__(self, data: dict) -> None:
        self.version: str = data["version"]
        self.levels: dict[str, str] = data["evidence_level"]
        self.fallback_level: str = data.get("fallback_level", "listed")
        self.max_chars: int = int(data.get("snippet_max_chars", 200))
        words = sorted(data["internship_words"], key=len, reverse=True)
        self.internship = re.compile(rf"(?<![\w])(?:{'|'.join(map(re.escape, words))})(?![\w])")


@lru_cache(maxsize=2)
def load_config(path: str | Path = DEFAULT_CONFIG) -> _Config:
    return _Config(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def _taxonomy():
    from skillkit.levels.pipeline import SKILLS_YAML
    from skillkit.matcher import SkillMatcher
    from skillkit.taxonomy import load_taxonomy

    taxonomy = load_taxonomy(SKILLS_YAML)
    return SkillMatcher(taxonomy), {s.id: (s.name or s.id) for s in taxonomy}


def _lines(text: str, start: int = 0, end: int | None = None):
    end = len(text) if end is None else end
    pos = start
    for raw in text[start:end].split("\n"):
        yield pos, raw
        pos += len(raw) + 1


def _is_bullet(line: str) -> bool:
    return bool(_BULLET.match(line))


def _clean(part: str) -> str:
    return part.strip(" |·•–—-:,").strip()


# ----------------------------------------------------------------------------- mục con


def _entries_from_text(
    text: str, secs: CvSections, as_of: date, cfg: _Config
) -> tuple[list[Entry], list[DateRange], list[int]]:
    """Tách việc làm / dự án. Trả (entries, khoảng thời gian dùng tính số năm, tháng thực tập)."""
    entries: list[Entry] = []
    ranges: list[DateRange] = []
    intern_months: list[int] = []
    for sec in secs.sections:
        if sec.name not in ("experience", "projects"):
            continue
        current: dict | None = None
        prev_plain: tuple[int, str] | None = None  # dòng thường ngay trước (có thể là tên công ty)
        last_was_bullet = True  # đầu mục coi như sau gạch đầu dòng
        for pos, raw in _lines(text, sec.start, sec.end):
            line = raw.strip()
            if not line:
                continue
            bullet = _is_bullet(line)
            found = [] if bullet else find_ranges(raw, as_of)
            single_date = not bullet and not found and has_date(raw)
            label_line = bool(re.match(r"^[^:]{1,25}:\s*\S", line))  # "Dự án: …", "Công nghệ: …"
            starts = bool(found) or (
                sec.name == "projects" and not bullet and not label_line
                and (single_date or last_was_bullet)
            )  # fmt: skip
            if starts:
                if current is not None:
                    entries.append(Entry(**current, text_end=pos))
                rng = found[0] if found else None
                rest = raw[: rng.text_start] + raw[rng.text_end :] if rng else raw
                rest = re.sub(r"(?<!\d)(?:19|20)\d{2}(?!\d)", "", rest) if single_date else rest
                parts = [_clean(p) for p in _PARTS.split(rest) if _clean(p)]
                org = parts[0] if parts else None
                title = parts[1] if len(parts) > 1 and sec.name == "experience" else None
                start_at = pos
                if org is None and prev_plain is not None:  # "Công ty X" ⏎ "03/2021 – nay"
                    start_at, org = prev_plain
                current = {
                    "section": sec.name, "org": org, "title": title, "text_start": start_at,
                    "start": rng.label()[0] if rng else None,
                    "end": rng.label()[1] if rng else None,
                    "months": rng.months if rng else None,
                }  # fmt: skip
            elif current is not None and current.get("title") is None and not bullet:
                if len(line.split()) <= 8 and not label_line:
                    current["title"] = _clean(line)
            last_was_bullet = bullet
            prev_plain = None if bullet else (pos, _clean(line))

        if current is not None:
            entries.append(Entry(**current, text_end=sec.end))

    final: list[Entry] = []
    for e in entries:
        raw = text[e.text_start : e.text_end]
        rng = next(iter(find_ranges(raw.split("\n")[0], as_of) or find_ranges(raw, as_of)), None)
        head = fold_keep_length(f"{e.org or ''} {e.title or ''}")
        intern = bool(cfg.internship.search(head)) and not _TRANSITION.search(head)
        final.append(e.model_copy(update={"is_internship": intern}))
        if e.section == "experience" and rng is not None:
            (intern_months if intern else ranges).append(rng)
    return final, ranges, [r.months for r in intern_months]


def _entries_from_tables(tables, as_of: date) -> tuple[list[Entry], list[DateRange]]:
    """Kinh nghiệm dạng bảng (PDF, từ D01): hàng có khoảng thời gian; cột Công ty / Vị trí."""
    entries, ranges = [], []
    for table in tables or []:
        rows = getattr(table, "rows", None) or []
        if len(rows) < 2:
            continue
        header = [fold_keep_length(c or "") for c in rows[0]]
        org_col = _column(header, r"cong ty|company|don vi|noi lam")
        title_col = _column(header, r"vi tri|chuc danh|position|role|title")
        for row in rows[1:]:
            joined = " | ".join(c or "" for c in row)
            found = find_ranges(" ".join(joined.split()), as_of)
            if not found:
                continue
            rng = found[0]
            entries.append(
                Entry(
                    section="experience", org=_cell(row, org_col), title=_cell(row, title_col),
                    start=rng.label()[0], end=rng.label()[1], months=rng.months,
                )
            )  # fmt: skip
            ranges.append(rng)
    return entries, ranges


def _column(header: list[str], pattern: str) -> int | None:
    return next((i for i, h in enumerate(header) if re.search(pattern, h)), None)


def _cell(row: list, i: int | None) -> str | None:
    return " ".join((row[i] or "").split()) if i is not None and i < len(row) else None


# ----------------------------------------------------------------------------- kỹ năng


def _snippet(line: str, s: int, e: int, max_chars: int) -> tuple[str, tuple[int, int]]:
    body = _BULLET.sub("", line, count=1).strip()
    shift = line.find(body) if body else 0
    s, e = s - shift, e - shift
    if len(body) <= max_chars:
        return body, (s, e)
    half = (max_chars - (e - s)) // 2
    a = max(0, s - half)
    b = min(len(body), a + max_chars)
    a = max(0, b - max_chars)
    if a > 0:
        a = body.find(" ", a) + 1 or a
    if b < len(body):
        b = body.rfind(" ", a, b) or b
    prefix = "…" if a > 0 else ""
    suffix = "…" if b < len(body) else ""
    return f"{prefix}{body[a:b]}{suffix}", (s - a + len(prefix), e - a + len(prefix))


def _skills(
    text: str, secs: CvSections, entries: list[Entry], cfg: _Config, now: int
) -> list[SkillEvidence]:
    from skillkit.matcher import prepare

    matcher, names = _taxonomy()
    fallback = all(s.method == "fallback" for s in secs.sections)
    best: dict[str, dict] = {}
    counts: dict[str, int] = {}
    entry_hits: dict[str, list[Entry]] = {}
    for pos, raw in _lines(text):
        if not raw.strip():
            continue
        line = prepare(raw)[0]
        lead = len(raw) - len(raw.lstrip())
        for m in matcher.find(line):
            section = secs.section_at(pos + lead + m.start)
            level = cfg.fallback_level if fallback else cfg.levels.get(section)
            if level is None:
                continue
            counts[m.skill_id] = counts.get(m.skill_id, 0) + 1
            entry = next(
                (en for en in entries if en.text_start <= pos < en.text_end), None
            ) if level == "strong" else None  # fmt: skip
            if entry is not None and entry.section == "experience":
                entry_hits.setdefault(m.skill_id, []).append(entry)
            # Câu trích: ưu tiên strong, Kinh nghiệm, rồi dòng mô tả (gạch đầu dòng) hơn dòng
            # liệt kê "Công nghệ: Java, …" hay dòng tiêu đề việc làm.
            kind = 2 if _is_bullet(raw) else (0 if re.match(r"^\s*[^:]{1,25}:", raw) else 1)
            rank = (level == "strong", section == "experience", kind)
            if m.skill_id in best and best[m.skill_id]["rank"] >= rank:
                continue
            snippet, hl = _snippet(line, m.start, m.end, cfg.max_chars)
            context = (
                (entry.org or entry.title)
                if entry and entry.section == "experience"
                else ((entry.org or entry.title) if entry else None)
            )
            best[m.skill_id] = {
                "rank": rank, "skill_id": m.skill_id, "name": names.get(m.skill_id, m.skill_id),
                "evidence_level": level, "evidence": snippet, "highlight": hl,
                "section": section, "context": context,
            }  # fmt: skip
    out = []
    for sid, b in best.items():
        hit_ranges = {(e.start, e.end): e for e in entry_hits.get(sid, []) if e.months}
        years = None
        if hit_ranges and b["evidence_level"] == "strong":
            months = _merge_labels(list(hit_ranges), now)
            years = round(months / 12, 1) if months else None
        b.pop("rank")
        out.append(SkillEvidence(**b, mentions=counts[sid], years=years))
    return sorted(out, key=lambda s: (s.evidence_level != "strong", -s.mentions, s.name.lower()))


def _merge_labels(labels: list[tuple[str | None, str | None]], now: int) -> int:
    """Tổng tháng (gộp chồng nhau) của các khoảng dạng ("2021-07", "2023-02" | "present")."""
    spans = []
    for start, end in labels:
        if not start or not end:
            continue
        sy, sm = map(int, start.split("-"))
        s = sy * 12 + sm - 1
        if end == "present":
            e = now
        else:
            ey, em = map(int, end.split("-"))
            e = ey * 12 + em - 1
        spans.append((s, e + 1))
    spans.sort()
    total, cs, ce = 0, None, None
    for s, e in spans:
        if ce is None or s > ce:
            total += (ce - cs) if ce is not None else 0
            cs, ce = s, e
        else:
            ce = max(ce, e)
    return total + ((ce - cs) if ce is not None else 0)


# ----------------------------------------------------------------------------- chức danh


def _target_title(text: str, secs: CvSections, entries: list[Entry]):
    from cvparser.redact import _is_place
    from cvparser.redact import load_config as pii_config

    header = next((s for s in secs.sections if s.name == "header"), None)
    if header is not None:
        for _, raw in _lines(text, header.start, header.end):
            line = raw.strip()
            words = line.split()
            if (
                1 <= len(words) <= 7
                and not re.search(r"[\[@:\d]", line)
                and not match_heading(line)
                and not _is_place(line, pii_config())
            ):
                return line, "header"
    jobs = [e for e in entries if e.section == "experience" and e.title and not e.is_internship]
    if jobs:
        latest = max(
            jobs, key=lambda e: ("9999" if e.end == "present" else e.end or "", e.start or "")
        )
        return latest.title, "latest_job"
    return None, None


# ----------------------------------------------------------------------------- API


def build_profile(text: str, sections: CvSections, tables=(), *, as_of: date) -> CvProfile:
    """`text`: văn bản ĐÃ che PII (S3-D03); `sections`: split_sections(text) (S3-D02);
    `tables`: ExtractionResult.tables (S3-D01) để đọc kinh nghiệm dạng bảng."""
    cfg = load_config()
    warnings: list[str] = []
    entries, ranges, intern = _entries_from_text(text, sections, as_of, cfg)
    table_entries, table_ranges = _entries_from_tables(tables, as_of)
    if not ranges:  # không có khoảng thời gian trong văn bản: kinh nghiệm chỉ nằm trong bảng
        ranges += table_ranges
        entries += table_entries
    else:
        # Bảng PDF xuống dòng giữa ô ("Công ty Cổ phần" ⏎ "Phần mềm Ánh"): lấy công ty, chức danh
        # từ hàng bảng có cùng khoảng thời gian.
        by_range = {(e.start, e.end): e for e in table_entries}
        entries = [
            e.model_copy(update={"org": by_range[(e.start, e.end)].org or e.org,
                                 "title": by_range[(e.start, e.end)].title or e.title})
            if e.section == "experience" and (e.start, e.end) in by_range else e
            for e in entries
        ]  # fmt: skip
    if not any(s.name == "experience" for s in sections.sections):
        warnings.append("no_experience_section")
    months = total_months(ranges)
    title, source = _target_title(text, sections, entries)
    return CvProfile(
        version=cfg.version,
        as_of=as_of,
        target_title=title,
        target_title_source=source,
        years_exp=round(months / 12, 1) if ranges else None,
        years_ranges=[r.label() for r in sorted(ranges, key=lambda r: r.start)],
        internship_months=sum(intern),
        entries=entries,
        skills=_skills(text, sections, entries, cfg, as_of.year * 12 + as_of.month - 1),
        warnings=warnings,
    )


def to_db_rows(profile: CvProfile, skill_ids: dict[str, int]) -> tuple[dict, list[dict]]:
    """(cột app.cvs, các dòng app.cv_skills) cho S3-D05. Kỹ năng không có trong ref.skills bị bỏ."""
    cvs = {"years_exp": profile.years_exp, "target_title": profile.target_title}
    rows = [
        {
            "skill_id": skill_ids[s.skill_id],
            "evidence_level": s.evidence_level,
            "evidence": s.evidence,
            "years": s.years,
            "confirmed": False,
        }
        for s in profile.skills
        if s.skill_id in skill_ids
    ]
    return cvs, rows
