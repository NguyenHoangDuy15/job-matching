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
