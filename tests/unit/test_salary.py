"""S2-D02: chuẩn hóa lương. Tỷ giá cố định trong test để kết quả không đổi theo thị trường."""

from datetime import date

import pytest

from ingestion.fx import FxRate
from ingestion.salary import (
    ParsedSalary,
    StoredSalary,
    parse_salary,
    refresh_salaries,
    salary_columns,
    to_vnd,
)

M = 1_000_000
OLD_DAY, NEW_DAY = date(2026, 11, 1), date(2026, 11, 9)


def rates(usd: float = 25_000, day: date = NEW_DAY) -> dict[str, FxRate]:
    return {
        "USD": FxRate("USD", usd, day, "test"),
        "EUR": FxRate("EUR", 28_000, day, "test"),
        "JPY": FxRate("JPY", 160, day, "test"),
        "SGD": FxRate("SGD", 19_000, day, "test"),
    }


def amounts(result: ParsedSalary) -> tuple:
    return result.amount_min, result.amount_max, result.currency, result.status


# --- Khoảng VND (7) và chỉ min / chỉ max / một số (7) ---
@pytest.mark.parametrize(
    ("raw", "low", "high"),
    [
        ("6 - 8 triệu", 6 * M, 8 * M),
        ("10.0 - 15.0 triệu", 10 * M, 15 * M),  # dạng VietJobs
        ("15tr - 20tr", 15 * M, 20 * M),
        ("15M-20M", 15 * M, 20 * M),
        ("15.000.000 - 20.000.000 VND", 15 * M, 20 * M),
        ("Từ 10 đến 15 triệu", 10 * M, 15 * M),
        ("Lương 10 - 15", 10 * M, 15 * M),  # không ghi đơn vị → triệu
        ("Từ 6 triệu", 6 * M, None),
        ("Trên 20 triệu", 20 * M, None),
        ("Tới 40 triệu", None, 40 * M),  # dạng TopCV
        ("Lên đến 30tr", None, 30 * M),
        ("Up to 25M", None, 25 * M),
        ("35.0 triệu", 35 * M, 35 * M),
        ("20.000.000đ", 20 * M, 20 * M),
    ],
)
def test_parse_vnd(raw, low, high):
    assert amounts(parse_salary(raw)) == (low, high, "VND", "parsed")


# --- Ngoại tệ (7): giữ số gốc + mã tiền, đổi VND theo tỷ giá truyền vào ---
@pytest.mark.parametrize(
    ("raw", "low", "high", "currency", "low_vnd", "high_vnd"),
    [
        ("$1,500", 1500, 1500, "USD", 37_500_000, 37_500_000),
        ("1000–2000 USD", 1000, 2000, "USD", 25_000_000, 50_000_000),
        ("Tới 2,500 USD", None, 2500, "USD", None, 62_500_000),
        ("1.5k - 2k USD", 1500, 2000, "USD", 37_500_000, 50_000_000),
        ("€2,000", 2000, 2000, "EUR", 56_000_000, 56_000_000),
        ("¥300,000", 300_000, 300_000, "JPY", 48_000_000, 48_000_000),
        ("SGD 5,000", 5000, 5000, "SGD", 95_000_000, 95_000_000),
    ],
)
def test_parse_foreign_currency(raw, low, high, currency, low_vnd, high_vnd):
    parsed = parse_salary(raw)
    assert amounts(parsed) == (low, high, currency, "parsed")
    vnd = to_vnd(parsed, rates())
    assert (vnd.min_vnd, vnd.max_vnd, vnd.fx_date, vnd.note) == (low_vnd, high_vnd, NEW_DAY, "ok")
    columns = salary_columns(parsed, vnd)
    assert (columns["salary_currency"], columns["salary_raw"]) == (currency, raw)
    assert columns["salary_is_negotiable"] is False


