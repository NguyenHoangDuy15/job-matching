"""Lập hồ sơ dữ liệu CSV và ghi báo cáo profiling."""

import argparse
import json
import re
from pathlib import Path

import pandas as pd
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "column_map.yaml"
OTHER_GROUP = "other"


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


def load_config(path: Path) -> dict:
    """Đọc file cấu hình ánh xạ cột và luật nhóm nghề."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def compile_job_groups(job_groups: dict[str, list[str]]) -> dict[str, re.Pattern]:
    """Tạo regex cho từng nhóm; biên từ giúp `java` không khớp `javascript`."""
    return {
        group: re.compile(
            "|".join(rf"(?<!\w){re.escape(keyword.lower())}(?!\w)" for keyword in keywords)
        )
        for group, keywords in job_groups.items()
    }


def classify_title(title: str, patterns: dict[str, re.Pattern]) -> str:
    """Trả về nhóm đầu tiên khớp với tiêu đề, không khớp thì trả về `other`."""
    lowered = title.lower()
    for group, pattern in patterns.items():
        if pattern.search(lowered):
            return group
    return OTHER_GROUP


def job_group_distribution(titles: pd.Series, job_groups: dict[str, list[str]]) -> dict:
    """Đếm số tin và % theo nhóm nghề, giữ cả nhóm có 0 tin."""
    patterns = compile_job_groups(job_groups)
    counts = titles.fillna("").map(lambda title: classify_title(title, patterns)).value_counts()
    return {
        group: {
            "count": int(counts.get(group, 0)),
            "pct": round(float(counts.get(group, 0)) / len(titles) * 100, 2),
        }
        for group in [*job_groups, OTHER_GROUP]
    }


def profile(df: pd.DataFrame, config: dict | None = None) -> dict:
    """Tính các chỉ số cơ bản; có config thì tính thêm ngày đăng, URL và nhóm nghề."""
    result = {
        "n_rows": len(df),
        "n_cols": df.shape[1],
        "missing_pct": (df.isna().mean() * 100).round(2).to_dict(),
        "dup_exact_pct": round(float(df.duplicated().mean() * 100), 2),
    }
    if config is None:
        return result

    columns = {field: column for column, field in config["columns"].items() if field}
    posted_raw = df[columns["posted_at"]]
    posted = pd.to_datetime(posted_raw, errors="coerce")
    url_column = columns["source_url"]
    other_columns = [column for column in df.columns if column != url_column]

    result |= {
        "columns": list(df.columns),
        "dup_without_url_pct": round(float(df.duplicated(subset=other_columns).mean() * 100), 2),
        "posted_min": posted.min().date().isoformat() if posted.notna().any() else None,
        "posted_max": posted.max().date().isoformat() if posted.notna().any() else None,
        "posted_invalid_pct": round(float((posted_raw.notna() & posted.isna()).mean() * 100), 2),
        "url_pct": round(float(df[url_column].str.startswith("http", na=False).mean() * 100), 2),
        "job_groups": job_group_distribution(df[columns["title"]], config["job_groups"]),
        "missing_fields": [f for f in config["raw_job_fields"] if f not in columns],
    }
    return result


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
    if "job_groups" in result:
        lines += [
            f"| dup_without_url_pct | {result['dup_without_url_pct']:.2f} |",
            f"| posted_min | {result['posted_min']} |",
            f"| posted_max | {result['posted_max']} |",
            f"| posted_invalid_pct | {result['posted_invalid_pct']:.2f} |",
            f"| url_pct | {result['url_pct']:.2f} |",
        ]
        lines += [
            f"| job_group.{group} | {item['count']} ({item['pct']:.2f}%) |"
            for group, item in result["job_groups"].items()
        ]
    return "\n".join(lines)


def crawl_conclusion(missing_fields: list[str]) -> str:
    """Viết câu kết luận dựa trên trường raw_job còn thiếu."""
    if "description" in missing_fields:
        return (
            "**Kết luận:** Có, cần lấy thêm nội dung mô tả công việc bằng crawl hoặc nguồn khác, "
            "vì bộ dữ liệu không có trường `description` nên chưa đủ cho semantic search CV ↔ JD; "
            "cần kiểm tra điều khoản và `robots.txt` của nguồn trước khi crawl."
        )
    return "**Kết luận:** Không cần crawl thêm, vì bộ dữ liệu đã có trường `description`."


def build_markdown(result: dict, config: dict) -> str:
    """Tạo báo cáo profiling gồm 6 mục và một câu kết luận."""
    dataset = config["dataset"]
    missing_rows = [f"| `{column}` | {pct:.2f} |" for column, pct in result["missing_pct"].items()]
    group_rows = [
        f"| `{group}` | {item['count']} | {item['pct']:.2f} |"
        for group, item in result["job_groups"].items()
    ]
    missing_fields = ", ".join(f"`{field}`" for field in result["missing_fields"]) or "không có"
    lines = [
        "# Báo cáo profiling TopCV 2026",
        "",
        f"Nguồn: [{dataset['name']}]({dataset['url']}), tác giả `{dataset['author']}`, "
        f"giấy phép {dataset['license']}.",
        "",
        "## 1. Quy mô và cột",
        "",
        f"- Số dòng: {result['n_rows']}",
        f"- Số cột: {result['n_cols']}",
        f"- Các cột: {', '.join(f'`{column}`' for column in result['columns'])}",
        f"- Trường `raw_job` chưa có trong dữ liệu: {missing_fields}",
        "",
        "## 2. Dữ liệu thiếu",
        "",
        "| Cột | % ô trống |",
        "|---|---:|",
        *missing_rows,
        "",
        "## 3. Trùng lặp",
        "",
        f"- Trùng exact trên mọi cột: {result['dup_exact_pct']:.2f}%",
        f"- Trùng khi bỏ cột URL: {result['dup_without_url_pct']:.2f}%",
        "",
        "## 4. Ngày đăng",
        "",
        f"- Sớm nhất: {result['posted_min']}",
        f"- Muộn nhất: {result['posted_max']}",
        f"- Có giá trị nhưng không đọc được: {result['posted_invalid_pct']:.2f}%",
        "",
        "## 5. URL tin gốc",
        "",
        f"- Có URL bắt đầu bằng `http`: {result['url_pct']:.2f}%",
        "",
        "## 6. Nhóm nghề",
        "",
        "Gán theo từ khóa trong tiêu đề, xem `config/column_map.yaml`. Kết quả chưa được đối chiếu "
        "với mẫu gán nhãn.",
        "",
        "| Nhóm | Số tin | % |",
        "|---|---:|---:|",
        *group_rows,
        "",
        crawl_conclusion(result["missing_fields"]),
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="File CSV hoặc thư mục chứa CSV")
    parser.add_argument("--out", type=Path, help="Đường dẫn file JSON kết quả (không bắt buộc)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="File cấu hình YAML")
    parser.add_argument("--report", type=Path, help="Đường dẫn báo cáo Markdown (không bắt buộc)")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    result = profile(load_dataset(args.input), config)
    print(format_report(result))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(build_markdown(result, config), encoding="utf-8")


if __name__ == "__main__":
    main()