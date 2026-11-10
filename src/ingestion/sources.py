"""Cấu hình nguồn (config/sources.yaml) và tìm link tin từ trang danh sách."""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "sources.yaml"


@dataclass(frozen=True)
class SourceConfig:
    name: str  # = ops.sources.code
    source_id: int | None  # = ops.sources.id
    base_url: str
    allowed: bool
    rate_limit_s: float
    listing_url: str | None  # có {page}; None = chưa cấu hình crawl
    max_pages: int
    job_url_pattern: re.Pattern | None  # nhóm 1 = mã tin của nguồn


def load_sources(path: str | Path = DEFAULT_CONFIG) -> dict[str, SourceConfig]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    result = {}
    for item in data.get("sources", []):
        listing = item.get("listing") or {}
        pattern = item.get("job_url_pattern")
        result[item["name"]] = SourceConfig(
            name=item["name"],
            source_id=item.get("source_id"),
            base_url=item["base_url"].rstrip("/"),
            allowed=bool(item.get("allowed", False)),
            rate_limit_s=float(item.get("rate_limit_s", 5)),
            listing_url=listing.get("url"),
            max_pages=int(listing.get("max_pages", 1)),
            job_url_pattern=re.compile(pattern) if pattern else None,
        )
    return result


def _clean(url: str) -> str:
    """Bỏ query và fragment để một tin chỉ có một URL."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def extract_job_links(page_html: str, page_url: str, source: SourceConfig) -> dict[str, str]:
    """Tìm link tin trong HTML (cả thẻ <a> lẫn JSON nhúng trong trang).

    Trả {mã tin: URL tuyệt đối}, giữ thứ tự xuất hiện, không trùng.
    """
    if source.job_url_pattern is None:
        raise ValueError(f"{source.name}: chưa có job_url_pattern trong config")
    text = page_html.replace("\\/", "/").replace("\\u002F", "/")  # URL trong JSON nhúng
    host = urlsplit(source.base_url).netloc
    # Bắt cả tiền tố https://host nếu có, để loại link trỏ sang trang khác.
    pattern = re.compile(r"(?:https?://[A-Za-z0-9.-]+)?" + source.job_url_pattern.pattern)
    links: dict[str, str] = {}
    for match in pattern.finditer(text):
        url = _clean(urljoin(page_url, match.group(0)))
        if urlsplit(url).netloc != host:
            continue
        links.setdefault(match.group(1), url)
    return links


def job_id_from_url(url: str, source: SourceConfig) -> str | None:
    if source.job_url_pattern is None:
        return None
    match = source.job_url_pattern.search(url)
    return match.group(1) if match else None
