import unicodedata
from pathlib import Path

import pytest

from skillkit import TaxonomyError, load_taxonomy

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        ("skills_bad_dup_id.yaml", "trùng id 'python'"),
        ("skills_bad_dup_alias.yaml", "alias 'go' trùng giữa golang và go_lang"),
        ("skills_bad_level.yaml", r"id=python.*level phải thuộc \[1, 2, 3\], nhận 4"),
        ("skills_bad_parent.yaml", "python: parent 'pythn_group' không tồn tại"),
        ("skills_bad_ambiguous.yaml", "golang: ambiguous=True thì context không được rỗng"),
    ],
)
def test_schema_error(fixture, message):
    with pytest.raises(TaxonomyError, match=message):
        load_taxonomy(FIXTURES / fixture)


def _write_yaml(tmp_path, text):
    path = tmp_path / "skills.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_ok(tmp_path):
    path = _write_yaml(
        tmp_path,
        "skills:\n"
        "  - id: programming\n"
        "    level: 1\n"
        "  - id: python\n"
        "    level: 2\n"
        "    parent: programming\n"
        "    aliases: [py, python3]\n",
    )
    taxonomy = load_taxonomy(path)
    assert len(taxonomy) == 2
    assert "python" in taxonomy
    assert taxonomy.get("python").aliases == ["py", "python3"]


def test_dup_alias_after_nfc(tmp_path):
    nfc = unicodedata.normalize("NFC", "Lập trình")
    nfd = unicodedata.normalize("NFD", "Lập trình")
    assert nfc != nfd
    path = _write_yaml(
        tmp_path,
        "skills:\n"
        "  - id: a\n"
        "    level: 1\n"
        f"    aliases: [{nfc}]\n"
        "  - id: b\n"
        "    level: 1\n"
        f"    aliases: [{nfd}]\n",
    )
    with pytest.raises(TaxonomyError, match="trùng giữa a và b"):
        load_taxonomy(path)


def test_quoted_level_rejected(tmp_path):
    path = _write_yaml(tmp_path, 'skills:\n  - id: a\n    level: "1"\n')
    with pytest.raises(TaxonomyError, match="id=a"):
        load_taxonomy(path)


def test_missing_skills_key(tmp_path):
    path = _write_yaml(tmp_path, "- id: a\n  level: 1\n")
    with pytest.raises(TaxonomyError, match="'skills'"):
        load_taxonomy(path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "  - {id: a, level: 2, parent: b}\n  - {id: b, level: 1, parent: a}\n",
            "vòng lặp parent",
        ),
        ("  - {id: a, level: 2, parent: a}\n", "vòng lặp parent"),
        (
            "  - {id: root, level: 1}\n  - {id: a, level: 1, parent: root}\n",
            "a: level 1 không được có parent",
        ),
        ("  - {id: a, level: 2}\n", "a: level 2 bắt buộc có parent"),
        (
            "  - {id: root, level: 1}\n  - {id: a, level: 3, parent: root}\n",
            "a: level 3 phải có parent level 2",
        ),
    ],
)
def test_parent_rules(tmp_path, body, message):
    path = _write_yaml(tmp_path, "skills:\n" + body)
    with pytest.raises(TaxonomyError, match=message):
        load_taxonomy(path)


@pytest.fixture
def small_taxonomy():
    return load_taxonomy(FIXTURES / "skills_small.yaml")


def test_relations_ancestors(small_taxonomy):
    assert small_taxonomy.ancestors("react") == ["javascript", "programming"]
    assert small_taxonomy.ancestors("programming") == []


def test_relations_children(small_taxonomy):
    assert small_taxonomy.children("javascript") == ["react", "vue"]
    assert small_taxonomy.children("react") == []


def test_relations_family_members(small_taxonomy):
    assert small_taxonomy.family_members("react") == ["javascript", "programming", "react"]
    assert small_taxonomy.family_members("javascript") == [
        "javascript",
        "programming",
        "react",
        "vue",
    ]


@pytest.mark.parametrize("method", ["ancestors", "children", "family_members"])
def test_unknown_id_raises_key_error(small_taxonomy, method):
    with pytest.raises(KeyError):
        getattr(small_taxonomy, method)("khong_co")
