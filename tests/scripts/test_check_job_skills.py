import csv

import pytest

from scripts.check_job_skills import (
    COLUMNS,
    _fix_repeated_paste,
    _items,
    comma_names,
    merge,
    score,
)

KEEP = ("Cẩn thận, chi tiết",)


def write_csv(path, rows, bom=False):
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in COLUMNS})


def test_comma_names_from_taxonomy():
    assert "Cẩn thận, chi tiết" in comma_names()


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("Python, SQL", ["Python", "SQL"]),
        ("Cẩn thận, chi tiết, Photoshop", ["Cẩn thận, chi tiết", "Photoshop"]),
        ("Sales, Sales, Git", ["Sales", "Git"]),
        ("Sales\tGit", ["Sales", "Git"]),
        ("", []),
    ],
)
def test_items(cell, expected):
    assert _items(cell, KEEP) == expected


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("A1, B2, C3A1, B2, C3", "A1, B2, C3"),
        ("Sales, BD\tSales, BD", "Sales, BD"),
        ("Linux, WinLinux, WinLin", "Linux, Win"),
        ("Python, SQL", "Python, SQL"),
        ("", ""),
    ],
)
def test_fix_repeated_paste(cell, expected):
    assert _fix_repeated_paste(cell) == expected


def test_score_counts_and_skips(tmp_path):
    path = tmp_path / "check.csv"
    write_csv(
        path,
        [
            # 3 thẻ (tên có dấu phẩy là 1 thẻ), 1 sai, thiếu 2.
            {
                "job_id": "1",
                "bat_buoc": "Cẩn thận, chi tiết, Photoshop, System Design",
                "sai": "System Design",
                "thieu": "After Effects, Premiere Pro",
            },
            # 2 thẻ đúng, 1 sai mức, không thiếu → tin đầy đủ.
            {"job_id": "2", "bat_buoc": "Jira", "uu_tien": "Tiếng Trung", "sai_muc": "Tiếng Trung"},
            # "Git" ghi thiếu nhưng máy đã gắn: không tính thiếu, có cảnh báo.
            {"job_id": "3", "uu_tien": "Git", "thieu": "Git, Docker"},
            {"job_id": "4", "note": "JD lỗi crawler - bỏ qua"},
        ],
    )
    result = score(path, keep=KEEP)
    assert result["tin"] == 4
    assert result["bo_qua"] == 1
    assert result["tin_cham"] == 3
    assert result["the"] == 6
    assert result["the_sai"] == 1
    assert result["thieu"] == 3
    assert result["precision_the"] == round(5 / 6, 3)
    assert result["dung_muc"] == round(4 / 5, 3)
    assert result["recall_xap_xi"] == round(5 / 8, 3)
    assert result["tin_day_du"] == "1/3"
    assert result["canh_bao"] == ["job 3: Git vừa ở 'thieu' vừa đã gắn"]


def test_merge_reads_bom_and_fixes_paste(tmp_path):
    a, b, out = tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "out.csv"
    write_csv(a, [{"job_id": "1", "thieu": "Sales, BD\tSales, BD"}], bom=True)
    write_csv(b, [{"job_id": "2", "sai": "SOLID"}], bom=True)
    notes = merge([a, b], out)
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [r["job_id"] for r in rows] == ["1", "2"]
    assert rows[0]["thieu"] == "Sales, BD"
    assert notes == ["job 1: cột thieu bị dán lặp, giữ bản đầu"]


def test_merge_rejects_duplicate_job(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    write_csv(a, [{"job_id": "1"}])
    write_csv(b, [{"job_id": "1"}])
    with pytest.raises(ValueError, match="job 1"):
        merge([a, b], tmp_path / "out.csv")
