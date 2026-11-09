"""Chuẩn hóa mức lương tin tuyển dụng về VND/tháng (S2-D02, US-09).

Hai bước tách riêng:
  parse_salary(raw)     chuỗi gốc → số tiền gốc theo tháng + mã tiền tệ (không cần tỷ giá).
  to_vnd(parsed, rates) số tiền gốc → VND/tháng theo bảng tỷ giá mới nhất.

core.jobs lưu cả hai: số gốc không bao giờ đổi; cột VND được ref.refresh_job_salaries_vnd()
tính lại khi tỷ giá đổi, nên tin cũ và tin mới luôn cùng một tỷ giá.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

from ingestion.fx import FxRate

Status = Literal["parsed", "negotiable", "missing", "unparsed"]
PayType = Literal["gross", "net", "unknown"]
VndNote = Literal["ok", "not_parsed", "no_rate", "out_of_range"]

# Mức VND/tháng hợp lý cho tin IT; ngoài khoảng này coi là đọc sai, không đưa vào bộ lọc.
MIN_MONTHLY_VND = 1_000_000
MAX_MONTHLY_VND = 500_000_000

_NEGOTIABLE = re.compile(
    r"thoa thuan|thuong luong|negotiable|negotiate|canh tranh|competitive|hap dan|attractive"
)
_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₫": "VND"}
_CODES = re.compile(r"\b(usd|eur|gbp|jpy|sgd|aud|krw|cny|vnd|vnđ)\b")
_VND_WORDS = re.compile(r"(?<=\d)\s*(?:d|dong)\b|\bdong\b")
_YEARLY = re.compile(r"/\s*(?:nam|year|yr)\b|\bper (?:year|annum)\b|\b(?:annual|yearly|mot nam)\b")
_UNSUPPORTED_PERIOD = re.compile(
    r"/\s*(?:gio|hour|hr|h|ngay|day|tuan|week)\b|\bper (?:hour|day|week)\b|\b(?:du an|project)\b"
)
_PAY_TYPE = re.compile(r"\b(gross|net)\b")
_MIN_ONLY = re.compile(r"\b(?:tu|tren|from|above|over|min|it nhat|toi thieu)\b|>")
_MAX_ONLY = re.compile(r"\b(?:toi(?! thieu)|den|len den|up ?to|upto|max|duoi|under|toi da)\b|<")
# Số kèm đơn vị: "15", "2,500", "15.000.000", "1,5", "1.5k", "20tr", "15M".
_AMOUNT = re.compile(r"(\d+(?:[.,]\d+)*)\s*(trieu|tr|m|k|nghin|ngan)?(?![a-z])")
_SCALE = {"trieu": 1e6, "tr": 1e6, "m": 1e6, "k": 1e3, "nghin": 1e3, "ngan": 1e3}


@dataclass(frozen=True)
class ParsedSalary:
    raw: str  # chuỗi gốc, lưu nguyên văn vào core.jobs.salary_raw
    status: Status
    amount_min: float | None = None  # theo tháng, đơn vị là currency
    amount_max: float | None = None
    currency: str | None = None  # mã ISO 4217
    pay_type: PayType = "unknown"


@dataclass(frozen=True)
class SalaryVnd:
    min_vnd: int | None
    max_vnd: int | None
    fx_rate: float | None  # None với tin VND
    fx_date: date | None
    note: VndNote


def _fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt (đ → d) nhưng giữ ký hiệu tiền tệ và dấu câu."""
    decomposed = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def parse_number(token: str) -> float:
    """Đọc số có dấu phân cách: 2,500 và 15.000.000 là phân nghìn; 1,5 và 15.0 là thập phân.

    Có cả "." và "," thì dấu đứng sau là dấu thập phân ("1,500.50").
    Chỉ một loại dấu: lặp lại hoặc theo sau đúng 3 chữ số → phân nghìn, còn lại → thập phân.
    """
    if "." in token and "," in token:
        decimal = "." if token.rfind(".") > token.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        return float(token.replace(thousands, "").replace(decimal, "."))
    for sep in ".,":
        if sep in token:
            parts = token.split(sep)
            if len(parts) > 2 or len(parts[1]) == 3:
                return float(token.replace(sep, ""))
            return float(token.replace(sep, "."))
    return float(token)


def _currency(text: str, folded: str) -> str:
    for symbol, code in _SYMBOLS.items():
        if symbol in text:
            return code
    match = _CODES.search(folded)
    if match:
        return "VND" if match.group(1) in ("vnd", "vnđ") else match.group(1).upper()
    return "VND"


