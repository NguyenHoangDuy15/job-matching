"""Đọc khoảng thời gian trong CV và cộng số tháng kinh nghiệm (S3-D04).

    find_ranges("Công ty X | 03/2021 – nay", as_of=date(2026, 11, 18))
    → [DateRange(start=2021*12+2, end=2026*12+11, ...)]   # tháng tính theo chỉ số year*12 + month-1
    total_months([r1, r2])  → gộp khoảng chồng nhau, không tính khoảng trống

Quy ước (config/cv_profile.yaml):
  - Có tháng: tính trọn tháng đầu và tháng cuối ("07/2021 – 02/2023" = 20 tháng).
  - "nay/present" = tháng của `as_of` (tham số để test không phụ thuộc ngày chạy).
  - Chỉ có năm ("2019 – 2021"): (năm cuối − năm đầu) × 12; cùng năm = 6 tháng.
  - Khoảng ngược hoặc bắt đầu sau `as_of`: bỏ (invalid); kết thúc sau `as_of`: cắt về `as_of`.
"""

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "cv_profile.yaml"
_SEP = r"\s*(?:-+|–|—|~|→|->|to|den|toi|until|till)\s*"


@dataclass(frozen=True)
class DateToken:
    start: int  # vị trí trong chuỗi
    end: int
    month_index: int | None  # year*12 + month-1; None nếu là "nay"
    year_only: bool = False
    present: bool = False


@dataclass(frozen=True)
class DateRange:
    start: int  # chỉ số tháng, tính cả tháng này
    end_excl: int  # chỉ số tháng ngay SAU tháng cuối
    text_start: int  # vị trí trong chuỗi gốc (để biết dòng nào là dòng có thời gian)
    text_end: int
    present: bool

    @property
    def months(self) -> int:
        return self.end_excl - self.start

    def label(self) -> tuple[str, str]:
        y, m = divmod(self.start, 12)
        ey, em = divmod(self.end_excl - 1, 12)
        return f"{y:04d}-{m + 1:02d}", ("present" if self.present else f"{ey:04d}-{em + 1:02d}")


class _Rules:
    def __init__(self, data: dict) -> None:
        self.present = re.compile(
            r"(?<![\w])(?:"
            + "|".join(re.escape(w) for w in sorted(data["present_words"], key=len, reverse=True))
            + r")(?![\w])"
        )
        self.months: dict[str, int] = data["month_names"]
        names = "|".join(sorted(self.months, key=len, reverse=True))
        year = r"((?:19|20)\d{2})"
        self.patterns = [
            # "thang 3/2021", "t3/2021", "03/2023", "06.2019", "3-2021"
            ("my", re.compile(rf"(?<![\d/.])(?:thang\s*|t)?(\d{{1,2}})\s*[/.\-]\s*{year}(?!\d)")),
            # "2021-03", "2021/3"
            ("ym", re.compile(rf"(?<!\d){year}\s*[/.\-]\s*(\d{{1,2}})(?![\d/.])")),
            # "mar 2021", "march, 2021", "thang 3 nam 2021"
            ("ny", re.compile(rf"(?<![\w])({names})\.?,?\s*{year}(?!\d)")),
            ("tn", re.compile(rf"(?<![\w])thang\s*(\d{{1,2}})\s*(?:nam\s*)?{year}(?!\d)")),
            ("y", re.compile(rf"(?<![\d/.\-]){year}(?![\d/.]|\s*[/.]\s*\d)")),
        ]
        self.same_year_months = int(data.get("year_only_same_year_months", 6))


@lru_cache(maxsize=2)
def load_rules(path: str | Path = DEFAULT_CONFIG) -> _Rules:
    return _Rules(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _fold(text: str) -> str:
    from cvparser.redact import fold_keep_length

    return fold_keep_length(text)


def tokens(text: str, rules: _Rules | None = None) -> list[DateToken]:
    """Mốc thời gian trong chuỗi (không chồng nhau, dạng có tháng được ưu tiên)."""
    rules = rules or load_rules()
    key = _fold(text)
    taken: list[tuple[int, int]] = []
    out: list[DateToken] = []

    def free(s: int, e: int) -> bool:
        return all(e <= a or s >= b for a, b in taken)

    for kind, pattern in rules.patterns:
        for m in pattern.finditer(key):
            if not free(m.start(), m.end()):
                continue
            if kind == "my":
                month, year = int(m.group(1)), int(m.group(2))
            elif kind == "ym":
                year, month = int(m.group(1)), int(m.group(2))
            elif kind == "ny":
                month, year = rules.months[m.group(1)], int(m.group(2))
            elif kind == "tn":
                month, year = int(m.group(1)), int(m.group(2))
            else:
                month, year = 1, int(m.group(1))
            if not 1 <= month <= 12:
                continue
            taken.append((m.start(), m.end()))
            out.append(DateToken(m.start(), m.end(), year * 12 + month - 1, year_only=kind == "y"))
    for m in rules.present.finditer(key):
        if free(m.start(), m.end()):
            taken.append((m.start(), m.end()))
            out.append(DateToken(m.start(), m.end(), None, present=True))
    return sorted(out, key=lambda t: t.start)


def find_ranges(text: str, as_of: date, rules: _Rules | None = None) -> list[DateRange]:
    """Các khoảng "mốc – mốc" trong chuỗi, đã chuẩn hóa theo quy ước ở đầu file."""
    rules = rules or load_rules()
    key = _fold(text)
    toks = tokens(text, rules)
    now = as_of.year * 12 + as_of.month - 1
    out: list[DateRange] = []
    i = 0
    while i + 1 < len(toks):
        a, b = toks[i], toks[i + 1]
        if a.present or not re.fullmatch(_SEP, key[a.end : b.start]):
            i += 1
            continue
        start = a.month_index
        if b.present:
            end_excl = now + 1
        elif a.year_only and b.year_only:
            span = (b.month_index - a.month_index) or rules.same_year_months
            end_excl = start + span
        elif b.year_only:  # "03/2019 – 2021": không rõ tháng cuối → tính tới đầu năm cuối
            end_excl = max(b.month_index, start + 1)
        else:
            end_excl = b.month_index + 1
        i += 2
        if start > now or end_excl <= start:
            continue  # khoảng trong tương lai hoặc ngược
        out.append(
            DateRange(start, min(end_excl, now + 1), a.start, b.end, present=bool(b.present))
        )
    return out


def has_date(text: str) -> bool:
    return bool(tokens(text))


def total_months(ranges: list[DateRange]) -> int:
    """Tổng số tháng sau khi gộp các khoảng chồng nhau (làm hai việc cùng lúc không cộng đôi)."""
    spans = sorted((r.start, r.end_excl) for r in ranges)
    total, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total
