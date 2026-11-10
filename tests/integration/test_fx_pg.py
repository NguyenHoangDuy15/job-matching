"""S2-D02: tỷ giá trong DB và tính lại lương tin ngoại tệ (migration 0002).

Bỏ qua nếu không đặt TEST_DATABASE_URL. Mỗi test chạy trong một transaction rồi rollback,
nên không để lại dữ liệu trong DB thử (KHÔNG dùng Supabase production).
"""

import os
import re
from datetime import date
from pathlib import Path

import pytest

from ingestion.fx import VIETCOMBANK_URL, FxConfig, load_latest_pg, sync_rates_pg

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="cần TEST_DATABASE_URL trỏ tới DB thử")
XML = (Path(__file__).resolve().parents[1] / "fixtures" / "fx_vietcombank.xml").read_text("utf-8")
TODAY = date(2026, 11, 9)


def vcb(usd: str, day: str = "11/9/2026 3:00:00 PM"):
    text = re.sub(r'(CurrencyCode="USD"[^/]*Transfer=")[^"]+', rf"\g<1>{usd}", XML)
    text = re.sub(r"<DateTime>[^<]+", f"<DateTime>{day}", text)
    return lambda url, timeout: text if url == VIETCOMBANK_URL else (_ for _ in ()).throw(OSError())


@pytest.fixture
def conn(tmp_path):
    import psycopg

    with psycopg.connect(DSN) as c, c.transaction(force_rollback=True):
        c.execute("delete from ref.fx_rates")
        yield c


def _job(conn, raw: str, currency: str, low, high) -> int:
    return conn.execute(
        """insert into core.jobs (title, title_norm, apply_url, salary_raw, salary_currency,
                                  salary_amount_min, salary_amount_max, salary_status)
           values ('Test', 'test', 'https://example.com/fx', %s, %s, %s, %s, 'parsed')
           returning id""",
        (raw, currency, low, high),
    ).fetchone()[0]


def _vnd(conn, job_id: int):
    return conn.execute(
        "select salary_min_vnd, salary_max_vnd, salary_fx_date from core.jobs where id = %s",
        (job_id,),
    ).fetchone()


def test_sync_writes_rates_and_refreshes_foreign_jobs_only(conn):
    usd_job = _job(conn, "$1,500 - $2,000", "USD", 1500, 2000)
    vnd_job = _job(conn, "15 - 20 triệu", "VND", 15_000_000, 20_000_000)
    config = FxConfig(sources=("vietcombank",))

    first = sync_rates_pg(conn, TODAY, config, vcb("25,000.00"))
    assert first.update.changed >= {"USD"} and first.jobs_refreshed >= 1
    assert load_latest_pg(conn)["USD"].rate_vnd == 25_000
    assert _vnd(conn, usd_job) == (37_500_000, 50_000_000, TODAY)
    assert _vnd(conn, vnd_job) == (None, None, None)  # tin VND không bị đụng tới

    again = sync_rates_pg(conn, TODAY, config, vcb("25,000.00"))
    assert again.update.changed == frozenset() and again.jobs_refreshed == 0

    later = sync_rates_pg(
        conn, date(2026, 11, 10), config, vcb("26,000.00", "11/10/2026 9:00:00 AM")
    )
    assert later.update.changed >= {"USD"}
    assert _vnd(conn, usd_job) == (39_000_000, 52_000_000, date(2026, 11, 10))


def test_sources_down_keeps_last_rates(conn):
    config = FxConfig(sources=("vietcombank",))
    sync_rates_pg(conn, TODAY, config, vcb("25,000.00"))
    down = sync_rates_pg(conn, TODAY, config, lambda url, timeout: (_ for _ in ()).throw(OSError()))
    assert down.update.rates["USD"].rate_vnd == 25_000
    assert "dùng tỷ giá đã lưu" in down.update.warnings[0]


def test_pg_store_reads_rates_with_source():
    """Trước đây PgStore._fx_rates tạo FxRate thiếu `source` nên lỗi khi DB đã có tỷ giá."""
    import psycopg

    from ingestion.store import PgStore

    row = ("USD", date(2000, 1, 1), 1, "test_pg_store")
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(
            "insert into ref.fx_rates (currency, rate_date, rate_vnd, source) "
            "values (%s, %s, %s, %s) on conflict do nothing",
            row,
        )
    try:
        store = PgStore(DSN)
        assert "USD" in store.fx_rates
        assert all(rate.source for rate in store.fx_rates.values())
        store.close()
    finally:
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute("delete from ref.fx_rates where source = %s", (row[3],))
