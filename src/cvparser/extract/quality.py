"""Chỉ số "văn bản đọc được" (S3-D01). Ngưỡng là ước lượng ban đầu, chỉnh sau S3-D06."""

import re
import unicodedata

from cvparser.extract.models import Quality

MIN_CHARS = 300
MAX_GARBLED = 0.01
MIN_LETTER_RATIO = 0.6
MIN_VI_DIACRITIC = 0.15
# Ký tự chỉ có trong tiếng Việt (sau NFC): nhận ra văn bản Việt còn dấu.
_VI_CHARS = set("ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵ")
# Từ Việt phổ biến khi đã mất dấu: nhiều từ này + ít từ có dấu → văn bản bị mất dấu.
_VI_PLAIN = {
    "kinh", "nghiem", "ky", "nang", "cong", "ty", "du", "an", "hoc", "van", "truong", "dai",
    "chuc", "danh", "thong", "tin", "lien", "he", "muc", "tieu", "phat", "trien", "quan", "ly",
}  # fmt: skip
_CID = re.compile(r"\(cid:\d+\)")
_WORD = re.compile(r"\w+", re.UNICODE)


def _is_garbled_char(c: str) -> bool:
    cat = unicodedata.category(c)
    return c == "�" or cat == "Co" or (cat == "Cc" and c not in "\n\t")


def measure(text: str) -> Quality:
    cid = _CID.findall(text)
    body = _CID.sub("", text)
    visible = [c for c in body if not c.isspace()]
    n = len(visible) + sum(len(x) for x in cid)
    letters = sum(c.isalpha() for c in visible)
    garbled = sum(_is_garbled_char(c) for c in visible) + sum(len(x) for x in cid)
    words = [w for w in _WORD.findall(body.lower()) if any(c.isalpha() for c in w)]
    vi_words = sum(any(c in _VI_CHARS for c in w) for w in words)
    plain_vi = sum(w in _VI_PLAIN for w in words)

    letter_ratio = letters / n if n else 0.0
    garbled_ratio = garbled / n if n else 0.0
    vi_ratio = vi_words / len(words) if words else 0.0

    reasons = []
    if n < MIN_CHARS:
        reasons.append("too_short")
    if garbled_ratio > MAX_GARBLED:
        reasons.append("garbled")
    if n and letter_ratio < MIN_LETTER_RATIO:
        reasons.append("low_letter_ratio")
    # Có nhiều từ Việt không dấu mà gần như không có từ có dấu → mất dấu (font lỗi, TCVN3...).
    if words and plain_vi >= 5 and plain_vi / len(words) > 0.05 and vi_ratio < MIN_VI_DIACRITIC:
        reasons.append("lost_diacritics")
    return Quality(
        char_count=n,
        word_count=len(words),
        letter_ratio=round(letter_ratio, 4),
        garbled_ratio=round(garbled_ratio, 4),
        vi_diacritic_ratio=round(vi_ratio, 4),
        readable=not reasons,
        reasons=reasons,
    )
