"""Đo chuẩn hóa lương (S2-D02) trên một file CSV với tỷ giá thật hôm nay.

Chạy: PYTHONPATH=src uv run python scripts/salary_report.py --input <file.csv>
Thêm --offline để dùng tỷ giá đã lưu thay vì gọi Vietcombank / open.er-api.
"""

import argparse
from collections import Counter
from datetime import date

import pandas as pd

from ingestion.fx import load_fx_config, load_latest, update_rates
from ingestion.salary import parse_salary, parsed_ratio, to_vnd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--salary-col", default="salary")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    config = load_fx_config()
    if args.offline:
        rates = load_latest(config.store_path)
    else:
        update = update_rates(date.today(), config)
        rates = update.rates
        for warning in update.warnings:
            print("CẢNH BÁO:", warning)
    if "USD" in rates:
        usd = rates["USD"]
        print(f"Tỷ giá USD: {usd.rate_vnd:,.2f} VND ({usd.source}, {usd.rate_date})")

    raws = [None if pd.isna(v) else str(v) for v in pd.read_csv(args.input)[args.salary_col]]
    parsed = [parse_salary(raw) for raw in raws]
    converted = [to_vnd(p, rates) for p in parsed]

    print(f"Số tin: {len(parsed)}")
    print(f"Đọc được hoặc ghi rõ thỏa thuận: {parsed_ratio(parsed):.2%}")
    print("Trạng thái:", dict(Counter(p.status for p in parsed)))
    print("Tiền tệ:", dict(Counter(p.currency for p in parsed if p.currency)))
    print("Gross/Net:", dict(Counter(p.pay_type for p in parsed)))
    print("Đổi VND:", dict(Counter(v.note for v in converted)))
    misses = Counter(p.raw for p in parsed if p.status == "unparsed")
    misses.update(p.raw for p, v in zip(parsed, converted, strict=True) if v.note == "out_of_range")
    print(f"Top {args.top} chuỗi không đọc được hoặc ngoài khoảng:")
    for value, count in misses.most_common(args.top):
        print(f"  {count:5d}  {value!r}")


if __name__ == "__main__":
    main()
