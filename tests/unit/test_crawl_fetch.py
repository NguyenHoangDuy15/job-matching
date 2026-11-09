"""S2-T03: tải trang lịch sự, tìm link tin, chạy cả luồng với HTTP giả (không ra mạng)."""

import re
from pathlib import Path

import httpx
import pytest

from ingestion.crawl import crawl_source
from ingestion.fetch import Blocked, NotAllowed, PoliteFetcher, RateLimiter
from ingestion.location import default_index
from ingestion.sources import SourceConfig, extract_job_links, load_sources
from ingestion.store import LocalStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "crawl"
ROOT = Path(__file__).resolve().parents[2]


def _cfg(name="itviec", base="https://itviec.com", pattern=r"/it-jobs/[a-z0-9-]*?-(\d+)(?![\w-])"):
    return SourceConfig(
        name=name,
        source_id=2,
        base_url=base,
        allowed=True,
        rate_limit_s=2,
        listing_url=f"{base}/it-jobs?page={{page}}",
        max_pages=5,
        job_url_pattern=re.compile(pattern),
    )


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _fetcher(handler, base="https://itviec.com"):
    clock = FakeClock()
    fetcher = PoliteFetcher(
        base,
        allowed=True,
        rate_limit_s=2,
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
        limiter=RateLimiter(2, clock=clock.clock, sleep=clock.sleep),
    )
    return fetcher, clock


def _robots_404(request):
    return httpx.Response(404) if request.url.path == "/robots.txt" else None


# ---- tìm link -------------------------------------------------------------------
def test_extract_itviec_links_dedup_strip_query_and_skip_category_pages():
    page = (FIXTURES / "itviec_listing.html").read_text(encoding="utf-8")
    links = extract_job_links(page, "https://itviec.com/it-jobs?page=1", _cfg())
    assert links == {
        "1234": "https://itviec.com/it-jobs/backend-developer-java-cong-ty-a-1234",
        "5678": "https://itviec.com/it-jobs/data-engineer-python-sql-cong-ty-b-5678",
        "9012": "https://itviec.com/it-jobs/qa-engineer-cong-ty-c-9012",
    }


def test_extract_vietnamworks_links_from_embedded_json():
    cfg = _cfg("vietnamworks", "https://www.vietnamworks.com", r"/[a-z0-9-]+-(\d+)-jv(?![\w-])")
    page = (FIXTURES / "vietnamworks_listing.html").read_text(encoding="utf-8")
    links = extract_job_links(page, "https://www.vietnamworks.com/viec-lam?page=1", cfg)
    assert links == {
        "1900001": "https://www.vietnamworks.com/senior-frontend-developer-1900001-jv",
        "1900002": "https://www.vietnamworks.com/devops-engineer-1900002-jv",
    }


def test_repo_config_patterns_and_gate():
    sources = load_sources(ROOT / "config" / "sources.yaml")
    assert sources["topcv"].listing_url is None  # TopCV không đi qua crawler S2-T03
    for name in ("itviec", "vietnamworks"):
        cfg = sources[name]
        assert cfg.rate_limit_s >= 2
        assert "{page}" in cfg.listing_url
        assert cfg.job_url_pattern.groups == 1


# ---- quyền, robots, chặn ------------------------------------------------------
def test_not_allowed_source_cannot_build_fetcher():
    with pytest.raises(NotAllowed):
        PoliteFetcher("https://www.topcv.vn", allowed=False, rate_limit_s=5)


def test_robots_404_allows_and_disallow_rule_blocks():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /it-jobs/secret\n")
        return httpx.Response(200, text="<html>ok</html>")

    fetcher, _ = _fetcher(handler)
    assert fetcher.get("https://itviec.com/it-jobs?page=1").status == 200
    with pytest.raises(NotAllowed):
        fetcher.get("https://itviec.com/it-jobs/secret-1")


def test_robots_5xx_means_disallow_all():
    fetcher, _ = _fetcher(lambda r: httpx.Response(503))
    assert fetcher.can_fetch("https://itviec.com/it-jobs") is False


