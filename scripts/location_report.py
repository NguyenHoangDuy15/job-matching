"""Đo US-09/AC3 trên một file CSV: tỷ lệ tin có tỉnh chuẩn hoặc nhãn Remote.

Chạy: PYTHONPATH=src uv run python scripts/location_report.py --input <file.csv>
"""

import argparse
from collections import Counter

import pandas as pd

from ingestion.location import load_index_from_seed, normalize_location, parsed_ratio


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--location-col", default="location")
    parser.add_argument("--title-col", default="title")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    index = load_index_from_seed()
    titles = df[args.title_col] if args.title_col in df else [None] * len(df)
    results = [
        normalize_location(
            None if pd.isna(loc) else str(loc), None if pd.isna(t) else str(t), index
        )
        for loc, t in zip(df[args.location_col], titles, strict=True)
    ]

    print(f"Số tin: {len(results)}")
    print(f"Có tỉnh chuẩn hoặc Remote: {parsed_ratio(results):.2%} (mục tiêu ≥ 95%)")
    print("Hình thức:", dict(Counter(r.work_mode for r in results)))
    print(f"Số tin nhiều tỉnh: {sum(len(r.province_codes) > 1 for r in results)}")
    misses = Counter(u for r in results for u in r.unmatched)
    print(f"Top {args.top} giá trị không nhận ra:")
    for value, count in misses.most_common(args.top):
        print(f"  {count:5d}  {value}")


if __name__ == "__main__":
    main()
