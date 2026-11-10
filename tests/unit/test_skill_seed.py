"""S2-D03: từ điển ≥ 300 kỹ năng và seed DB luôn khớp YAML."""

from pathlib import Path

import pytest

from skillkit import load_taxonomy

ROOT = Path(__file__).resolve().parents[2]
SKILLS_YAML = ROOT / "config" / "skills.yaml"
SEED_SQL = ROOT / "db" / "seed" / "seed_skills.sql"


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy(SKILLS_YAML)


def test_at_least_300_skills_with_name_aliases_and_group(taxonomy):
    skills = [s for s in taxonomy if s.level > 1]
    assert len(skills) >= 300
    assert all(s.name for s in skills)  # US-10/AC2: tên chuẩn
    assert all(taxonomy.category_of(s.id) in range(1, 8) for s in skills)  # nhóm
    assert sum(len(s.aliases) for s in skills) >= 600  # cách viết khác


@pytest.mark.parametrize("skill_id", ["golang", "r_lang", "c_lang"])
def test_required_ambiguous_skills_have_rules(taxonomy, skill_id):
    skill = taxonomy.get(skill_id)
    assert skill.ambiguous and skill.rule and skill.rule.forms


def test_net_alone_is_not_an_alias(taxonomy):
    # "Net" trơn là lương net; .NET chỉ nhận khi có dấu chấm hoặc "dotnet".
    assert "net" not in [t.lower() for s in taxonomy for t in s.terms()]


def test_seed_sql_is_up_to_date(taxonomy):
    from scripts.build_skill_seed import render

    assert SEED_SQL.read_text(encoding="utf-8") == render(taxonomy), (
        "db/seed/seed_skills.sql lệch config/skills.yaml: "
        "chạy PYTHONPATH=src uv run python scripts/build_skill_seed.py"
    )


def test_ambiguous_terms_need_context_in_seed(taxonomy):
    from scripts.build_skill_seed import rows

    _, aliases = rows(taxonomy)
    flagged = {alias for alias, _, needs, _ in aliases if needs}
    assert {"go", "r", "c", "ai", "react", "swift", "spring", "excel"} <= flagged
    assert "golang" not in flagged and "javascript" not in flagged
