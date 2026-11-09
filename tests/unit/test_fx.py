"""S2-D02: nguồn tỷ giá. Không gọi mạng thật: HTTP được thay bằng hàm đọc fixture."""

from datetime import date
from pathlib import Path

import pytest

from ingestion.fx import (
    OPEN_ER_API_URL,
    VIETCOMBANK_URL,
    FxConfig,
    FxRate,
    parse_vietcombank,
    save_rates,
    update_rates,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VCB_XML = (FIXTURES / "fx_vietcombank.xml").read_text(encoding="utf-8")
ER_JSON = (FIXTURES / "fx_open_er_api.json").read_text(encoding="utf-8")
TODAY = date(2026, 11, 9)


def fake_fetch(responses: dict[str, str]):
    def fetch(url: str, timeout: float) -> str:
        if url not in responses:
            raise OSError(f"không kết nối được {url}")
        return responses[url]

    return fetch


@pytest.fixture
def config(tmp_path) -> FxConfig:
    return FxConfig(store_path=tmp_path / "fx_rates.json")


def test_vietcombank_first_with_transfer_rate(config):
    fetch = fake_fetch({VIETCOMBANK_URL: VCB_XML, OPEN_ER_API_URL: ER_JSON})
    assert update_rates(TODAY, config, fetch).rates["USD"].source == "vietcombank"
    table = parse_vietcombank(VCB_XML)
    assert table["USD"] == FxRate("USD", 25_320.0, TODAY, "vietcombank")
    assert table["DKK"].rate_vnd == 3_742.79  # cột Buy là "-" nhưng Transfer có giá


def test_falls_back_to_open_er_api_when_vietcombank_fails(config):
    update = update_rates(TODAY, config, fake_fetch({OPEN_ER_API_URL: ER_JSON}))
    assert update.rates["USD"].source == "open_er_api"
    assert update.rates["USD"].rate_vnd == pytest.approx(25_611.565139)
    assert update.rates["EUR"].rate_vnd == pytest.approx(25_611.565139 / 0.896919)
    assert update.changed >= {"USD", "EUR"} and update.warnings == ()


def test_uses_saved_rates_when_sources_fail(config):
    save_rates({"USD": FxRate("USD", 25_000, date(2026, 11, 5), "vietcombank")}, config.store_path)
    update = update_rates(TODAY, config, fake_fetch({}))
    assert update.rates["USD"].rate_vnd == 25_000
    assert update.changed == frozenset()  # giữ tỷ giá cũ thì không tính lại lương
    assert "dùng tỷ giá đã lưu" in update.warnings[0]


def test_stale_saved_rates_are_not_used(config):
    save_rates({"USD": FxRate("USD", 25_000, date(2026, 10, 20), "vietcombank")}, config.store_path)
    update = update_rates(TODAY, config, fake_fetch({}))
    assert update.rates == {}
    assert "quá 7 ngày" in update.warnings[0]
