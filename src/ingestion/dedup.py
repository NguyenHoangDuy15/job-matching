"""Khử trùng chính xác (S3-T03, US-14): nhận ra cùng một tin đăng ở nhiều nơi.

Một tin nguồn (source_id, source_job_id) được gắn vào tin chuẩn core.jobs theo thứ tự:
  1. Cùng (nguồn, mã tin)     → chính tin đó (đã có từ S2-T03)
  2. Cùng URL đã chuẩn hóa    → chính tin đó, chỉ khác mã tin (ví dụ nạp JSONL rồi crawl lại)
  3. Cùng dedup hash          → tin chuẩn đang mở có cùng chức danh + công ty + tỉnh + mô tả
Gần trùng (khác vài chữ) do S3-T04 xử lý bằng MinHash.

dedup hash KHÁC content_hash của từng nguồn (store.content_hash): content_hash dùng để biết
tin của một nguồn có đổi nội dung không; dedup hash so sánh giữa các nguồn nên bỏ hết phần
trình bày (dấu, chữ hoa, dấu câu, khoảng trắng) và các trường mỗi nơi ghi một kiểu
(lương, hạn nộp, loại hình).
"""

import hashlib
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

from ingestion.location import normalize_key

# Mô tả ngắn hơn ngưỡng này (sau chuẩn hóa) thì không dùng hash: chức danh + công ty + tỉnh
# giống nhau là chuyện thường (một công ty tuyển nhiều "Java Developer" ở Hà Nội).
MIN_DESCRIPTION_CHARS = 200

# Phiên bản cách tính: đổi cách chuẩn hóa thì tăng số này và chạy lại scripts/dedup_exact.py.
DEDUP_HASH_VERSION = "dedup-1"


def canonical_url(url: str) -> str:
    """URL tin đăng dạng chuẩn để so: https, host chữ thường bỏ www., bỏ query/fragment,
    bỏ dấu / thừa. Đường dẫn giữ nguyên chữ hoa/thường (một số web phân biệt)."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = "/".join(seg for seg in parts.path.split("/") if seg)
    return urlunsplit(("https", host, f"/{path}" if path else "", "", ""))


def normalize_description(text: str | None) -> str:
    """Mô tả để so giữa các nguồn: chữ thường, bỏ dấu, dấu câu/gạch đầu dòng thành khoảng trắng."""
    return normalize_key(text or "")


def dedup_hash(
    title: str,
    company_norm: str | None,
    province_codes: Iterable[int],
    description: str | None,
) -> bytes | None:
    """SHA-256 của (chức danh, công ty, tỉnh, mô tả) đã chuẩn hóa; None khi mô tả quá ngắn
    hoặc thiếu công ty (không đủ chắc để gộp)."""
    body = normalize_description(description)
    if len(body) < MIN_DESCRIPTION_CHARS or not company_norm:
        return None
    key = "\x1f".join(
        (
            DEDUP_HASH_VERSION,
            normalize_key(title),
            company_norm,
            ",".join(str(c) for c in sorted(set(province_codes))),
            body,
        )
    )
    return hashlib.sha256(key.encode()).digest()