# --- Thỏa thuận / trống (5): để trống, không đoán ---
@pytest.mark.parametrize(
    ("raw", "status"),
    [
        ("Thoả thuận", "negotiable"),
        ("Negotiable", "negotiable"),
        ("Cạnh tranh", "negotiable"),
        ("0.0 triệu", "negotiable"),  # VietJobs ghi 0.0 khi không công bố
        ("", "missing"),
    ],
)
def test_negotiable_or_missing_stays_empty(raw, status):
    parsed = parse_salary(raw)
    assert (parsed.status, parsed.amount_min, parsed.amount_max) == (status, None, None)
    columns = salary_columns(parsed, to_vnd(parsed, rates()))
    assert columns["salary_is_negotiable"] is (status == "negotiable")
    assert columns["salary_raw"] == (raw or None)
    assert columns["salary_min_vnd"] is None and columns["salary_max_vnd"] is None


# --- Gross / Net (3) ---
@pytest.mark.parametrize(
    ("raw", "pay_type", "currency"),
    [
        ("20 - 25 triệu (Gross)", "gross", "VND"),
        ("Net 30 triệu", "net", "VND"),
        ("$2,000 net", "net", "USD"),
    ],
)
def test_pay_type(raw, pay_type, currency):
    parsed = parse_salary(raw)
    assert (parsed.pay_type, parsed.currency, parsed.status) == (pay_type, currency, "parsed")


# --- Dấu phân cách và kỳ trả lương (3) ---
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,5 triệu", (1.5 * M, 1.5 * M, "VND", "parsed")),  # dấu phẩy thập phân
        ("240 triệu/năm", (20 * M, 20 * M, "VND", "parsed")),  # chia 12
        ("200.000đ/giờ", (None, None, "VND", "unparsed")),  # không đoán số giờ
    ],
)
def test_separators_and_period(raw, expected):
    assert amounts(parse_salary(raw)) == expected


# --- Tỷ giá đổi → lương ngoại tệ đổi theo (3) ---
def _stored(job_id: int, raw: str, table: dict[str, FxRate]) -> StoredSalary:
    parsed = parse_salary(raw)
    return StoredSalary(job_id, parsed, to_vnd(parsed, table))


def test_rate_change_updates_old_and_new_foreign_jobs_only():
    old_rates = rates(usd=25_000, day=OLD_DAY)
    jobs = [
        _stored(1, "$1,500", old_rates),  # tin cũ, đổi bằng tỷ giá 01/11
        _stored(2, "15 - 20 triệu", old_rates),  # tin VND
        _stored(3, "€2,000", old_rates),  # EUR không đổi giá
    ]
    new_rates = rates(usd=26_000, day=NEW_DAY)
    updated = refresh_salaries(jobs, new_rates, changed={"USD"})
    new_job = _stored(4, "$1,500", new_rates)  # tin mới nạp sau khi cập nhật tỷ giá

    assert [job.job_id for job in updated] == [1]
    assert updated[0].vnd == new_job.vnd  # tin cũ và tin mới cùng một số VND
    assert updated[0].vnd.min_vnd == 39_000_000 and updated[0].vnd.fx_date == NEW_DAY


def test_unchanged_rates_update_nothing():
    jobs = [_stored(1, "$1,500", rates()), _stored(2, "10 - 12 triệu", rates())]
    assert refresh_salaries(jobs, rates(), changed=set()) == []


def test_currency_without_rate_is_left_empty():
    vnd = to_vnd(parse_salary("AUD 4,000"), rates())
    assert (vnd.min_vnd, vnd.max_vnd, vnd.note) == (None, None, "no_rate")


# --- Biên (1): ngoài 1–500 triệu/tháng thì không đưa vào bộ lọc ---
def test_out_of_range_is_dropped():
    vnd = to_vnd(parse_salary("$100,000"), rates())
    assert (vnd.min_vnd, vnd.max_vnd, vnd.note) == (None, None, "out_of_range")
