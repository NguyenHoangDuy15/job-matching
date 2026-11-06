import json

import pandas as pd
import pytest

from scripts.make_snapshot import (
    allocate,
    main,
    prepare_jobs,
    stratified_sample,
    write_jsonl,
)
from scripts.profile_dataset import DEFAULT_CONFIG, load_config

TITLES = {
    "qa_test": "Tester",
    "ba_pm": "Business Analyst",
    "it_sales": "IT Sales",
    "data_ai": "Data Engineer",
    "infra_support": "DevOps",
    "software_dev": "Java Developer",
}


def make_rows(title: str, start_id: int, n: int) -> list[dict]:
    return [
        {
            "title": title,
            "company": f"Công ty {start_id + i}",
            "location": "Hà Nội",
            "experience": None,
            "salary": "Thoả thuận",
            "date_posted": "2026-01-08",
            "url": f"https://www.topcv.vn/viec-lam/slug/{start_id + i}.html?u_sr_id=abc",
        }
        for i in range(n)
    ]


@pytest.fixture
def config():
    return load_config(DEFAULT_CONFIG)


@pytest.fixture
def raw_jobs():
    rows = []
    for index, title in enumerate(TITLES.values()):
        rows += make_rows(title, 1000 * (index + 1), 30 + index * 20)
    rows += make_rows("Kế Toán", 9000, 5)
    return pd.DataFrame(rows)


def test_allocate_gives_minimum_and_exact_total():
    allocation = allocate({"a": 500, "b": 100, "c": 25}, size=100, min_per_group=20)
    assert sum(allocation.values()) == 100
    assert min(allocation.values()) >= 20
    assert allocation["a"] > allocation["b"] > allocation["c"]


def test_allocate_never_exceeds_group_size():
    counts = {"a": 21, "b": 22, "c": 23}
    allocation = allocate(counts, size=66, min_per_group=20)
    assert allocation == counts


def test_allocate_rejects_group_below_minimum():
    with pytest.raises(ValueError, match="không đủ"):
        allocate({"a": 19, "b": 100}, size=50, min_per_group=20)


def test_allocate_rejects_size_larger_than_data():
    with pytest.raises(ValueError, match="Không thể lấy"):
        allocate({"a": 20, "b": 20}, size=50, min_per_group=20)


def test_prepare_reads_id_from_both_url_formats(config):
    df = pd.DataFrame(make_rows("Tester", 111, 1) + make_rows("DevOps", 222, 1))
    df.loc[1, "url"] = "https://www.topcv.vn/brand/abc/tuyen-dung/devops-j1907652.html?x=1"
    assert sorted(prepare_jobs(df, config)["jd_id"]) == ["topcv_111", "topcv_1907652"]


def test_prepare_fails_on_unknown_url_format(config):
    df = pd.DataFrame(make_rows("Tester", 111, 1))
    df.loc[0, "url"] = "https://www.topcv.vn/khac"
    with pytest.raises(ValueError, match="mã tin"):
        prepare_jobs(df, config)


def test_prepare_removes_badges_and_url_query(config):
    df = pd.DataFrame(make_rows("Tin mới\nGẤP\nTester", 111, 1))
    df.loc[0, "company"] = "Pro\nCÔNG TY A"
    job = prepare_jobs(df, config).iloc[0]
    assert job["title"] == "Tester"
    assert job["company"] == "CÔNG TY A"
    assert job["source_url"] == "https://www.topcv.vn/viec-lam/slug/111.html"


def test_prepare_drops_exact_duplicates_with_different_tracking_id(config):
    first = make_rows("Tester", 111, 1)
    second = make_rows("Tester", 111, 1)
    second[0]["url"] = second[0]["url"].replace("abc", "xyz")
    assert len(prepare_jobs(pd.DataFrame(first + second), config)) == 1


def test_prepare_excludes_other_group(raw_jobs, config):
    assert "other" not in set(prepare_jobs(raw_jobs, config)["group"])


def test_sample_is_independent_of_input_order(raw_jobs, config, tmp_path):
    allocation = {group: 20 for group in TITLES}
    outputs = []
    for name, df in [("a", raw_jobs), ("b", raw_jobs.sample(frac=1, random_state=7))]:
        path = tmp_path / f"{name}.jsonl"
        write_jsonl(stratified_sample(prepare_jobs(df, config), allocation, seed=42), path)
        outputs.append(path.read_bytes())
    assert outputs[0] == outputs[1]


def test_seed_changes_sample(raw_jobs, config):
    jobs = prepare_jobs(raw_jobs, config)
    allocation = {group: 20 for group in TITLES}
    first = stratified_sample(jobs, allocation, seed=42)["jd_id"].tolist()
    second = stratified_sample(jobs, allocation, seed=43)["jd_id"].tolist()
    assert first != second


def test_write_jsonl_format(raw_jobs, config, tmp_path):
    path = tmp_path / "nested" / "snapshot.jsonl"
    sample = prepare_jobs(raw_jobs, config).head(2)
    write_jsonl(sample, path)

    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert "Công ty".encode() in raw  # ensure_ascii=False

    records = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    assert list(records[0]) == [
        "jd_id",
        "title",
        "company",
        "description",
        "location",
        "source_url",
        "group",
    ]
    assert records[0]["description"] is None


def test_main_writes_200_lines_and_prints_six_groups(raw_jobs, tmp_path, capsys):
    csv = tmp_path / "jobs.csv"
    raw_jobs.to_csv(csv, index=False, encoding="utf-8-sig")
    out = tmp_path / "snapshot.jsonl"

    main(["--input", str(csv), "--out", str(out), "--stats"])
    first_run = out.read_bytes()
    main(["--input", str(csv), "--out", str(out)])

    printed = capsys.readouterr().out
    records = [json.loads(line) for line in first_run.decode("utf-8").splitlines()]
    assert len(records) == 200
    assert len({record["jd_id"] for record in records}) == 200
    assert all(f"`{group}`" in printed for group in TITLES)
    assert first_run == out.read_bytes()


def test_main_merges_descriptions_without_changing_selection(raw_jobs, tmp_path):
    csv = tmp_path / "jobs.csv"
    raw_jobs.to_csv(csv, index=False, encoding="utf-8-sig")
    plain = tmp_path / "plain.jsonl"
    main(["--input", str(csv), "--out", str(plain)])
    plain_records = [json.loads(line) for line in plain.read_text(encoding="utf-8").splitlines()]

    first_id = plain_records[0]["jd_id"]
    descriptions = tmp_path / "descriptions.jsonl"
    lines = [
        {"jd_id": first_id, "status": "ok", "description": "Mô tả"},
        {"jd_id": plain_records[1]["jd_id"], "status": "not_found", "description": None},
    ]
    descriptions.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines), encoding="utf-8"
    )
    merged = tmp_path / "merged.jsonl"
    main(["--input", str(csv), "--out", str(merged), "--descriptions", str(descriptions)])
    records = [json.loads(line) for line in merged.read_text(encoding="utf-8").splitlines()]

    assert [r["jd_id"] for r in records] == [r["jd_id"] for r in plain_records]
    assert records[0]["description"] == "Mô tả"
    assert records[1]["description"] is None
