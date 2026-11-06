import csv

import pytest

from scripts.skill_ngrams import count_ngrams, main, to_rows, tokenize


def test_tokenize_keeps_special_skills():
    assert tokenize("- Biết C++, C#. Dùng .NET Core; Node.js.") == [
        ["biết", "c++"],
        ["c#"],
        ["dùng", ".net", "core"],
        ["node.js"],
    ]


def test_ngrams_do_not_cross_punctuation():
    assert ("java", "python") not in count_ngrams(["Java, Python"])


def test_stopwords_filtered_at_edges_only():
    counts = count_ngrams(["kinh nghiệm và java"])
    assert ("và",) not in counts
    assert ("nghiệm", "và") not in counts
    assert ("nghiệm", "và", "java") in counts


def test_to_rows_sorted_and_filtered_by_min_freq():
    counts = count_ngrams(["java python", "java python", "java", "go"])
    assert to_rows(counts, min_freq=2) == [("java", 1, 3), ("java python", 2, 2), ("python", 1, 2)]


def test_main_writes_csv(tmp_path):
    source = tmp_path / "jd.csv"
    source.write_text("description\nBiết Python\nBiết Python\n", encoding="utf-8")
    out = tmp_path / "interim" / "skill_candidates.csv"

    main(["--input", str(source), "--out", str(out)])

    with out.open(encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))
    assert rows[0] == ["ngram", "n", "freq"]
    assert ["biết python", "2", "2"] in rows


def test_main_reports_missing_column(tmp_path):
    source = tmp_path / "jd.csv"
    source.write_text("title\nDev\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="Không có cột 'description'"):
        main(["--input", str(source), "--out", str(tmp_path / "out.csv")])


def test_main_reports_missing_input(tmp_path):
    with pytest.raises(SystemExit, match="Không đọc được dữ liệu"):
        main(["--input", str(tmp_path / "khong_co.csv"), "--out", str(tmp_path / "out.csv")])
