"""Crawler nguồn #1 VietnamWorks và #2 ITviec (S2-T03, US-03).

Luồng: trang danh sách → link tin → trang chi tiết → JSON-LD JobPosting → JobPostingRaw
→ raw.job_snapshots + core.jobs trên Supabase.

    uv run python scripts/crawl.py probe --source itviec
    uv run python scripts/crawl.py run --source itviec --max-jobs 150 --dry-run
    uv run python scripts/crawl.py run --source itviec --source vietnamworks --max-jobs 150
    uv run python scripts/crawl.py parse duong/dan/trang.html --source itviec
"""

import argparse
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from ingestion.fetch import Blocked, CrawlError, NotAllowed, PoliteFetcher
from ingestion.jsonld import find_job_posting, parse_job_posting
from ingestion.location import default_index
from ingestion.sources import SourceConfig, extract_job_links, job_id_from_url, load_sources
from ingestion.store import (
    LocalStore,
    PgStore,
    RunStats,
    build_job_row,
    html_key,
    save_html,
)

ROOT = Path(__file__).resolve().parents[2]


def _log(msg: str) -> None:
    print(msg, flush=True)


def discover(cfg: SourceConfig, fetcher: PoliteFetcher, max_jobs: int, max_pages: int, stats):
    """Đi qua trang danh sách cho tới khi đủ max_jobs hoặc trang không còn tin mới."""
    if not cfg.listing_url:
        raise CrawlError(f"{cfg.name}: chưa cấu hình listing.url trong config/sources.yaml")
    links: dict[str, str] = {}
    for page_no in range(1, max_pages + 1):
        page = fetcher.get(cfg.listing_url.format(page=page_no))
        stats.pages_fetched += 1
        found = extract_job_links(page.text, page.url, cfg)
        fresh = {k: v for k, v in found.items() if k not in links}
        _log(f"  danh sách trang {page_no}: {len(found)} link, {len(fresh)} mới")
        if not fresh:
            break
        links.update(fresh)
        if len(links) >= max_jobs:
            break
    return dict(list(links.items())[:max_jobs])


def fetch_posting(cfg: SourceConfig, fetcher: PoliteFetcher, job_id: str, url: str):
    """Tải và đọc một tin. Trả (posting, html) hoặc (None, lý do bỏ qua)."""
    page = fetcher.get(url)
    if page.status in (404, 410):
        return None, "gone"
    if page.status >= 400:
        return None, f"http_{page.status}"
    item = find_job_posting(page.text)
    if item is None:
        return None, "no_jsonld"
    posting = parse_job_posting(
        item,
        source=cfg.name,
        source_job_id=job_id,
        url=url,
        fetched_at=datetime.now(UTC),
        http_status=page.status,
    )
    if not posting.title:
        return None, "no_title"
    return posting, page.text


def crawl_source(
    cfg: SourceConfig,
    store,
    *,
    max_jobs: int,
    max_pages: int,
    run_type: str = "manual",
    fetcher: PoliteFetcher | None = None,
    html_root: Path | None = None,
):
    fetcher = fetcher or PoliteFetcher(
        cfg.base_url, allowed=cfg.allowed, rate_limit_s=cfg.rate_limit_s
    )
    stats = RunStats()
    run_id = store.start_run(cfg.name, cfg.source_id, run_type)
    status, error = "success", None
    try:
        links = discover(cfg, fetcher, max_jobs, max_pages, stats)
        _log(f"  → {len(links)} tin sẽ tải (≈ {len(links) * fetcher.limiter.interval:.0f} giây)")
        for i, (job_id, url) in enumerate(links.items(), start=1):
            try:
                posting, extra = fetch_posting(cfg, fetcher, job_id, url)
            except NotAllowed:
                stats.skip("robots")
                continue
            if posting is None:
                stats.skip(extra)
                if error is None:
                    error = f"{extra}: {url}"
                _log(f"  [{i}/{len(links)}] bỏ qua ({extra}) {url}")
                continue
            key = html_key(posting)
            save_html(key, extra, html_root) if html_root else save_html(key, extra)
            result = store.save(posting, key, run_id)
            stats.count(result)
            _log(f"  [{i}/{len(links)}] {result:9} {posting.title} — {posting.company_name}")
        skipped = sum(stats.skipped.values())
        if not stats.items_seen:
            status = "failed"
        elif skipped > max(2, 0.2 * len(links)):  # vài tin 404 là bình thường
            status = "partial"
    except Blocked as exc:
        status, error = ("partial" if stats.items_seen else "failed"), str(exc)
        _log(f"  DỪNG: {exc}")
    except Exception as exc:
        status, error = "failed", repr(exc)
        raise
    finally:
        stats.http_errors = fetcher.http_errors
        store.finish_run(run_id, stats, status, error)
        fetcher.close()
    _log(
        f"  KẾT QUẢ {cfg.name}: {status} · mới {stats.items_new} · cập nhật {stats.items_updated}"
        f" · đã đọc {stats.items_seen} · bỏ qua {stats.skipped or 0} · request {fetcher.requests}"
    )
    return stats, status


