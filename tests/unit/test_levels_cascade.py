"""S2-D04: Tầng 1 (hồi quy trên SkillMatcher), ghép tầng, gộp, pipeline cả JD."""

from pathlib import Path

import pytest

from skillkit.levels.cascade import Mention, aggregate, label_mention
from skillkit.levels.pipeline import SkillLabeler, rule_section
from skillkit.levels.rules import Decision
from skillkit.levels.tier2 import JevLocal, build_model, prep
from skillkit.matcher import SkillMatcher
from skillkit.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def matcher():
    return SkillMatcher(load_taxonomy(ROOT / "config" / "skills.yaml"))


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Thành thạo Java.", ["java"]),
        ("Biết JavaScript, React Native", ["javascript", "react_native"]),
        ("C/C++ và C#", ["c_lang", "cpp", "csharp"]),
        ("ASP.NET Core vs .NET", ["aspnet", "dotnet"]),
        ("Cử nhân CNTT", []),
        ("C-level, R&D", []),
        ("Node.js là lợi thế", ["nodejs"]),
        ("Có kinh nghiệm kiểm thử", ["software_testing"]),
        ("Java-based, C-suite", ["java"]),
        ("Làm việc tại Gò Vấp", []),
    ],
)
def test_tier1_regression(matcher, text, expected):
    assert [m.skill_id for m in matcher.find(text)] == expected


class FakeClf:
    version = "fake"

    def __init__(self, p: float) -> None:
        self.p = p

    def prob_preferred(self, section, sentence, skill_text):
        return self.p


def _m(section, sentence, skill, has_sections=True, skill_id=None):
    s = sentence.index(skill)
    return Mention(
        "1", skill_id or skill.lower(), skill, section, sentence, s, s + len(skill), has_sections
    )


def test_same_rank_required_wins_and_counts():
    a = _m("REQ", "Kinh nghiệm Java", "Java")
    b = _m("PREF", "Kinh nghiệm Java", "Java")
    rows = aggregate(
        [
            (a, Decision("REQUIRED", 0.85, "rule_section")),
            (b, Decision("PREFERRED", 0.95, "rule_section")),
        ]
    )
    assert [(r.level, r.mention_count) for r in rows] == [("required", 2)]


def test_stronger_source_wins():
    a = _m("NONE", "Java", "Java", has_sections=False)
    b = _m("NONE", "Java is a plus", "Java", has_sections=False)
    rows = aggregate(
        [(a, Decision("REQUIRED", 0.5, "fallback")), (b, Decision("PREFERRED", 0.9, "rule_cue"))]
    )
    assert rows[0].level == "preferred"


def test_mentioned_loses_to_any_level():
    a = _m("DESC", "Phát triển API bằng Java", "Java")
    b = _m("NONE", "Java", "Java")
    rows = aggregate(
        [(a, Decision("MENTIONED", 0.6, "rule_desc")), (b, Decision("REQUIRED", 0.5, "fallback"))]
    )
    assert rows[0].level == "required"


def test_benefits_dropped():
    m = _m("BEN", "Được đào tạo AWS", "AWS")
    assert aggregate([(m, label_mention(m, None))]) == []


def test_model_decides_unsure_case_without_headings():
    m = _m("NONE", "Hiểu biết về Kafka sẽ giúp ích nhiều", "Kafka", has_sections=False)
    assert label_mention(m, FakeClf(0.9)) == Decision("PREFERRED", 0.9, "model")
    assert label_mention(m, FakeClf(0.6)).source == "fallback"
    assert label_mention(m, None) == Decision("REQUIRED", 0.5, "fallback")


def test_model_flips_requirement_only_when_very_sure():
    m = _m("REQ", "Kinh nghiệm Kafka", "Kafka")
    assert label_mention(m, FakeClf(0.8)).level == "REQUIRED"
    assert label_mention(m, FakeClf(0.95)) == Decision("PREFERRED", 0.95, "model")


def test_model_overrides_only_nearest_cue_guess():
    same_item = _m("REQ", "Thành thạo Java, ưu tiên biết thêm Kotlin", "Java")  # 0.8
    assert label_mention(same_item, FakeClf(0.99)).source == "rule_mixed"
    nearest = _m("REQ", "Thành thạo Java là một lợi thế", "Java")  # 2 cue cùng mục
    assert label_mention(nearest, None).conf == 0.65
    assert label_mention(nearest, FakeClf(0.9)) == Decision("PREFERRED", 0.9, "model")
    assert label_mention(nearest, FakeClf(0.6)).source == "rule_mixed"


def test_description_without_cue_is_mentioned():
    m = _m("DESC", "Phát triển dịch vụ bằng Kafka", "Kafka")
    assert label_mention(m, FakeClf(0.99)).level == "MENTIONED"


def test_rule_section_uses_original_heading():
    line = "- Biết Java là bắt buộc, Spring Boot là một lợi thế"
    assert rule_section("preferred", line, True) == "REQ"
    assert rule_section("preferred", "- Ít nhất 1 năm React", True) == "PREF"
    assert rule_section("other", line, False) == "NONE"
    # Chỉ cụm trong ngoặc làm D03 chuyển dòng → cả dòng là ưu tiên.
    assert (
        rule_section("preferred", "- Hiểu biết API, Git. (điểm cộng, không bắt buộc)", True)
        == "PREF"
    )


JD = """Tuyển Backend Developer
Mô tả công việc
- Phát triển API bằng Kafka
Yêu cầu
- Thành thạo Java, ưu tiên biết thêm Kotlin
- Biết Python là bắt buộc, Docker là một lợi thế
- Tiếng Nhật N3 không bắt buộc
Quyền lợi
- Được đào tạo AWS"""


def test_pipeline_end_to_end(matcher):
    rows = SkillLabeler(matcher).label_text("7", JD)
    levels = {r.skill_id: r.level for r in rows}
    assert levels["java"] == "required"
    assert levels["kotlin"] == "preferred"
    assert levels["python"] == "required"
    assert levels["docker"] == "preferred"
    assert levels["kafka"] == "mentioned"
    assert "aws" not in levels
    assert all(r.extractor == "dict" for r in rows)


def test_pipeline_from_columns_matches_text(matcher):
    from skillkit.sections import split_text

    labeler = SkillLabeler(matcher)
    by_text = {(r.skill_id, r.level) for r in labeler.label_text("7", JD)}
    by_cols = {(r.skill_id, r.level) for r in labeler.label_columns("7", split_text(JD).columns())}
    assert by_text == by_cols


def test_pipeline_without_headings_is_required(matcher):
    rows = SkillLabeler(matcher).label_text("8", "Cần người biết Java. Biết Docker là lợi thế.")
    assert {r.skill_id: r.level for r in rows} == {"java": "required", "docker": "preferred"}


def test_jev_local_roundtrip(tmp_path):
    import joblib

    x = [
        prep(sec, s, "Java") for sec, s in [("REQ", "Thành thạo Java"), ("REQ", "Java là lợi thế")]
    ]
    model = build_model().set_params(tfidfvectorizer__min_df=1).fit(x * 5, [0, 1] * 5)
    path = tmp_path / "jev_test.joblib"
    joblib.dump(model, path)
    clf = JevLocal(path)
    assert clf.version == "jev_test"
    assert clf.prob_preferred("REQ", "Kotlin là lợi thế", "Kotlin") > 0.5
    assert prep("REQ", "Biết Java", "Java") == "[REQ] Biết  <s> "
