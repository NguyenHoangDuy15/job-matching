"""Tạo snapshot JD lấy mẫu phân tầng theo nhóm nghề, tái lập được nhờ seed cố định."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.profile_dataset import (
    DEFAULT_CONFIG,
    OTHER_GROUP,
    classify_title,
    compile_job_groups,
    load_config,
    load_dataset,
)

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "snapshot_200.jsonl"
OUTPUT_FIELDS = ["jd_id", "title", "company", "description", "location", "source_url", "group"]
# TopCV có 2 dạng URL: /viec-lam/<slug>/2007041.html và /brand/<hãng>/tuyen-dung/<slug>-j190.html
JOB_ID_PATTERN = r"(?:/|-j)(\d+)\.html"


def clean_badge(values: pd.Series) -> pd.Series:
    """Bỏ nhãn dính ở dòng đầu như `GẤP\\n`, `Tin mới\\n`, `Pro\\n`: chỉ giữ dòng cuối."""
    return values.str.split("\n").str[-1].str.strip()


def prepare_jobs(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Đổi tên cột, làm sạch, tạo jd_id, gán nhóm nghề và bỏ dòng trùng exact."""
    columns = {column: field for column, field in config["columns"].items() if field}
    jobs = df.rename(columns=columns)
    jobs["title"] = clean_badge(jobs["title"])
    jobs["company"] = clean_badge(jobs["company"])
    # Query chứa mã phiên tìm kiếm (u_sr_id), cùng một tin có thể mang nhiều mã khác nhau.
    jobs["source_url"] = jobs["source_url"].str.split("?").str[0]

    job_ids = jobs["source_url"].str.extract(JOB_ID_PATTERN)[0]
    if job_ids.isna().any():
        bad_url = jobs.loc[job_ids.isna(), "source_url"].iloc[0]
        raise ValueError(f"Không tách được mã tin từ URL: {bad_url}")
    jobs["jd_id"] = "topcv_" + job_ids

    patterns = compile_job_groups(config["job_groups"])
    jobs["group"] = jobs["title"].map(lambda title: classify_title(title, patterns))

    # Sắp xếp trước để dòng được giữ lại không phụ thuộc thứ tự dòng trong CSV.
    jobs = jobs.sort_values(["jd_id", *columns.values()], kind="stable")
    content_columns = [c for c in jobs.columns if c not in {"jd_id", "source_url"}]
    jobs = jobs.drop_duplicates(subset=content_columns).drop_duplicates(subset="jd_id")
    return jobs[jobs["group"] != OTHER_GROUP].reset_index(drop=True)


def allocate(counts: dict[str, int], size: int, min_per_group: int) -> dict[str, int]:
    """Chia suất: mỗi nhóm `min_per_group`, phần còn lại theo tỷ lệ số tin dư."""
    too_small = [group for group, count in counts.items() if count < min_per_group]
    if too_small:
        raise ValueError(f"Nhóm không đủ {min_per_group} tin: {too_small}")
    remaining = size - min_per_group * len(counts)
    spare = {group: count - min_per_group for group, count in counts.items()}
    total_spare = sum(spare.values())
    if remaining < 0 or remaining > total_spare:
        raise ValueError(f"Không thể lấy {size} tin từ {sum(counts.values())} tin hiện có")

    # Tính theo số tin dư nên suất của một nhóm không bao giờ vượt quá số tin nhóm đó có.
    quotas = {group: remaining * extra / total_spare for group, extra in spare.items()}
    allocation = {group: min_per_group + int(quota) for group, quota in quotas.items()}
    leftover = size - sum(allocation.values())
    # Hòa phần dư thì theo tên nhóm để kết quả luôn cố định.
    by_remainder = sorted(quotas, key=lambda group: (int(quotas[group]) - quotas[group], group))
    for group in by_remainder[:leftover]:
        allocation[group] += 1
    return allocation


def stratified_sample(jobs: pd.DataFrame, allocation: dict[str, int], seed: int) -> pd.DataFrame:
    """Lấy mẫu từng nhóm theo số suất đã chia, kết quả sắp theo jd_id."""
    # groupby().sample(n=...) chỉ nhận một n chung nên phải lấy theo từng nhóm.
    frames = [
        jobs[jobs["group"] == group].sample(n=n, random_state=seed)
        for group, n in allocation.items()
    ]
    return pd.concat(frames).sort_values("jd_id", kind="stable").reset_index(drop=True)


def load_descriptions(path: Path) -> dict[str, str]:
    """Đọc mô tả đã lấy được, bỏ các tin không có mô tả."""
    with path.open(encoding="utf-8") as file:
        records = (json.loads(line) for line in file if line.strip())
        return {r["jd_id"]: r["description"] for r in records if r.get("description")}


def write_jsonl(sample: pd.DataFrame, path: Path) -> None:
    """Ghi JSONL UTF-8, luôn xuống dòng LF để sha256 giống nhau trên Windows và Linux."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for _, row in sample.iterrows():
            record = {
                field: None if field not in row or pd.isna(row[field]) else row[field]
                for field in OUTPUT_FIELDS
            }
            file.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def format_stats(counts: dict[str, int], allocation: dict[str, int]) -> str:
    """Tạo bảng phân bố Markdown để dán vào PR."""
    total = sum(allocation.values())
    lines = [
        "| Nhóm | Số tin sau lọc | Số tin trong snapshot | % snapshot |",
        "|---|---:|---:|---:|",
    ]
    lines += [
        f"| `{group}` | {counts[group]} | {n} | {n / total * 100:.1f} |"
        for group, n in allocation.items()
    ]
    lines.append(f"| **Tổng** | {sum(counts.values())} | {total} | 100.0 |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="File CSV hoặc thư mục chứa CSV")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Đường dẫn file JSONL")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="File cấu hình YAML")
    parser.add_argument("--descriptions", type=Path, help="File JSONL từ import_saved_pages")
    parser.add_argument("--stats", action="store_true", help="In bảng phân bố theo nhóm nghề")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    settings = config["snapshot"]
    jobs = prepare_jobs(load_dataset(args.input), config)
    counts = {group: int((jobs["group"] == group).sum()) for group in config["job_groups"]}
    allocation = allocate(counts, settings["size"], settings["min_per_group"])
    sample = stratified_sample(jobs, allocation, settings["seed"])
    # Chỉ gắn mô tả sau khi lấy mẫu, nên 200 tin được chọn không đổi dù mô tả thiếu hay đủ.
    descriptions = load_descriptions(args.descriptions) if args.descriptions else {}
    sample["description"] = sample["jd_id"].map(descriptions)
    write_jsonl(sample, args.out)

    if args.stats:
        print(format_stats(counts, allocation))
        print(f"Có description: {int(sample['description'].notna().sum())}/{len(sample)}")
    print(f"sha256: {hashlib.sha256(args.out.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