# ---- CLI -------------------------------------------------------------------------
def _database_url() -> str | None:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def cmd_probe(cfg: SourceConfig) -> int:
    """Kiểm tra nhanh 1 nguồn bằng ~4 request: robots, 1 trang danh sách, 1 trang tin."""
    try:
        fetcher = PoliteFetcher(cfg.base_url, allowed=cfg.allowed, rate_limit_s=cfg.rate_limit_s)
    except NotAllowed as exc:
        _log(f"  ✗ {exc}")
        return 1
    if not cfg.listing_url:
        _log(f"  ✗ {cfg.name}: chưa cấu hình listing.url")
        return 1
    try:
        listing = cfg.listing_url.format(page=1)
        _log(f"[{cfg.name}] robots.txt cho phép trang danh sách: {fetcher.can_fetch(listing)}")
        page = fetcher.get(listing)
        links = extract_job_links(page.text, page.url, cfg)
        _log(f"[{cfg.name}] {listing} → HTTP {page.status}, tìm thấy {len(links)} link tin")
        for url in list(links.values())[:3]:
            _log(f"    {url}")
        if not links:
            _log("  ✗ Không thấy link tin: sửa listing.url hoặc job_url_pattern trong config.")
            return 1
        job_id, url = next(iter(links.items()))
        posting, extra = fetch_posting(cfg, fetcher, job_id, url)
        if posting is None:
            _log(f"  ✗ Trang tin không đọc được ({extra}): {url}")
            return 1
        row = build_job_row(posting, default_index(), {}, posting.fetched_at.date())
        _log(f"  ✓ JSON-LD JobPosting: {posting.title} — {posting.company_name}")
        _log(f"    địa điểm: {posting.location_text()!r} → tỉnh {row.province_codes}")
        _log(f"    lương: {posting.salary_text()!r} → {row.columns['salary_status']}")
        _log(f"    đăng {posting.date_posted} · hạn {posting.valid_through}")
        _log(f"    mô tả: {len(posting.description_text)} ký tự")
        return 0
    except CrawlError as exc:
        _log(f"  ✗ {exc}")
        return 1
    finally:
        fetcher.close()


def cmd_parse(path: Path, cfg: SourceConfig) -> int:
    """Đọc 1 file HTML đã lưu (không cần mạng): xem JSON-LD đọc ra gì."""
    page = path.read_text(encoding="utf-8", errors="replace")
    item = find_job_posting(page)
    if item is None:
        _log("Không thấy JSON-LD JobPosting trong file.")
        return 1
    url = item.get("url") or str(path)
    job_id = job_id_from_url(url, cfg) or path.stem
    posting = parse_job_posting(
        item, source=cfg.name, source_job_id=job_id, url=url, fetched_at=datetime.now(UTC)
    )
    row = build_job_row(posting, default_index(), {}, posting.fetched_at.date())
    _log(posting.model_dump_json(indent=2, exclude={"json_ld", "description_html"}))
    _log(f"tỉnh: {row.province_codes} · work_mode: {row.columns['work_mode']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=str(ROOT / "config" / "sources.yaml"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_probe = sub.add_parser("probe", help="kiểm tra nhanh cấu hình 1 nguồn (~4 request)")
    p_probe.add_argument("--source", required=True)

    p_run = sub.add_parser("run", help="crawl và ghi DB")
    p_run.add_argument("--source", action="append", required=True)
    p_run.add_argument("--max-jobs", type=int, default=150)
    p_run.add_argument("--max-pages", type=int, help="ghi đè listing.max_pages")
    p_run.add_argument("--dry-run", action="store_true", help="không ghi DB, ghi data/raw/crawl")
    p_run.add_argument("--run-type", default="manual", choices=["manual", "daily", "backfill"])
    p_run.add_argument(
        "--skip-fx", action="store_true", help="không cập nhật tỷ giá trước khi crawl"
    )

    p_parse = sub.add_parser("parse", help="đọc 1 file HTML đã lưu, không cần mạng")
    p_parse.add_argument("path", type=Path)
    p_parse.add_argument("--source", required=True)

    args = parser.parse_args(argv)
    sources = load_sources(args.config)
    names = args.source if isinstance(args.source, list) else [args.source]
    unknown = [n for n in names if n not in sources]
    if unknown:
        parser.error(f"không có nguồn {unknown} trong {args.config}")

    if args.cmd == "probe":
        return cmd_probe(sources[args.source])
    if args.cmd == "parse":
        return cmd_parse(args.path, sources[args.source])

    if args.dry_run:
        store = LocalStore(default_index())
    else:
        dsn = _database_url()
        if not dsn:
            parser.error("thiếu DATABASE_URL (biến môi trường hoặc file .env); hoặc dùng --dry-run")
        store = PgStore(dsn)
        if not store.salary_v2:
            _log("! DB chưa chạy 0002_fx_rates.sql: chỉ ghi các cột lương của schema v2.0.")
        elif not args.skip_fx:
            fx = store.sync_fx(date.today())  # ① tỷ giá trước, ② crawl sau (S2-D02)
            usd = store.fx_rates.get("USD")
            _log(
                f"tỷ giá USD {usd.rate_vnd:,.0f} ({usd.source}, {usd.rate_date}); "
                f"tính lại lương {fx.jobs_refreshed} tin ngoại tệ"
                if usd
                else "! chưa có tỷ giá USD: tin ngoại tệ chưa có lương VND"
            )
            for warning in fx.update.warnings:
                _log(f"! {warning}")
    exit_code = 0
    try:
        for name in names:
            cfg = sources[name]
            _log(f"== {name} ({cfg.base_url}) ==")
            try:
                _, status = crawl_source(
                    cfg,
                    store,
                    max_jobs=args.max_jobs,
                    max_pages=args.max_pages or cfg.max_pages,
                    run_type=args.run_type,
                )
            except NotAllowed as exc:
                _log(f"  ✗ {exc}")
                status = "failed"
            if status == "failed":
                exit_code = 1
    finally:
        store.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
