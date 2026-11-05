import unicodedata

import pytest
from flashtext import KeywordProcessor

from skillkit import normalize_text

NFC = unicodedata.normalize("NFC", "lập trình")
NFD = unicodedata.normalize("NFD", "lập trình")

# flashtext coi chữ có dấu là ranh giới từ, nên phải thêm vào: nếu không "cơ" khớp với "c".
# Không thêm "." vì sẽ mất kỹ năng ở cuối câu ("c#.", "go.").
LETTERS_WITH_MARKS = {chr(c) for c in range(0xC0, 0x1F00) if chr(c).isalpha()}
NON_WORD_BOUNDARIES = {"+", "#"} | LETTERS_WITH_MARKS


def build_processor() -> KeywordProcessor:
    processor = KeywordProcessor()
    for char in NON_WORD_BOUNDARIES:
        processor.add_non_word_boundary(char)
    for keyword in ["c++", "c#", ".net", "go", "c", "r", "lập trình"]:
        processor.add_keyword(keyword)
    for version in ["11", "14", "17", "20", "23"]:
        processor.add_keyword(f"c++{version}", "c++")
    return processor


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (NFD, NFC),
        ("LẬP TRÌNH", "lập trình"),
        ("  python\n\t và\u00a0 java  ", "python và java"),
    ],
)
def test_normalize_text(text, expected):
    assert normalize_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Biết C++ và C++17", ["c++", "c++"]),
        ("Kinh nghiệm C#.", ["c#"]),
        ("Dùng .NET Core", [".net"]),
        ("Go, Google", ["go"]),
        ("C++, C#, .NET, Go, Google", ["c++", "c#", ".net", "go"]),
        (NFD, ["lập trình"]),
        ("Cơ sở dữ liệu rất tốt", []),
    ],
)
def test_extract_skills(text, expected):
    assert build_processor().extract_keywords(normalize_text(text)) == expected
