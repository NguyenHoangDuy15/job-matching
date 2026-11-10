"""Cập nhật tỷ giá và tính lại lương VND cho tin ngoại tệ trong DB (S2-D02).

crawl.py đã tự chạy bước này trước mỗi lượt crawl (tắt bằng --skip-fx). Dùng script này
khi muốn cập nhật tỷ giá riêng, ví dụ chạy tay hoặc đặt lịch tách khỏi crawl.

    uv run python scripts/update_fx.py            # cần DATABASE_URL (biến môi trường hoặc .env)
    uv run python scripts/update_fx.py --dry-run  # chỉ lấy và in tỷ giá, không ghi DB
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.crawl import _database_url  # noqa: E402
from ingestion.fx import fetch_rates, load_fx_config, load_latest_pg, sync_rates_pg  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="không ghi DB")
    args = parser.parse_args(argv)
    config = load_fx_config()
    if args.dry_run:
        rates = fetch_rates(config)
        for code in ("USD", "EUR", "JPY", "SGD"):
            if code in rates:
                r = rates[code]
                print(f"{code}: {r.rate_vnd:,.2f} VND ({r.source}, {r.rate_date})")
        return 0
    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL (biến môi trường hoặc file .env)")
    import psycopg

    with psycopg.connect(
        dsn.replace("postgresql+psycopg://", "postgresql://"), prepare_threshold=None
    ) as conn:
        result = sync_rates_pg(conn, date.today(), config)
        latest = load_latest_pg(conn)
    for warning in result.update.warnings:
        print(f"! {warning}")
    usd = latest.get("USD")
    print(
        f"Tỷ giá USD: {usd.rate_vnd:,.2f} VND ({usd.source}, {usd.rate_date})"
        if usd
        else "! DB chưa có tỷ giá USD"
    )
    print(f"Ngoại tệ đổi giá: {sorted(result.update.changed) or 'không'}")
    print(f"Tin ngoại tệ được tính lại lương VND: {result.jobs_refreshed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
