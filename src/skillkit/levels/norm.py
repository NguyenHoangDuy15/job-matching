"""Chuẩn hóa để so cue: bỏ dấu, chữ thường, GIỮ NGUYÊN độ dài chuỗi.

Giữ độ dài để vị trí kỹ năng (từ SkillMatcher) dùng được trên bản đã chuẩn hóa.
Chỉ dùng để so cue; dò kỹ năng luôn giữ dấu ("Gò Vấp" không phải "Go").
"""

import unicodedata


def _fold_char(ch: str) -> str:
    base = unicodedata.normalize("NFD", ch)[0]
    if base in "đĐ":
        return "d"
    low = base.lower()
    return low if len(low) == 1 else base


def norm(text: str) -> str:
    """NFC → bỏ dấu từng ký tự (đ → d) → chữ thường; len(norm(s)) == len(NFC(s))."""
    return "".join(_fold_char(ch) for ch in unicodedata.normalize("NFC", text))
