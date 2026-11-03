import json
from pathlib import Path

from scripts.profile_dataset import load_dataset, main, profile

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
