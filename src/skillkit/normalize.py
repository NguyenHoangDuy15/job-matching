"""Chuẩn hóa văn bản trước khi so khớp kỹ năng."""

import unicodedata


def normalize_text(text: str) -> str:
    """NFC, chữ thường, gộp mọi khoảng trắng (cả xuống dòng, NBSP) thành một dấu cách."""
    return " ".join(unicodedata.normalize("NFC", text).lower().split())