def _amounts(folded: str, currency: str) -> list[float]:
    found = [(parse_number(num), unit) for num, unit in _AMOUNT.findall(folded)][:2]
    if not found:
        return []
    # "10 - 15 triệu": đơn vị chỉ ghi ở số cuối thì áp cho cả khoảng.
    last_unit = found[-1][1]
    values = []
    for value, unit in found:
        scale = _SCALE.get(unit or last_unit or "", 1.0)
        if currency == "VND" and not (unit or last_unit) and value < 1000:
            scale = 1e6  # "Lương 10 - 15" trên trang Việt: đơn vị ngầm là triệu
        values.append(value * scale)
    return values


def parse_salary(raw: str | None) -> ParsedSalary:
    text = (raw or "").strip()
    if not text:
        return ParsedSalary(raw=text, status="missing")
    folded = _fold(text)
    pay = _PAY_TYPE.search(folded)
    pay_type: PayType = pay.group(1) if pay else "unknown"  # type: ignore[assignment]

    currency = _currency(text, folded)
    values = _amounts(_VND_WORDS.sub(" ", folded), currency)
    if not values or all(v == 0 for v in values):  # VietJobs ghi "0.0 triệu" khi không công bố
        status: Status = "negotiable" if _NEGOTIABLE.search(folded) or values else "unparsed"
        return ParsedSalary(raw=text, status=status, pay_type=pay_type)
    if _UNSUPPORTED_PERIOD.search(folded):  # lương giờ/ngày/dự án: đổi ra tháng là phải đoán
        return ParsedSalary(raw=text, status="unparsed", currency=currency, pay_type=pay_type)
    if _YEARLY.search(folded):
        values = [v / 12 for v in values]

    if len(values) == 2:
        low, high = sorted(values)
    elif _MAX_ONLY.search(folded):
        low, high = None, values[0]
    elif _MIN_ONLY.search(folded):
        low, high = values[0], None
    else:
        low = high = values[0]
    return ParsedSalary(
        raw=text,
        status="parsed",
        amount_min=low,
        amount_max=high,
        currency=currency,
        pay_type=pay_type,
    )


def to_vnd(parsed: ParsedSalary, rates: Mapping[str, FxRate]) -> SalaryVnd:
    """Đổi sang VND/tháng; giống công thức trong ref.refresh_job_salaries_vnd()."""
    if parsed.status != "parsed" or parsed.currency is None:
        return SalaryVnd(None, None, None, None, "not_parsed")
    if parsed.currency == "VND":
        rate, fx_rate, fx_date = 1.0, None, None
    elif parsed.currency in rates:
        fx = rates[parsed.currency]
        rate, fx_rate, fx_date = fx.rate_vnd, fx.rate_vnd, fx.rate_date
    else:
        return SalaryVnd(None, None, None, None, "no_rate")

    converted = [
        None if a is None else round(a * rate) for a in (parsed.amount_min, parsed.amount_max)
    ]
    if any(v is not None and not MIN_MONTHLY_VND <= v <= MAX_MONTHLY_VND for v in converted):
        return SalaryVnd(None, None, fx_rate, fx_date, "out_of_range")
    return SalaryVnd(converted[0], converted[1], fx_rate, fx_date, "ok")


@dataclass(frozen=True)
class StoredSalary:
    """Phần lương của một dòng core.jobs."""

    job_id: int
    parsed: ParsedSalary
    vnd: SalaryVnd


def refresh_salaries(
    jobs: Iterable[StoredSalary], rates: Mapping[str, FxRate], changed: Iterable[str]
) -> list[StoredSalary]:
    """Bản Python của ref.refresh_job_salaries_vnd(): chỉ tính lại tin có ngoại tệ vừa đổi giá.

    Trả các dòng cần UPDATE; tin VND và tin ngoại tệ không đổi giá không bị đụng tới.
    """
    targets = {code for code in changed if code != "VND"}
    return [
        StoredSalary(job.job_id, job.parsed, to_vnd(job.parsed, rates))
        for job in jobs
        if job.parsed.status == "parsed" and job.parsed.currency in targets
    ]


def parsed_ratio(results: Iterable[ParsedSalary]) -> float:
    """Tỷ lệ tin có lương đọc được hoặc ghi rõ "thỏa thuận" (cho ops.quality_reports, US-19)."""
    items = list(results)
    ok = sum(r.status in ("parsed", "negotiable") for r in items)
    return ok / len(items) if items else 0.0
