import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.profile_dataset import (
    DEFAULT_CONFIG,
    build_markdown,
    classify_title,
    compile_job_groups,
    load_config,
    load_dataset,
    main,
    profile,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "topcv_sample_20.csv"


def test_shape():
    result = profile(load_dataset(FIXTURE))
    assert result["n_rows"] == 20
    assert result["n_cols"] == 7


def test_dup_exact_pct():
    # Dòng 19 và 20 là bản sao của dòng 3 và 7 → 2/20.
    assert profile(load_dataset(FIXTURE))["dup_exact_pct"] == 10.0


def test_missing_experience():
    # 7/20 ô trống, gồm cả các ô vốn đã trống trong dữ liệu gốc.
    assert profile(load_dataset(FIXTURE))["missing_pct"]["experience"] == 35.0


def test_missing_salary():
    assert profile(load_dataset(FIXTURE))["missing_pct"]["salary"] == 5.0


def test_main_writes_json_and_report(tmp_path, capsys):
    out = tmp_path / "nested" / "profile.json"
    main(["--input", str(FIXTURE), "--out", str(out)])

    assert "| n_rows | 20 |" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["n_rows"] == 20


@pytest.fixture
def config():
    return load_config(DEFAULT_CONFIG)


@pytest.fixture
def jobs():
    return pd.DataFrame(
        {
            "title": ["Tester", "Java Developer", "Kế Toán", None],
            "company": ["A", "B", "C", "D"],
            "location": ["Hà Nội", "Hà Nội", "Đà Nẵng", "Huế"],
            "experience": ["1 năm", None, "2 năm", None],
            "salary": ["Thoả thuận", "10 triệu", "12 triệu", "9 triệu"],
            "date_posted": ["2026-01-02", "2025-12-30", "không rõ", None],
            "url": ["https://a.vn/1", "http://a.vn/2", "a.vn/3", None],
        }
    )


def test_profile_dates_ignore_empty_and_invalid_values(jobs, config):
    result = profile(jobs, config)
    assert result["posted_min"] == "2025-12-30"
    assert result["posted_max"] == "2026-01-02"
    assert result["posted_invalid_pct"] == 25.0


def test_url_pct_counts_only_http_urls(jobs, config):
    assert profile(jobs, config)["url_pct"] == 50.0


def test_job_groups_count_every_row(jobs, config):
    groups = profile(jobs, config)["job_groups"]
    assert groups["qa_test"] == {"count": 1, "pct": 25.0}
    assert groups["software_dev"] == {"count": 1, "pct": 25.0}
    assert groups["other"] == {"count": 2, "pct": 50.0}
    assert sum(item["count"] for item in groups.values()) == 4


def test_missing_fields_come_from_column_map(jobs, config):
    assert profile(jobs, config)["missing_fields"] == ["description", "deadline"]


@pytest.mark.parametrize(
    ("title", "group"),
    [
        ("Manual Tester Domain Banking", "qa_test"),
        ("Phân Tích Kinh Doanh (Business Analyst)", "ba_pm"),
        ("IT Sales Executive", "it_sales"),
        ("Data Analyst", "data_ai"),
        ("DevOps Engineer", "infra_support"),
        (".NET Developer", "software_dev"),
        ("JavaScript Intern", "software_dev"),
        ("C++ Intern", "software_dev"),
        ("Chuyên Viên Kế Toán", "other"),
        ("Bảo Trì Máy", "other"),
    ],
)
def test_classify_title(title, group, config):
    patterns = compile_job_groups(config["job_groups"])
    assert classify_title(title, patterns) == group


def test_keyword_does_not_match_inside_another_word():
    patterns = compile_job_groups({"java": ["java"]})
    assert classify_title("JavaScript Developer", patterns) == "other"


def test_report_has_six_sections_and_crawl_conclusion(jobs, config):
    report = build_markdown(profile(jobs, config), config)
    assert sum(line.startswith("## ") for line in report.splitlines()) == 6
    assert "**Kết luận:** Có, cần lấy thêm" in report
    assert "CC BY 4.0" in report


def test_report_says_no_crawl_when_description_exists(jobs, config):
    config["columns"]["description"] = "description"
    jobs["description"] = "Mô tả"
    report = build_markdown(profile(jobs, config), config)
    assert "**Kết luận:** Không cần crawl thêm" in report


def test_main_writes_report(tmp_path):
    report = tmp_path / "reports" / "profiling.md"
    main(["--input", str(FIXTURE), "--report", str(report)])
    assert report.read_text(encoding="utf-8").startswith("# Báo cáo profiling")