def test_off_domain_url_rejected():
    fetcher, _ = _fetcher(lambda r: _robots_404(r) or httpx.Response(200, text="ok"))
    with pytest.raises(NotAllowed):
        fetcher.get("https://example.com/x")


@pytest.mark.parametrize("status", [403, 429])
def test_403_429_stop_source(status):
    fetcher, _ = _fetcher(lambda r: _robots_404(r) or httpx.Response(status))
    with pytest.raises(Blocked):
        fetcher.get("https://itviec.com/it-jobs")


def test_challenge_page_stops_source():
    body = "<html><title>Just a moment...</title><div class='cf-browser-verification'></div>"
    fetcher, _ = _fetcher(lambda r: _robots_404(r) or httpx.Response(200, text=body))
    with pytest.raises(Blocked):
        fetcher.get("https://itviec.com/it-jobs")


def test_5xx_retried_then_ok():
    calls = {"n": 0}

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, text="ok")

    fetcher, _ = _fetcher(handler)
    assert fetcher.get("https://itviec.com/it-jobs").status == 200
    assert calls["n"] == 2


def test_rate_limit_two_seconds_between_requests():
    fetcher, clock = _fetcher(lambda r: _robots_404(r) or httpx.Response(200, text="ok"))
    for _ in range(3):
        fetcher.get("https://itviec.com/it-jobs")
    # robots + 3 trang = 4 request → 3 lần chờ, mỗi lần đủ 2 giây
    assert clock.sleeps == [2, 2, 2]


def test_crawl_delay_in_robots_slows_down():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 10\n")
        return httpx.Response(200, text="ok")

    fetcher, _ = _fetcher(handler)
    fetcher.can_fetch("https://itviec.com/it-jobs")
    assert fetcher.limiter.interval == 10


# ---- cả luồng (HTTP giả + LocalStore) ---------------------------------------------
def test_crawl_source_end_to_end(tmp_path):
    listing = (FIXTURES / "itviec_listing.html").read_text(encoding="utf-8")
    job = (FIXTURES / "itviec_job.html").read_text(encoding="utf-8")

    def handler(request):
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(404)
        if path == "/it-jobs":
            page = request.url.params.get("page")
            return httpx.Response(200, text=listing if page == "1" else "<html></html>")
        if path.endswith("-9012"):
            return httpx.Response(404)  # tin đã gỡ
        return httpx.Response(200, text=job)

    fetcher, _ = _fetcher(handler)
    store = LocalStore(default_index(), out_dir=tmp_path / "out")
    stats, status = crawl_source(
        _cfg(), store, max_jobs=10, max_pages=5, fetcher=fetcher, html_root=tmp_path / "raw"
    )
    assert status == "success"
    assert stats.pages_fetched == 2  # trang 2 không còn tin mới → dừng
    assert stats.items_new == 2
    assert stats.skipped == {"gone": 1}
    assert len(list((tmp_path / "raw").rglob("*.html.gz"))) == 2
    lines = next((tmp_path / "out" / "itviec").glob("*.jsonl")).read_text(encoding="utf-8")
    assert lines.count("\n") == 2


def test_crawl_source_blocked_midway_is_partial(tmp_path):
    listing = (FIXTURES / "itviec_listing.html").read_text(encoding="utf-8")
    job = (FIXTURES / "itviec_job.html").read_text(encoding="utf-8")

    def handler(request):
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(404)
        if path == "/it-jobs":
            return httpx.Response(200, text=listing)
        if path.endswith("-1234"):
            return httpx.Response(200, text=job)
        return httpx.Response(429)

    fetcher, _ = _fetcher(handler)
    store = LocalStore(default_index(), out_dir=tmp_path / "out")
    stats, status = crawl_source(
        _cfg(), store, max_jobs=3, max_pages=1, fetcher=fetcher, html_root=tmp_path / "raw"
    )
    assert status == "partial"
    assert stats.items_new == 1
