"""Lập hồ sơ cơ bản cho dữ liệu CSV: số dòng, số cột, % thiếu và % trùng exact."""

import argparse
import json
from pathlib import Path

import pandas as pd


def load_dataset(path: Path) -> pd.DataFrame:
    """Đọc một file CSV, hoặc gộp mọi file CSV trong một thư mục."""
    files = sorted(path.glob("*.csv")) if path.is_dir() else [path]
    if not files:
        raise FileNotFoundError(f"Không tìm thấy file CSV trong {path}")

    # Giữ mọi cột ở dạng chuỗi và chỉ coi ô rỗng là thiếu.
    frames = [
        pd.read_csv(file, encoding="utf-8-sig", dtype=str, keep_default_na=False, na_values=[""])
        for file in files
    ]
    return pd.concat(frames, ignore_index=True)


def profile(df: pd.DataFrame) -> dict:
    """Tính số dòng, số cột, % thiếu theo cột và % dòng trùng exact."""
    return {
        "n_rows": len(df),
        "n_cols": df.shape[1],
        "missing_pct": (df.isna().mean() * 100).round(2).to_dict(),
        "dup_exact_pct": round(float(df.duplicated().mean() * 100), 2),
    }


def format_report(result: dict) -> str:
    """Tạo bảng Markdown để in ra màn hình và dán vào issue."""
    lines = [
        "| metric | value |",
        "|---|---|",
        f"| n_rows | {result['n_rows']} |",
        f"| n_cols | {result['n_cols']} |",
        f"| dup_exact_pct | {result['dup_exact_pct']:.2f} |",
    ]
    lines += [
        f"| missing_pct.{column} | {pct:.2f} |" for column, pct in result["missing_pct"].items()
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="File CSV hoặc thư mục chứa CSV")
    parser.add_argument("--out", type=Path, help="Đường dẫn file JSON kết quả (không bắt buộc)")
    args = parser.parse_args(argv)

    result = profile(load_dataset(args.input))
    print(format_report(result))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()