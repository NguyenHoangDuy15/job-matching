"""Tải trang lịch sự: kiểm tra quyền, robots.txt, giới hạn tốc độ, dừng khi bị chặn.

Quy tắc lấy từ docs/data_sources.md (TASK-U008):
- chỉ crawl nguồn có `allowed: true` trong config/sources.yaml (đã có đồng ý bằng văn bản);
- tuân theo robots.txt (RFC 9309: 4xx = được phép, 5xx/lỗi mạng = coi như cấm hết);
- gặp 403, 429 hoặc trang xác minh chống bot thì DỪNG, không tìm cách vượt.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "JobMatchBot/0.1 (+https://github.com/NguyenHoangDuy15/job-matching)"
ROBOTS_AGENT = "JobMatchBot"

# Dấu hiệu trang chống bot (Cloudflare, captcha...). Gặp là dừng nguồn đó.
_CHALLENGE_MARKERS = (
    "cf-browser-verification",
    "challenge-platform",
    "cf-chl-",
    "<title>just a moment",
    "g-recaptcha",
    "h-captcha",
    "captcha-delivery",
)
_RETRY_STATUS = {500, 502, 503, 504}


class CrawlError(RuntimeError):
    """Lỗi chung khi crawl."""


class NotAllowed(CrawlError):
    """Nguồn chưa được phép crawl, hoặc robots.txt cấm URL này."""


class Blocked(CrawlError):
    """Nguồn trả 403/429 hoặc trang chống bot: dừng cả nguồn."""


@dataclass
class Page:
    url: str  # URL cuối cùng sau khi theo redirect
    status: int
    text: str


class RateLimiter:
    """Bảo đảm hai request liên tiếp tới cùng nguồn cách nhau ít nhất `interval` giây."""

    def __init__(
        self,
        interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.interval = interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None:
            remaining = self.interval - (now - self._last)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last = now


def looks_like_challenge(text: str) -> bool:
    head = text[:20000].lower()
    return any(marker in head for marker in _CHALLENGE_MARKERS)


class PoliteFetcher:
    """httpx client cho MỘT nguồn: kiểm tra allowed + robots, giới hạn tốc độ, retry 5xx."""

    def __init__(
        self,
        base_url: str,
        *,
        allowed: bool,
        rate_limit_s: float,
        client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        max_retries: int = 2,
    ):
        if not allowed:
            raise NotAllowed(
                f"{base_url}: allowed=false trong config/sources.yaml. "
                "Chỉ bật khi đã có đồng ý bằng văn bản (docs/data_sources.md)."
            )
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "vi,en;q=0.8"},
            follow_redirects=True,
            timeout=20.0,
        )
        self.limiter = limiter or RateLimiter(rate_limit_s)
        self.max_retries = max_retries
        self.requests = 0
        self.http_errors = 0
        self._robots: RobotFileParser | None = None

    # ---- robots.txt -------------------------------------------------------
    def robots(self) -> RobotFileParser:
        if self._robots is not None:
            return self._robots
        parser = RobotFileParser()
        try:
            self.limiter.wait()
            self.requests += 1
            resp = self.client.get(f"{self.base_url}/robots.txt")
        except httpx.HTTPError:
            parser.disallow_all = True  # không đọc được → an toàn là không crawl
        else:
            if resp.status_code >= 500:
                parser.disallow_all = True
            elif resp.status_code >= 400:
                parser.allow_all = True  # RFC 9309 mục 2.3.1.3
            else:
                parser.parse(resp.text.splitlines())
        self._robots = parser
        delay = parser.crawl_delay(ROBOTS_AGENT)
        if delay and float(delay) > self.limiter.interval:
            self.limiter.interval = float(delay)
        return parser

    def can_fetch(self, url: str) -> bool:
        return self.robots().can_fetch(ROBOTS_AGENT, url)

    # ---- tải trang ----------------------------------------------------------
    def get(self, url: str) -> Page:
        if urlsplit(url).netloc != urlsplit(self.base_url).netloc:
            raise NotAllowed(f"URL ngoài nguồn: {url}")
        if not self.can_fetch(url):
            raise NotAllowed(f"robots.txt cấm: {url}")
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            self.requests += 1
            try:
                resp = self.client.get(url)
            except httpx.HTTPError as exc:
                last_error = exc
                self.http_errors += 1
                continue
            if resp.status_code in (403, 429):
                self.http_errors += 1
                raise Blocked(f"HTTP {resp.status_code} tại {url}: dừng nguồn, không thử vượt")
            if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                self.http_errors += 1
                self.limiter.interval *= 1.5  # máy chủ đang mệt: giãn nhịp
                continue
            if looks_like_challenge(resp.text):
                raise Blocked(f"Trang xác minh chống bot tại {url}: dừng nguồn")
            if resp.status_code >= 400:
                self.http_errors += 1
            return Page(url=str(resp.url), status=resp.status_code, text=resp.text)
        raise CrawlError(f"Không tải được {url}: {last_error}")

    def close(self) -> None:
        self.client.close()
