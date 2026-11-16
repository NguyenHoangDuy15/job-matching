"""S3-D01: nhận loại file, chuẩn hóa chữ, chỉ số chất lượng."""

import io
import zipfile

import pytest

from cvparser.extract.errors import ErrorCode, ExtractionError
from cvparser.extract.models import ExtractOptions
from cvparser.extract.normalize import normalize_line, normalize_text
from cvparser.extract.quality import measure
from cvparser.extract.sniff import detect_kind


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


_CT = '<Types><Override ContentType="application/vnd.openxmlformats-officedocument.{}"/></Types>'


@pytest.mark.parametrize(
    ("data", "code", "detail"),
    [
        (b"", ErrorCode.EMPTY_FILE, None),
        (b"\x89PNG\r\n\x1a\n" + b"0" * 20, ErrorCode.UNSUPPORTED_TYPE, "image"),
        (b"\xff\xd8\xff\xe0" + b"0" * 20, ErrorCode.UNSUPPORTED_TYPE, "image"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 20, ErrorCode.UNSUPPORTED_TYPE, "legacy_doc"),
        (
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + "EncryptedPackage".encode("utf-16-le"),
            ErrorCode.ENCRYPTED,
            "office",
        ),
        (_zip({"a.txt": b"x"}), ErrorCode.UNSUPPORTED_TYPE, "zip"),
        (
            _zip({"[Content_Types].xml": _CT.format("spreadsheetml.sheet.main+xml").encode()}),
            ErrorCode.UNSUPPORTED_TYPE,
            "office_other",
        ),
        (b"PK\x03\x04 hong", ErrorCode.CORRUPT_FILE, "bad_zip"),
        (b"plain text", ErrorCode.UNSUPPORTED_TYPE, "other"),
    ],
)
def test_detect_kind_errors(data, code, detail):
    with pytest.raises(ExtractionError) as e:
        detect_kind(data)
    assert e.value.code == code and e.value.detail == detail


def test_detect_kind_ok_and_limits():
    assert detect_kind(b"rac\n%PDF-1.7\n...") == "pdf"  # vài byte rác trước header
    docx = _zip({"[Content_Types].xml": _CT.format("wordprocessingml.document.main+xml").encode()})
    assert detect_kind(docx) == "docx"
    with pytest.raises(ExtractionError) as e:
        detect_kind(b"%PDF-" + b"0" * 100, ExtractOptions(max_bytes=50))
    assert e.value.code == ErrorCode.TOO_LARGE


def test_zip_bomb_rejected():
    bomb = _zip(
        {
            "[Content_Types].xml": _CT.format("wordprocessingml.document.main+xml").encode(),
            "word/big.xml": b"0" * 3_000_000,
        }
    )
    with pytest.raises(ExtractionError) as e:
        detect_kind(bomb, ExtractOptions(max_unzipped_bytes=2_000_000))
    assert e.value.code == ErrorCode.TOO_LARGE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Kinh nghie\u0302\u0323m", "Kinh nghi\u1ec7m"),  # NFD → NFC
        ("Kinh nghi\u00ea \u0323m", "Kinh nghi\u1ec7m"),  # khoảng trắng trước dấu kết hợp
        ("Py\u200bthon\u00ad", "Python"),  # zero-width, soft hyphen
        ("\ufb01nance o\ufb03ce", "finance office"),  # ligature
        ("K I N H  N G H I Ệ M", "KINH NGHIỆM"),  # chữ giãn cách
        ("C C++ Go Java", "C C++ Go Java"),  # không gộp nhầm
        ("\uf0e0 hung@example.com", "hung@example.com"),  # icon font đầu dòng
        ("  Java  \t Spring  ", "Java Spring"),
    ],
)
def test_normalize_line(raw, expected):
    assert normalize_line(raw) == expected


def test_normalize_text_keeps_lines_and_one_blank():
    assert normalize_text("A\r\nB\n\n\n\nC\n") == "A\nB\n\nC"


VI = "Kinh nghiệm làm việc tại công ty phần mềm, phát triển hệ thống thanh toán bằng Java. " * 6


def test_quality_readable_vietnamese():
    q = measure(VI)
    assert q.readable and q.vi_diacritic_ratio > 0.5 and q.garbled_ratio == 0


def test_quality_flags_garbled_short_and_lost_diacritics():
    assert "garbled" in measure("(cid:12)(cid:34) " * 50 + VI).reasons
    assert "too_short" in measure("Java").reasons
    plain = "Kinh nghiem lam viec tai cong ty phan mem, ky nang lap trinh, hoc van dai hoc. " * 6
    assert "lost_diacritics" in measure(plain).reasons
    assert measure("Experienced data analyst with strong SQL skills. " * 10).readable
