import csv

import pytest

from scripts.evaluate_extraction import (
    NameResolver,
    build_gold,
    gold_from_mentions,
    macro_f1,
    prf,
    read_bo_sot,
    score_sets,
)
from skillkit.levels.pipeline import SKILLS_YAML, SkillLabeler
from skillkit.taxonomy import load_taxonomy


@pytest.fixture(scope="module")
def resolver():
    labeler = SkillLabeler.default(with_model=False)
    return NameResolver(load_taxonomy(SKILLS_YAML), labeler)


def _csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def test_prf():
    assert prf(8, 10, 16) == {
        "precision": 0.8,
        "recall": 0.5,
        "f1": 0.615,
        "tp": 8,
        "pred": 10,
        "gold": 16,
    }
    assert prf(0, 0, 0)["f1"] == 0.0


def test_score_sets_counts_level_separately():
    pred = {("a", "java"): "required", ("a", "go"): "preferred", ("a", "sql"): "required"}
    gold = {("a", "java"): "required", ("a", "go"): "required", ("a", "aws"): "required"}
    got = score_sets(pred, gold)
    assert got["skill"]["tp"] == 2 and got["skill"]["precision"] == 0.667
    assert got["skill_level"]["tp"] == 1  # go đúng kỹ năng, sai mức


def test_gold_from_mentions_takes_highest_label(tmp_path):
    path = _csv(
        tmp_path / "g.csv",
        ["jd_id", "skill_id", "gold"],
        [
            ["a", "java", "mentioned"],
            ["a", "java", "required"],  # cùng kỹ năng, lần nhắc khác → required
            ["a", "kafka", "mentioned"],  # không thành thẻ
            ["a", "aws", "drop"],
            ["a", "go", "preferred"],
        ],
    )
    assert gold_from_mentions(path) == {("a", "java"): "required", ("a", "go"): "preferred"}


def test_resolver_exact_partial_none(resolver):
    assert resolver.resolve("ReactJS")[1] in ("exact", "partial")
    assert resolver.resolve("python") == ("python", "exact")
    assert resolver.resolve("Ngôn ngữ Klingon XYZ")[1] == "none"


def test_build_gold_skips_already_found_and_marks_new(resolver):
    pred = {("a", "python"): "required"}
    rows = [
        {"jd_id": "a", "ky_nang_bo_sot": "Python", "muc": "required"},  # máy đã có
        {"jd_id": "a", "ky_nang_bo_sot": "Công cụ Zzz", "muc": "preferred"},  # ngoài từ điển
    ]
    gold, added, warnings = build_gold({}, rows, resolver, pred)
    assert len(warnings) == 1
    # Máy đã có thẻ người gán ghi là sót: không phải bỏ sót nhưng vẫn là thẻ chuẩn (không thành
    # thẻ sai khi từ điển vừa được sửa để bắt được nó).
    assert gold == {("a", "python"): "required", ("a", "new:công cụ zzz"): "preferred"}
    assert [r["ky_nang_bo_sot"] for r in added] == ["Công cụ Zzz"]
    assert added[0]["match"] == "none"


def test_read_bo_sot_skips_blank_and_maps_vietnamese(tmp_path):
    path = _csv(
        tmp_path / "b.csv",
        ["jd_id", "ky_nang_bo_sot", "muc", "note"],
        [["a", "", "", ""], ["a", "Docker", "ưu tiên", ""], ["b", "SAP", "bắt buộc", ""]],
    )
    rows = read_bo_sot(path)
    assert [(r["ky_nang_bo_sot"], r["muc"]) for r in rows] == [
        ("Docker", "preferred"),
        ("SAP", "required"),
    ]


def test_read_bo_sot_rejects_bad_level(tmp_path):
    path = _csv(
        tmp_path / "b.csv", ["jd_id", "ky_nang_bo_sot", "muc", "note"], [["a", "Docker", "x", ""]]
    )
    with pytest.raises(ValueError, match="dòng 2"):
        read_bo_sot(path)


def test_macro_f1_ignores_jd_without_cards():
    pred = {("a", "java"): "required"}
    gold = {("a", "java"): "required"}
    assert macro_f1(pred, gold, ["a", "b"]) == 1.0
