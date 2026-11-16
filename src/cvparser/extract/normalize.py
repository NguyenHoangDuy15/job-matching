"""Chuẩn hóa chữ trích từ PDF/DOCX: NFC, ký tự vô hình, ligature, icon, chữ giãn cách.

Giữ nguyên ranh giới dòng: S3-D02 tách section theo từng dòng.
"""

import re
import unicodedata

_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_SPACES = dict.fromkeys(map(ord, "      \t"), " ")
_LIGATURES = re.compile("[ﬀ-ﬆ]")
# Khoảng trắng đứng trước dấu kết hợp (dấu tiếng Việt bị tách khi trích PDF).
_SPACE_BEFORE_MARK = re.compile(r"[ ]+(?=[̀-ͯ])")
_PUA = re.compile("[-]")
_LEADING_ICON = re.compile(r"^(?:[-•●▪■‣⁃]\s*)+")
_BULLET = re.compile(r"^(?:[-–•●▪■◦*+]|\d{1,2}[.)])\s+")


def _join_letter_spaced(line: str) -> str:
    """'K I N H  N G H I Ệ M' → 'KINH NGHIỆM'. Không gộp 'C C++ Go' (có token dài hơn 1)."""
    words = re.split(r" {2,}", line.strip())
    tokens = [t for w in words for t in w.split(" ")]
    if len(tokens) < 4 or any(len(t) != 1 or not t.isalpha() for t in tokens):
        return line
    return " ".join(w.replace(" ", "") for w in words)


def normalize_line(line: str) -> str:
    line = line.translate(_INVISIBLE).translate(_SPACES)
    line = _LIGATURES.sub(lambda m: unicodedata.normalize("NFKC", m.group()), line)
    line = unicodedata.normalize("NFD", line)
    line = _SPACE_BEFORE_MARK.sub("", line)
    line = unicodedata.normalize("NFC", line)
    # Icon font (điện thoại, email) và chấm tròn đầu dòng: bỏ, không tính là chữ rác.
    line = _LEADING_ICON.sub("", line)
    line = _join_letter_spaced(line)
    return re.sub(r" {2,}", " ", line).strip()


def normalize_text(text: str) -> str:
    """Chuẩn hóa từng dòng, bỏ dòng trống thừa (tối đa một dòng trống liên tiếp)."""
    lines = [normalize_line(x) for x in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip("\n")


def is_bullet(line: str) -> bool:
    return bool(_BULLET.match(line))


def count_pua(text: str) -> int:
    return len(_PUA.findall(text))
