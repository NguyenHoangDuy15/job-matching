"""Tỷ giá ngoại tệ → VND cho chuẩn hóa lương (S2-D02, US-09).

Phương án: lưu sẵn lương VND trong core.jobs, tính lại khi tỷ giá đổi.
Job tỷ giá chạy mỗi ngày trước lượt crawl 02:00:
  1. fetch_rates(): Vietcombank (giá chuyển khoản) → open.er-api.com.
  2. Lỗi cả hai → dùng tỷ giá đã lưu nếu chưa quá max_age_days, không thì cảnh báo.
  3. changed_currencies() khác rỗng → gọi ref.refresh_job_salaries_vnd() (db/sql/fx_rates.sql)
     để mọi tin ngoại tệ đổi theo cùng một tỷ giá trong một transaction.
"""

import json
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "salary.yaml"

VIETCOMBANK_URL = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx"
OPEN_ER_API_URL = "https://open.er-api.com/v6/latest/USD"


class FxError(RuntimeError):
    """Không lấy hoặc không đọc được tỷ giá."""


@dataclass(frozen=True)
class FxRate:
    currency: str  # mã ISO 4217
    rate_vnd: float  # 1 đơn vị ngoại tệ = rate_vnd VND
    rate_date: date
    source: str


FxTable = dict[str, FxRate]
Fetch = Callable[[str, float], str]


@dataclass(frozen=True)
class FxConfig:
    sources: tuple[str, ...] = ("vietcombank", "open_er_api")
    vietcombank_rate: str = "Transfer"  # Buy / Transfer / Sell
    timeout_seconds: float = 10.0
    max_age_days: int = 7
    store_path: Path = ROOT / "data" / "storage" / "fx_rates.json"


def load_fx_config(path: str | Path = DEFAULT_CONFIG) -> FxConfig:
    data = (yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}).get("fx", {})
    defaults = FxConfig()
    return FxConfig(
        sources=tuple(data.get("sources", defaults.sources)),
        vietcombank_rate=data.get("vietcombank_rate", defaults.vietcombank_rate),
        timeout_seconds=float(data.get("timeout_seconds", defaults.timeout_seconds)),
        max_age_days=int(data.get("max_age_days", defaults.max_age_days)),
        store_path=ROOT / data["store_path"] if "store_path" in data else defaults.store_path,
    )


def http_get(url: str, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "job-matching-fx/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (URL cố định)
        return response.read().decode("utf-8")


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def parse_vietcombank(xml_text: str, column: str = "Transfer") -> FxTable:
    """Đọc XML tỷ giá Vietcombank; bỏ qua ngoại tệ không có giá ở cột đã chọn ("-")."""
    try:
        root = ET.fromstring(xml_text.strip())
        stamp = datetime.strptime(root.findtext("DateTime", "").strip(), "%m/%d/%Y %I:%M:%S %p")
    except (ET.ParseError, ValueError) as exc:
        raise FxError(f"XML Vietcombank không hợp lệ: {exc}") from exc
    table: FxTable = {}
    for node in root.iter("Exrate"):
        code, value = node.get("CurrencyCode", "").strip(), node.get(column, "-").strip()
        if code and value not in ("", "-"):
            table[code] = FxRate(code, _number(value), stamp.date(), "vietcombank")
    if "USD" not in table:
        raise FxError("XML Vietcombank không có USD")
    return table


def parse_open_er_api(json_text: str) -> FxTable:
    """open.er-api.com trả tỷ giá theo 1 USD; đổi thành VND cho 1 đơn vị mỗi ngoại tệ."""
    try:
        data = json.loads(json_text)
        rates, vnd_per_usd = data["rates"], float(data["rates"]["VND"])
        day = datetime.fromtimestamp(int(data["time_last_update_unix"]), UTC).date()
    except (ValueError, KeyError, TypeError) as exc:
        raise FxError(f"JSON open.er-api không hợp lệ: {exc}") from exc
    if data.get("result") != "success":
        raise FxError(f"open.er-api trả lỗi: {data.get('error-type')}")
    return {
        code: FxRate(code, vnd_per_usd / float(per_usd), day, "open_er_api")
        for code, per_usd in rates.items()
        if code != "VND" and float(per_usd) > 0
    }


def fetch_rates(config: FxConfig | None = None, fetch: Fetch = http_get) -> FxTable:
    """Thử lần lượt các nguồn; trả bảng của nguồn đầu tiên thành công."""
    config = config or FxConfig()
    parsers = {
        "vietcombank": (
            VIETCOMBANK_URL,
            lambda text: parse_vietcombank(text, config.vietcombank_rate),
        ),
        "open_er_api": (OPEN_ER_API_URL, parse_open_er_api),
    }
    errors: list[str] = []
    for name in config.sources:
        url, parse = parsers[name]
        try:
            return parse(fetch(url, config.timeout_seconds))
        except Exception as exc:  # mạng, HTTP, định dạng: đều chuyển sang nguồn sau
            errors.append(f"{name}: {exc}")
    raise FxError("không nguồn tỷ giá nào dùng được — " + "; ".join(errors))


# --- Lưu lịch sử khi chưa có DB (cùng nội dung với bảng ref.fx_rates) ---


def save_rates(table: Mapping[str, FxRate], path: Path) -> None:
    history = _read_history(path)
    keys = {(r["currency"], r["rate_date"], r["source"]) for r in history}
    for rate in table.values():
        row = asdict(rate) | {"rate_date": rate.rate_date.isoformat()}
        if (row["currency"], row["rate_date"], row["source"]) not in keys:
            history.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")


def _read_history(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def load_latest(path: Path) -> FxTable:
    """Tỷ giá mới nhất của mỗi ngoại tệ, giống view ref.fx_latest."""
    table: FxTable = {}
    for row in _read_history(path):
        rate = FxRate(
            row["currency"],
            float(row["rate_vnd"]),
            date.fromisoformat(row["rate_date"]),
            row["source"],
        )
        if rate.currency not in table or rate.rate_date >= table[rate.currency].rate_date:
            table[rate.currency] = rate
    return table


@dataclass(frozen=True)
class FxUpdate:
    rates: FxTable  # tỷ giá dùng từ giờ; rỗng nếu không có tỷ giá nào đủ mới
    changed: frozenset[str]  # ngoại tệ có tỷ giá khác lần trước → cần tính lại lương
    warnings: tuple[str, ...]


def changed_currencies(old: Mapping[str, FxRate], new: Mapping[str, FxRate]) -> frozenset[str]:
    return frozenset(
        code for code, rate in new.items() if code not in old or old[code].rate_vnd != rate.rate_vnd
    )


def update_rates(today: date, config: FxConfig | None = None, fetch: Fetch = http_get) -> FxUpdate:
    """Bước ① của Cloud Run Job: lấy tỷ giá mới, lưu lịch sử, báo ngoại tệ nào đổi."""
    config = config or load_fx_config()
    previous = load_latest(config.store_path)
    try:
        fresh = fetch_rates(config, fetch)
    except FxError as exc:
        usable = {
            code: rate
            for code, rate in previous.items()
            if (today - rate.rate_date).days <= config.max_age_days
        }
        if usable:
            return FxUpdate(usable, frozenset(), (f"dùng tỷ giá đã lưu vì {exc}",))
        return FxUpdate(
            {},
            frozenset(),
            (f"tỷ giá đã lưu quá {config.max_age_days} ngày, không đổi lương ngoại tệ: {exc}",),
        )
    save_rates(fresh, config.store_path)
    return FxUpdate(fresh, changed_currencies(previous, fresh), ())
