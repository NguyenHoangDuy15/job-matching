"""TopCV job ingestion (Nodriver + BeautifulSoup + SQLite).

Updated: JSON-stringified DOM readiness and safe recovery after browser read errors.

Standalone for C:\\FU\\job-matching\\src\\ingestion\\topcv.py.

Modes:
  python src/ingestion/topcv.py --pages 1 --limit 10
  python src/ingestion/topcv.py --details-only --limit 10
  python src/ingestion/topcv.py --pages 1 --no-details
  python src/ingestion/topcv.py --import-html saved.html --job-url https://www.topcv.vn/viec-lam/example/123.html

Online mode requires `config/sources.yaml` to explicitly set `topcv.allowed: true`.
Only use automation when you have permission. Stop on HTTP 401/403/429 and
anti-bot challenges; this file does not solve or bypass challenges.

Dependencies: pip install nodriver beautifulsoup4 lxml PyYAML
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import shutil
import sqlite3
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

BASE = "https://www.topcv.vn"
SEARCH_URL = BASE + "/tim-viec-lam-cong-nghe-thong-tin-cr257?page={page}"
DEFAULT_DB = "data/state/topcv_jobs.db"
DEFAULT_OUT = "data/raw/topcv_nodriver.jsonl"  # NEVER overwrite old topcv.jsonl by default.
DEFAULT_SEEN = "data/state/topcv_seen_nodriver.json"
MAIN_FIELDS = ("job_description", "requirements", "benefits")
SOURCE_NAME = "topcv"
MIN_JD_LENGTH = 80
# Popup thanh toán MoMo/QR có sẵn trong HTML của mọi trang TopCV và có heading
# "Quyền lợi ứng viên"; không được để nó lọt vào JD (lỗi 105 tin, 11/2026).
NON_CONTENT_SELECTORS = (
    "script, style, noscript, template, header, footer, nav, "
    ".modal, [role='dialog'], [aria-modal='true'], [class*='modal'], [id*='modal']"
)
PAYMENT_POPUP_MARKERS = (
    "mã qr đã hết hạn",
    "số tiền thanh toán",
    "thanh toán bằng ví điện tử momo",
    "giá trị đơn hàng đã bao gồm vat",
)
MAX_ATTEMPTS = 3
QUEUE_STATES = (
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "RETRY_PENDING",
    "INVALID_DATA",
    "FAILED",
    "BLOCKED",
    "NOT_FOUND",
)


class AccessRestricted(RuntimeError):
    """The origin refused automatic access. No retries are performed."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        url: str = "",
        retry_after_raw: str | None = None,
        retry_after_at: str | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.url = url
        self.retry_after_raw = retry_after_raw
        self.retry_after_at = retry_after_at


class RateLimited(AccessRestricted):
    """HTTP 429 from the main document. The whole source run must stop."""


class PageNotFound(RuntimeError):
    pass


class BrowserReadError(RuntimeError):
    """Unexpected response from Nodriver/CDP (not an HTTP access denial)."""


class InvalidJobData(ValueError):
    """A fetched/imported page is not a sufficiently complete job description."""


class ExportSafetyError(RuntimeError):
    """Replacing JSONL would unexpectedly discard already exported records."""


def stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_retry_after(value: str | None, now: datetime | None = None) -> str | None:
    """Return Retry-After as a UTC timestamp for either seconds or HTTP-date."""
    raw = str(value or "").strip()
    if not raw:
        return None
    current = now or datetime.now(UTC)
    try:
        seconds = int(raw)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat(timespec="seconds")
    if seconds < 0:
        return None
    return (current + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def backup_file(path: Path, backup_dir: Path | None = None) -> Path | None:
    """Create a timestamped, non-destructive backup before changing durable data."""
    if not path.is_file():
        return None
    destination_dir = backup_dir or path.parent / "backups"
    destination_dir.mkdir(parents=True, exist_ok=True)
    token = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = destination_dir / f"{path.name}.{token}.bak"
    suffix = 1
    while target.exists():
        target = destination_dir / f"{path.name}.{token}.{suffix}.bak"
        suffix += 1
    shutil.copy2(path, target)
    return target


def cleaned(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"&(?:#?40);?(?!\d)", "(", text)
    text = re.sub(r"&(?:#?41);?(?!\d)", ")", text)
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\r", "")
    text = re.sub(r"\n\s*([,;])", r"\1", text)
    lines = [re.sub(r"[\t ]+", " ", s).strip() for s in text.splitlines()]
    return "\n".join(s for s in lines if s)


def text_from_html(value: Any) -> str:
    if isinstance(value, list):
        return cleaned("\n".join(text_from_html(x) for x in value))
    if isinstance(value, dict):
        return text_from_html(value.get("value") or value.get("name") or "")
    if isinstance(value, str):
        return cleaned(BeautifulSoup(value, "lxml").get_text("\n", strip=True))
    return ""


def normalize_url(url: str) -> str:
    absolute = urljoin(BASE, str(url or "")).split("#", 1)[0].split("?", 1)[0]
    parsed = urlparse(absolute)
    if parsed.scheme != "https" or parsed.hostname not in ("topcv.vn", "www.topcv.vn"):
        raise ValueError("Đường dẫn phải thuộc HTTPS TopCV")
    if not parsed.path.startswith("/viec-lam/") or not re.search(r"/\d+\.html$", parsed.path):
        raise ValueError("Đường dẫn phải là URL JD /viec-lam/.../<job_id>.html")
    return absolute


def job_id_from_url(url: str) -> str:
    result = re.search(r"/(\d+)\.html$", urlparse(url).path)
    if not result:
        raise ValueError("Không xác định được job_id từ URL")
    return result.group(1)


def redirected_off_job(final_url: str) -> bool:
    """True khi trình duyệt đang ở một trang TopCV không phải trang JD (vd. /viec-lam).

    about:blank hoặc URL JD khác (trang cũ chưa kịp thay) không tính là bị gỡ.
    """
    if urlparse(final_url).hostname not in ("topcv.vn", "www.topcv.vn"):
        return False
    try:
        normalize_url(final_url)
    except ValueError:
        return True
    return False


def parse_cards(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.job-item-search-result") or soup.select(
        "div.job-item-default, div[data-job-id]"
    )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for card in cards:
        a = card.select_one("h3.title a[href]") or card.select_one("a[href*='/viec-lam/']")
        if not a:
            continue
        try:
            url = normalize_url(a.get("href", ""))
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)

        def pick(selector: str, current_card=card) -> str:
            tag = current_card.select_one(selector)
            return cleaned(tag.get_text(" ", strip=True)) if tag else ""

        rows.append(
            {
                "job_id": job_id_from_url(url),
                "url": url,
                "title": cleaned(a.get_text(" ", strip=True)),
                "company_name": pick("a.company"),
                "salary_preview": pick("label.salary, label.title-salary"),
                "location_preview": pick("a.address, span.city-text"),
                "experience_preview": pick("label.exp"),
                "posted_at": pick("label.label-update"),
            }
        )
    return rows


def find_job_posting(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (TypeError, ValueError):
            continue
        candidates = data if isinstance(data, list) else [data]
        while candidates:
            obj = candidates.pop(0)
            if not isinstance(obj, dict):
                continue
            kind = obj.get("@type", [])
            if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                return obj
            graph = obj.get("@graph", [])
            candidates.extend(graph if isinstance(graph, list) else [graph])
    return {}


def split_headings(content: str) -> dict[str, str]:
    """Extract common TopCV headings when structured HTML containers are missing."""
    names = {
        "mô tả công việc": "job_description",
        "yêu cầu ứng viên": "requirements",
        "yêu cầu công việc": "requirements",
        "quyền lợi ứng viên": "benefits",
        "quyền lợi": "benefits",
    }
    breaks = {
        "cách thức ứng tuyển",
        "thông tin chung",
        "việc làm liên quan",
        "về công ty",
        "địa điểm và thời gian",
    }
    current = None
    values: dict[str, list[str]] = {x: [] for x in MAIN_FIELDS}
    active = False
    for line in cleaned(content).splitlines():
        key = line.lower().strip().rstrip(":：-– ")
        if key in names:
            current = names[key]
            active = True
            continue
        if key in breaks and active:
            break
        if current:
            values[current].append(line)
    return {k: cleaned("\n".join(v)) for k, v in values.items()}


def parse_jd_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    posting = find_job_posting(soup)
    org = posting.get("hiringOrganization") or {}
    if not isinstance(org, dict):
        org = {}
    loc = posting.get("jobLocation") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = loc.get("address") or {} if isinstance(loc, dict) else {}
    if not isinstance(addr, dict):
        addr = {}
    location = ", ".join(
        str(v).strip() for v in (addr.get("addressLocality"), addr.get("addressRegion")) if v
    )

    desc_jsonld = text_from_html(posting.get("description"))
    json_sections = split_headings(desc_jsonld)
    result: dict[str, Any] = {
        "title": cleaned(posting.get("title")),
        "company_name": cleaned(org.get("name")),
        "salary": "",
        "experience": "",
        "job_level": "",
        "employment_type": posting.get("employmentType") or "",
        "location": location,
        "date_posted": posting.get("datePosted") or "",
        "valid_through": posting.get("validThrough") or "",
        "job_description": json_sections["job_description"],
        "requirements": json_sections["requirements"]
        or text_from_html(posting.get("qualifications")),
        "benefits": json_sections["benefits"] or text_from_html(posting.get("jobBenefits")),
        "skills": [],
        "raw_json_ld": json.dumps(posting, ensure_ascii=False),
    }

    if not any(result[k] for k in MAIN_FIELDS) and desc_jsonld:
        result["job_description"] = desc_jsonld

    # JSON-LD is authoritative; well-scoped DOM sections only fill missing fields.
    for item in soup.select("div.job-description__item"):
        header = item.find(["h2", "h3", "h4"])
        content = item.select_one("div.job-description__item--content")
        if not header or not content:
            continue
        key = cleaned(header.get_text(" ", strip=True)).lower()
        body = cleaned(content.get_text("\n", strip=True))
        if "mô tả" in key and not result["job_description"]:
            result["job_description"] = body
        elif "yêu cầu" in key and not result["requirements"]:
            result["requirements"] = body
        elif ("quyền lợi" in key or "chế độ" in key) and not result["benefits"]:
            result["benefits"] = body

    # If the only available source is ordinary HTML, try exact heading boundaries.
    if not any(result[k] for k in MAIN_FIELDS):
        for tag in soup.select(NON_CONTENT_SELECTORS):
            tag.decompose()
        scopes = soup.select("#job-description, .job-description, main, article")
        scopes = scopes or ([soup.body] if soup.body else [])
        for scope in scopes:
            parts = split_headings(scope.get_text("\n", strip=True))
            if sum(bool(parts[k]) for k in MAIN_FIELDS) > sum(bool(result[k]) for k in MAIN_FIELDS):
                result.update(parts)

    for box in soup.select("div.job-detail__info--section, div.box-general-group-info"):
        heading = box.select_one(
            "div.job-detail__info--section-content-title, div.box-general-group-info-title"
        )
        value = box.select_one(
            "div.job-detail__info--section-content-value, div.box-general-group-info-value"
        )
        if not heading or not value:
            continue
        key = cleaned(heading.get_text(" ", strip=True)).lower()
        body = cleaned(value.get_text(" ", strip=True))
        if "mức lương" in key or "thu nhập" in key:
            result["salary"] = body
        elif "kinh nghiệm" in key:
            result["experience"] = body
        elif "cấp bậc" in key:
            result["job_level"] = body

    skills = [
        cleaned(tag.get_text(" ", strip=True))
        for tag in soup.select("div.box-category-tags a, a.item-tag, div.skill-tag a")
    ]
    result["skills"] = list(dict.fromkeys(s for s in skills if s))
    return result


def looks_like_payment_popup(text: str) -> bool:
    lowered = text.lower()
    return sum(marker in lowered for marker in PAYMENT_POPUP_MARKERS) >= 2


def is_valid_jd(parsed: dict[str, Any], min_length: int = MIN_JD_LENGTH) -> bool:
    total = "\n".join(str(parsed.get(k) or "") for k in MAIN_FIELDS).strip()
    if len(total) < min_length:  # Do NOT record an empty/challenge page as completed.
        return False
    # Chỉ có "quyền lợi" (thường là popup/menu) thì không phải JD.
    if not (cleaned(parsed.get("job_description")) or cleaned(parsed.get("requirements"))):
        return False
    return not looks_like_payment_popup(total)


def page_is_challenge(html: str) -> bool:
    soup = BeautifulSoup(html[:30000], "lxml")
    title = cleaned(soup.title.get_text() if soup.title else "").lower()
    if any(
        term in title
        for term in ("just a moment", "attention required", "access denied", "403 forbidden")
    ):
        return True
    return bool(soup.select("#challenge-form, #cf-challenge-running, .cf-browser-verification"))


def initialize_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS job_queue (
        job_id TEXT PRIMARY KEY,
        url TEXT NOT NULL,
        title TEXT,
        company_name TEXT,
        salary_preview TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING',
        discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS job_details (
        job_id TEXT PRIMARY KEY,
        title TEXT,
        company_name TEXT,
        salary TEXT,
        experience TEXT,
        job_level TEXT,
        employment_type TEXT,
        location TEXT,
        date_posted TEXT,
        valid_through TEXT,
        description_text TEXT,
        requirements_text TEXT,
        benefits_text TEXT,
        skills_json TEXT,
        raw_json_ld TEXT,
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        synced_to_pg INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS source_state (
        source TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'READY',
        last_http_status INTEGER,
        blocked_url TEXT,
        blocked_at TEXT,
        retry_after_raw TEXT,
        retry_after_at TEXT,
        last_error TEXT,
        updated_at TEXT
    )""")
    # Idempotent migrations for databases created by earlier crawler versions.
    existing_queue = {row[1] for row in conn.execute("PRAGMA table_info(job_queue)")}
    for column, sql_type in {
        "location_preview": "TEXT",
        "experience_preview": "TEXT",
        "posted_at": "TEXT",
        "last_error": "TEXT",
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "last_error_kind": "TEXT",
        "last_http_status": "INTEGER",
        "last_attempt_at": "TEXT",
        "updated_at": "TEXT",
    }.items():
        if column not in existing_queue:
            conn.execute(f"ALTER TABLE job_queue ADD COLUMN {column} {sql_type}")
    existing_details = {row[1] for row in conn.execute("PRAGMA table_info(job_details)")}
    if "synced_to_pg" not in existing_details:
        conn.execute("ALTER TABLE job_details ADD COLUMN synced_to_pg INTEGER DEFAULT 0")
    conn.commit()
    return conn


def recover_processing(conn: sqlite3.Connection) -> int:
    """Move jobs interrupted by a process crash to a bounded retry queue."""
    with conn:
        cursor = conn.execute(
            """UPDATE job_queue
            SET status='RETRY_PENDING',
                last_error_kind='CRASH_RECOVERY',
                last_error='Khôi phục sau khi tiến trình dừng lúc đang xử lý',
                updated_at=?
            WHERE status='PROCESSING'
              AND NOT EXISTS (
                  SELECT 1 FROM job_details d WHERE d.job_id=job_queue.job_id
              )""",
            (stamp(),),
        )
    return cursor.rowcount


def get_source_state(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_state WHERE source=?", (SOURCE_NAME,)).fetchone()


def migrate_legacy_source_block(conn: sqlite3.Connection) -> int:
    """Backfill a source lock only from explicit historical HTTP 403/429 evidence."""
    if get_source_state(conn) is not None:
        return 0
    row = conn.execute(
        """SELECT url,last_error,last_http_status,updated_at
           FROM job_queue
           WHERE status='BLOCKED'
             AND (last_http_status IN (403,429)
                  OR last_error LIKE '%HTTP 403%'
                  OR last_error LIKE '%HTTP 429%')
           ORDER BY COALESCE(updated_at,discovered_at) DESC LIMIT 1"""
    ).fetchone()
    if row is None:
        return 0
    status = row["last_http_status"]
    if status not in (403, 429):
        status = 429 if "HTTP 429" in (row["last_error"] or "") else 403
    when = row["updated_at"] or stamp()
    with conn:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO source_state (
                source,status,last_http_status,blocked_url,blocked_at,last_error,updated_at
            ) VALUES (?,?,?,?,?,?,?)""",
            (
                SOURCE_NAME,
                "BLOCKED",
                status,
                row["url"],
                when,
                row["last_error"],
                when,
            ),
        )
    return cursor.rowcount


def record_source_block(conn: sqlite3.Connection, exc: AccessRestricted) -> None:
    when = stamp()
    with conn:
        conn.execute(
            """INSERT INTO source_state (
            source,status,last_http_status,blocked_url,blocked_at,retry_after_raw,
            retry_after_at,last_error,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(source) DO UPDATE SET
            status=excluded.status,
            last_http_status=excluded.last_http_status,
            blocked_url=excluded.blocked_url,
            blocked_at=excluded.blocked_at,
            retry_after_raw=excluded.retry_after_raw,
            retry_after_at=excluded.retry_after_at,
            last_error=excluded.last_error,
            updated_at=excluded.updated_at""",
            (
                SOURCE_NAME,
                "BLOCKED",
                exc.status,
                exc.url,
                when,
                exc.retry_after_raw,
                exc.retry_after_at,
                str(exc)[:500],
                when,
            ),
        )


def clear_source_block(conn: sqlite3.Connection) -> int:
    """Explicit administrative action; a blocked source is never reopened automatically."""
    with conn:
        cursor = conn.execute(
            """UPDATE source_state SET
            status='READY', last_error=NULL, updated_at=?
            WHERE source=? AND status='BLOCKED'""",
            (stamp(), SOURCE_NAME),
        )
    return cursor.rowcount


def store_listing(conn: sqlite3.Connection, jobs: list[dict[str, str]]) -> int:
    new_count = 0
    for job in jobs:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO job_queue
            (job_id, url, title, company_name, salary_preview,
             location_preview, experience_preview, posted_at)
            VALUES (:job_id, :url, :title, :company_name, :salary_preview,
                    :location_preview, :experience_preview, :posted_at)""",
            job,
        )
        new_count += cursor.rowcount
        # Preserve existing status and JD. Update metadata for existing rows only if nonempty.
        if cursor.rowcount == 0:
            conn.execute(
                """UPDATE job_queue SET
                title=COALESCE(NULLIF(:title,''),title),
                company_name=COALESCE(NULLIF(:company_name,''),company_name),
                salary_preview=COALESCE(NULLIF(:salary_preview,''),salary_preview),
                location_preview=COALESCE(NULLIF(:location_preview,''),location_preview),
                experience_preview=COALESCE(NULLIF(:experience_preview,''),experience_preview),
                posted_at=COALESCE(NULLIF(:posted_at,''),posted_at)
                WHERE job_id=:job_id""",
                job,
            )
    conn.commit()
    return new_count


def set_status(
    conn: sqlite3.Connection,
    job_id: str,
    status: str,
    reason: str = "",
    *,
    error_kind: str | None = None,
    http_status: int | None = None,
) -> None:
    if status not in QUEUE_STATES:
        raise ValueError(f"Trạng thái hàng đợi không hợp lệ: {status}")
    with conn:
        conn.execute(
            """UPDATE job_queue SET
            status=?, last_error=?, last_error_kind=?, last_http_status=?, updated_at=?
            WHERE job_id=?""",
            (status, reason or None, error_kind, http_status, stamp(), job_id),
        )


def mark_processing(conn: sqlite3.Connection, job_id: str) -> bool:
    """Atomically claim one eligible job and count the session attempt."""
    with conn:
        cursor = conn.execute(
            """UPDATE job_queue SET
            status='PROCESSING', attempt_count=attempt_count+1,
            last_attempt_at=?, last_error=NULL, last_error_kind=NULL,
            last_http_status=NULL, updated_at=?
            WHERE job_id=? AND status IN ('PENDING','RETRY_PENDING')
              AND attempt_count < ?""",
            (stamp(), stamp(), job_id, MAX_ATTEMPTS),
        )
    return cursor.rowcount == 1


def reset_dom_failures(conn: sqlite3.Connection) -> int:
    """Requeue only jobs failed by the previous DOM-state regression.

    No completed rows, blocked rows, or other failed jobs are changed. Exclude
    rows that already have a saved JD as a further data-protection safeguard.
    """
    cursor = conn.execute(
        """UPDATE job_queue
        SET status='PENDING', last_error=NULL, last_error_kind=NULL,
            last_http_status=NULL, updated_at=?
        WHERE status='FAILED'
          AND last_error LIKE '%Không đọc được trạng thái DOM của trình duyệt%'
          AND NOT EXISTS (
              SELECT 1 FROM job_details d WHERE d.job_id=job_queue.job_id
          )""",
        (stamp(),),
    )
    conn.commit()
    return cursor.rowcount


def save_job_detail(
    conn: sqlite3.Connection, job_id: str, parsed: dict[str, Any], min_length: int = MIN_JD_LENGTH
) -> None:
    if not is_valid_jd(parsed, min_length):
        raise InvalidJobData(f"JD trống hoặc ngắn hơn {min_length} ký tự; không đánh dấu COMPLETED")
    listing = conn.execute("SELECT * FROM job_queue WHERE job_id=?", (job_id,)).fetchone()
    if listing is None:
        raise ValueError(f"Không tìm thấy job_id={job_id} trong job_queue")
    try:
        normalized_listing_url = normalize_url(listing["url"])
    except ValueError as exc:
        raise InvalidJobData(f"URL JD không hợp lệ: {listing['url']}") from exc
    if job_id_from_url(normalized_listing_url) != str(job_id):
        raise InvalidJobData("job_id không khớp URL JD")
    resolved_title = cleaned(parsed.get("title") or listing["title"])
    if not resolved_title:
        raise InvalidJobData("JD thiếu title")
    row = {
        "job_id": job_id,
        "title": resolved_title,
        "company_name": parsed.get("company_name") or listing["company_name"],
        "salary": parsed.get("salary") or listing["salary_preview"],
        "experience": parsed.get("experience") or listing["experience_preview"],
        "job_level": parsed.get("job_level"),
        "employment_type": parsed.get("employment_type"),
        "location": parsed.get("location") or listing["location_preview"],
        "date_posted": parsed.get("date_posted"),
        "valid_through": parsed.get("valid_through"),
        "description_text": parsed.get("job_description", ""),
        "requirements_text": parsed.get("requirements", ""),
        "benefits_text": parsed.get("benefits", ""),
        "skills_json": json.dumps(parsed.get("skills", []), ensure_ascii=False),
        "raw_json_ld": parsed.get("raw_json_ld") or "{}",
    }
    missing = [field for field in ("requirements", "benefits") if not cleaned(parsed.get(field))]
    quality_note = f"Thiếu phần: {', '.join(missing)}" if missing else None
    # Both writes form one transaction. The conflict update intentionally omits
    # synced_to_pg so a downstream-sync marker survives a re-crawl/import.
    with conn:
        conn.execute(
            """INSERT INTO job_details (
            job_id,title,company_name,salary,experience,job_level,employment_type,location,
            date_posted,valid_through,description_text,requirements_text,benefits_text,
            skills_json,raw_json_ld,synced_to_pg)
            VALUES (:job_id,:title,:company_name,:salary,:experience,:job_level,:employment_type,
            :location,:date_posted,:valid_through,:description_text,:requirements_text,
            :benefits_text,:skills_json,:raw_json_ld,0)
            ON CONFLICT(job_id) DO UPDATE SET
            title=excluded.title,company_name=excluded.company_name,salary=excluded.salary,
            experience=excluded.experience,job_level=excluded.job_level,
            employment_type=excluded.employment_type,location=excluded.location,
            date_posted=excluded.date_posted,valid_through=excluded.valid_through,
            description_text=excluded.description_text,requirements_text=excluded.requirements_text,
            benefits_text=excluded.benefits_text,skills_json=excluded.skills_json,
            raw_json_ld=excluded.raw_json_ld,scraped_at=CURRENT_TIMESTAMP""",
            row,
        )
        conn.execute(
            """UPDATE job_queue SET
            status='COMPLETED', last_error=?, last_error_kind=?, last_http_status=NULL,
            updated_at=? WHERE job_id=?""",
            (quality_note, "MISSING_SECTIONS" if missing else None, stamp(), job_id),
        )


def export_jsonl(conn: sqlite3.Connection, output: Path) -> int:
    rows = conn.execute("""SELECT d.*,q.url,q.location_preview,q.experience_preview,q.posted_at
                           FROM job_details d JOIN job_queue q ON q.job_id=d.job_id
                           WHERE q.status='COMPLETED' ORDER BY d.job_id""").fetchall()
    if not rows:
        print("[EXPORT] Không có JD COMPLETED; không thay đổi file JSONL hiện có.")
        return 0
    if output.resolve() == Path("data/raw/topcv.jsonl").resolve():
        raise ExportSafetyError(
            "Từ chối ghi đè data/raw/topcv.jsonl cũ; hãy dùng topcv_nodriver.jsonl"
        )

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        if row["job_id"] in seen_ids:
            continue
        jd = cleaned(row["description_text"])
        req = cleaned(row["requirements_text"])
        ben = cleaned(row["benefits_text"])
        if not row["title"] or len("\n".join((jd, req, ben)).strip()) < MIN_JD_LENGTH:
            continue
        try:
            job_url = normalize_url(row["url"])
        except ValueError:
            continue
        if job_id_from_url(job_url) != str(row["job_id"]):
            continue
        combined = "\n\n".join(
            f"{label}\n{value}"
            for label, value in (
                ("Mô tả công việc", jd),
                ("Yêu cầu ứng viên", req),
                ("Quyền lợi ứng viên", ben),
            )
            if value
        )
        try:
            skills = json.loads(row["skills_json"] or "[]")
        except ValueError:
            skills = []
        records.append(
            {
                "site": SOURCE_NAME,
                "job_id": row["job_id"],
                "job_url": job_url,
                "title": row["title"],
                "company": row["company_name"],
                "location": row["location"] or row["location_preview"],
                "salary": row["salary"],
                "experience_level": row["experience"] or row["experience_preview"],
                "posted_at": row["posted_at"],
                "job_level": row["job_level"],
                "employment_type": row["employment_type"],
                "date_posted": row["date_posted"],
                "valid_through": row["valid_through"],
                "skills": skills if isinstance(skills, list) else [],
                "job_description": jd,
                "requirements": req,
                "benefits": ben,
                "description": combined,
                "details_status": "ok",
            }
        )
        seen_ids.add(row["job_id"])

    if not records:
        raise ExportSafetyError("Không có JD COMPLETED hợp lệ; giữ nguyên JSONL hiện có")

    existing_count = 0
    existing_ids: set[str] = set()
    if output.is_file():
        try:
            with output.open("r", encoding="utf-8") as current:
                existing_ids = {str(json.loads(line)["job_id"]) for line in current if line.strip()}
            existing_count = len(existing_ids)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ExportSafetyError(
                f"Không đọc được JSONL hiện có; từ chối thay thế: {exc}"
            ) from exc
    if len(records) < existing_count:
        raise ExportSafetyError(
            f"Export mới chỉ có {len(records)} JD, ít hơn {existing_count} JD hiện có; "
            "giữ nguyên file"
        )
    missing_existing = existing_ids - seen_ids
    if missing_existing:
        preview = ", ".join(sorted(missing_existing)[:5])
        raise ExportSafetyError(
            f"Export mới thiếu {len(missing_existing)} job_id đã có ({preview}); giữ nguyên file"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        backup = backup_file(output)
        if backup:
            print(f"[BACKUP] JSONL -> {backup}")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"[EXPORT] {len(records)} JD hợp lệ -> {output}")
    return len(records)


def print_report(
    conn: sqlite3.Connection,
    *,
    new_success: int = 0,
    duplicates: int = 0,
    exported: int | None = None,
) -> dict[str, int]:
    counts = {state: 0 for state in QUEUE_STATES}
    for row in conn.execute("SELECT status, COUNT(*) AS total FROM job_queue GROUP BY status"):
        counts[row["status"]] = row["total"]
    source = get_source_state(conn)
    source_status = source["status"] if source else "READY"
    summary = " ".join(f"{state}={counts.get(state, 0)}" for state in QUEUE_STATES)
    print(f"[REPORT] {summary}")
    suffix = f" tổng export={exported}" if exported is not None else ""
    print(
        f"[REPORT] JD mới thành công={new_success} URL trùng={duplicates} "
        f"nguồn={source_status}{suffix}"
    )
    if source and source["status"] == "BLOCKED":
        print(
            f"[REPORT] source blocked_at={source['blocked_at']} HTTP={source['last_http_status']} "
            f"Retry-After={source['retry_after_raw']!r} parsed={source['retry_after_at']}"
        )
    return counts


def write_seen(path: Path, urls: list[str], complete: bool, error: str | None = None) -> None:
    """Standalone manifest; replaces missing crawlers.base.write_seen dependency."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "site": "topcv",
        "urls": list(dict.fromkeys(urls)),
        "complete": complete,
        "error": error,
        "updated_at": stamp(),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def source_policy(config_path: Path) -> float:
    """Fail closed for online scraping; `allowed` means project approval, not a grant from TopCV."""
    if not config_path.is_file():
        raise PermissionError(
            f"Không có {config_path}. Cần cấu hình nguồn được phép trước khi crawl."
        )
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Thiếu PyYAML: python -m pip install PyYAML") from exc
    doc = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    sources = doc.get("sources", []) if isinstance(doc, dict) else []
    src = next((v for v in sources if isinstance(v, dict) and v.get("name") == "topcv"), None)
    if src is None or src.get("allowed") is not True:
        raise PermissionError("topcv.allowed chưa phải true trong config/sources.yaml")
    try:
        delay = float(src.get("rate_limit_s", 5.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("rate_limit_s phải là số giây hợp lệ") from exc
    if delay < 1.0:
        raise ValueError("rate_limit_s phải >= 1 giây")
    return delay


class NodriverBrowser:
    """A single visible browser tab; CDP records document response status."""

    def __init__(self, profile: Path, chrome: str | None, delay: float):
        self.profile = profile
        self.chrome = chrome
        self.delay = delay
        self.driver = None
        self.tab = None
        self._document_statuses: list[dict[str, Any]] = []
        self._last_http_logged: tuple[str, int] | None = None

    async def start(self) -> None:
        try:
            import nodriver as uc
        except ImportError as exc:
            raise RuntimeError("Thiếu nodriver: python -m pip install nodriver") from exc
        self.uc = uc
        self.profile.mkdir(parents=True, exist_ok=True)
        options: dict[str, Any] = {"headless": False, "user_data_dir": str(self.profile.resolve())}
        if self.chrome:
            options["browser_executable_path"] = self.chrome
        self.driver = await uc.start(**options)
        self.tab = await self.driver.get("about:blank")
        await self.tab.send(uc.cdp.network.enable())

        def capture(event) -> None:
            if (
                str(event.type_).lower().endswith("document")
                or getattr(event.type_, "value", "") == "Document"
            ):
                response = event.response
                if urlparse(response.url).hostname in ("topcv.vn", "www.topcv.vn"):
                    headers = getattr(response, "headers", {}) or {}
                    retry_after = next(
                        (
                            str(value)
                            for key, value in dict(headers).items()
                            if str(key).lower() == "retry-after"
                        ),
                        None,
                    )
                    self._document_statuses.append(
                        {
                            "url": response.url,
                            "status": int(response.status),
                            "retry_after_raw": retry_after,
                        }
                    )

        self.tab.add_handler(uc.cdp.network.ResponseReceived, capture)

    @staticmethod
    def _is_transient_cdp_error(exc: Exception) -> bool:
        """Recognize navigation/DOM races, not HTTP access restrictions."""
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "could not find node with given id",
                "could not find node",
                "execution context was destroyed",
                "cannot find context with specified id",
                "no node with given id",
            )
        )

    async def _evaluate_snapshot(self, script: str) -> Any:
        """Retry CDP reads locally, without loading the URL again."""
        assert self.tab is not None
        for attempt in range(3):
            try:
                return await self.tab.evaluate(script, return_by_value=True)
            except Exception as exc:
                if not self._is_transient_cdp_error(exc):
                    raise BrowserReadError(f"Lỗi khi đọc DOM qua CDP: {exc}") from exc
                if attempt == 2:
                    raise BrowserReadError(f"Lỗi CDP khi đọc DOM sau 3 lần thử: {exc}") from exc
                print(f"[CDP] DOM thay đổi khi đọc; thử lại nội bộ ({attempt + 1}/2)", flush=True)
                await asyncio.sleep(0.5 * (attempt + 1))
        raise RuntimeError("Không thể đọc DOM sau các lần thử nội bộ")

    @staticmethod
    def _same_document_target(response_url: str, requested_url: str) -> bool:
        response = urlparse(response_url)
        requested = urlparse(requested_url)
        return (
            response.hostname in ("topcv.vn", "www.topcv.vn")
            and response.path.rstrip("/") == requested.path.rstrip("/")
            and response.query == requested.query
        )

    def _check_document_status(self, requested_url: str) -> None:
        # Only the requested top-level document is authoritative. A 403/429 from
        # an image, script or unrelated subframe must not block the source.
        matches = [
            item
            for item in self._document_statuses
            if self._same_document_target(item["url"], requested_url)
        ]
        if not matches:
            return
        response = matches[-1]
        code = int(response["status"])
        marker = (response["url"], code)
        if marker != self._last_http_logged:
            print(f"[HTTP] {code} {response['url']}", flush=True)
            self._last_http_logged = marker
        retry_raw = response.get("retry_after_raw")
        retry_at = parse_retry_after(retry_raw)
        if code == 429:
            raise RateLimited(
                "HTTP 429: TopCV giới hạn yêu cầu; đã dừng toàn bộ nguồn",
                status=code,
                url=response["url"],
                retry_after_raw=retry_raw,
                retry_after_at=retry_at,
            )
        if code in (401, 403):
            raise AccessRestricted(
                f"HTTP {code}: TopCV từ chối truy cập tự động",
                status=code,
                url=response["url"],
                retry_after_raw=retry_raw,
                retry_after_at=retry_at,
            )
        if code in (404, 410):
            raise PageNotFound(f"HTTP {code}")
        if code >= 400:
            raise BrowserReadError(f"HTTP {code} khi tải tài liệu chính")

    async def fetch(self, url: str, is_listing: bool = False) -> str:
        if self.tab is None or self.driver is None:
            raise RuntimeError("Browser chưa khởi động")
        await asyncio.sleep(self.delay)
        self._document_statuses.clear()
        self._last_http_logged = None
        print(f"[GET {'LIST' if is_listing else 'DETAIL'}] {url}", flush=True)
        # Keep navigating the original tab, so the network event handler stays attached.
        try:
            self.tab = await self.tab.get(url)
        except Exception as exc:
            raise BrowserReadError(f"Browser không tải được {url}: {exc}") from exc
        self._check_document_status(url)

        selector = (
            "div.job-item-search-result"
            if is_listing
            else "div.job-description__item, script[type='application/ld+json']"
        )
        selector_arg = json.dumps(selector)
        # Nodriver's evaluate(return_by_value=True) does not promise Python dicts
        # for JS object expressions. JSON.stringify forces a simple string which
        # can be decoded consistently, even across Nodriver versions.
        readiness = f"""JSON.stringify((() => ({{
            ready: document.readyState,
            found: Boolean(document.querySelector({selector_arg})),
            href: location.href,
            challenge: /just a moment|attention required|access denied/i.test(document.title)
        }}))())"""
        deadline = asyncio.get_running_loop().time() + 8.0
        while True:
            self._check_document_status(url)
            raw_state = await self._evaluate_snapshot(readiness)
            if isinstance(raw_state, str):
                try:
                    state = json.loads(raw_state)
                except json.JSONDecodeError as exc:
                    raise BrowserReadError(
                        f"Trạng thái DOM không phải JSON: {raw_state[:120]}"
                    ) from exc
            else:
                state = raw_state  # backward compatibility when a driver returns a dict
            if not isinstance(state, dict):
                raise BrowserReadError(
                    f"Nodriver trả kiểu {type(raw_state).__name__} thay vì trạng thái DOM; "
                    "kiểm tra API evaluate()/phiên Chrome"
                )
            if state.get("challenge"):
                raise AccessRestricted(
                    "Trang yêu cầu xác minh/chặn truy cập tự động; đã dừng",
                    url=url,
                )
            final_url = str(state.get("href") or "")
            if (
                not is_listing
                and state.get("ready") == "complete"
                and redirected_off_job(final_url)
            ):
                # Tin đã gỡ: TopCV trả 200 sau khi chuyển hướng về trang chủ /viec-lam,
                # trang đó vẫn chứa popup thanh toán có heading "Quyền lợi ứng viên".
                raise PageNotFound(f"Tin đã bị gỡ: chuyển hướng tới {final_url}")
            if state.get("found") and state.get("ready") != "loading":
                break
            if asyncio.get_running_loop().time() >= deadline:
                break
            await asyncio.sleep(0.5)

        # A primitive HTML string avoids the two stale-node-id calls in get_content.
        html = await self._evaluate_snapshot(
            "document.documentElement ? document.documentElement.outerHTML : ''"
        )
        self._check_document_status(url)
        if not isinstance(html, str) or not html.strip():
            raise BrowserReadError(
                f"Nodriver không trả HTML dạng chuỗi (nhận {type(html).__name__})"
            )
        if page_is_challenge(html):
            raise AccessRestricted(
                "Trang yêu cầu xác minh/chặn truy cập tự động; đã dừng",
                url=url,
            )
        if (
            "Không tìm thấy trang" in html[:30000]
            or "Trang bạn tìm kiếm không tồn tại" in html[:30000]
        ):
            raise PageNotFound("JD không tồn tại")
        print(f"[DOM] {len(html)} bytes {url}", flush=True)
        return html

    async def close(self) -> None:
        driver = self.driver
        self.driver = None
        self.tab = None
        if driver is None:
            return

        # nodriver 0.50.99 stop() schedules aclose() without awaiting it, then
        # terminates Chrome without awaiting Process.wait(). On Windows this
        # leaves Proactor pipe transports alive beyond asyncio.run(). Perform
        # each lifecycle step explicitly instead of calling stop().
        process = getattr(driver, "_process", None)
        browser_close = getattr(getattr(self.uc.cdp, "browser", None), "close", None)
        if browser_close is not None:
            with suppress(Exception):
                await asyncio.wait_for(driver.send(browser_close()), timeout=2.0)

        with suppress(Exception):
            await asyncio.wait_for(driver.aclose(), timeout=3.0)

        if process is not None:
            if process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except TimeoutError:
                    with suppress(ProcessLookupError):
                        process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3.0)
                    except TimeoutError:
                        with suppress(ProcessLookupError):
                            process.kill()
                        await asyncio.wait_for(process.wait(), timeout=3.0)

            # Drain and close PIPE transports created for stdin/stdout/stderr.
            communicate = getattr(process, "communicate", None)
            if communicate is not None:
                with suppress(Exception):
                    await asyncio.wait_for(communicate(), timeout=2.0)
            transport = getattr(process, "_transport", None)
            if transport is not None:
                with suppress(Exception):
                    transport.close()

        with suppress(Exception):
            driver._process = None
            driver._process_pid = None
        # Let Proactor callbacks scheduled by transport.close() run before the
        # event loop owned by asyncio.run() is destroyed.
        await asyncio.sleep(0)


async def crawl_listing(
    conn: sqlite3.Connection, client: NodriverBrowser, start_page: int, pages: int, seen: list[str]
) -> tuple[int, int]:
    total_new = 0
    total_duplicates = 0
    for page in range(start_page, start_page + pages):
        try:
            html = await client.fetch(SEARCH_URL.format(page=page), is_listing=True)
        except PageNotFound:
            print(f"[LIST] Trang {page} không tồn tại; dừng phân trang.")
            break
        cards = parse_cards(html)
        print(f"[TRANG {page}] {len(cards)} tin tuyển dụng")
        if not cards:
            print("[LIST] Không có tin. Có thể HTML thay đổi; không tự giả định đã hết trang.")
            break
        new = store_listing(conn, cards)
        total_new += new
        total_duplicates += len(cards) - new
        seen.extend(c["url"] for c in cards)
        print(f"[LIST] Thêm mới {new}/{len(cards)} vào SQLite")
    return total_new, total_duplicates


async def crawl_details(
    conn: sqlite3.Connection, client: NodriverBrowser, limit: int, min_length: int = MIN_JD_LENGTH
) -> int:
    rows = conn.execute(
        """SELECT job_id,url,title FROM job_queue
                           WHERE status IN ('PENDING','RETRY_PENDING')
                             AND attempt_count < ?
                           ORDER BY discovered_at,posted_at DESC,job_id LIMIT ?""",
        (MAX_ATTEMPTS, limit),
    ).fetchall()
    print(f"[DETAILS] Cần xử lý tối đa {len(rows)} JD (bỏ qua COMPLETED/BLOCKED/FAILED)")
    succeeded = 0
    for i, row in enumerate(rows, 1):
        job_id = row["job_id"]
        if not mark_processing(conn, job_id):
            continue
        print(f"[DETAIL {i}/{len(rows)}] {job_id} {row['title'] or ''}")
        try:
            html = await client.fetch(normalize_url(row["url"]))
            parsed = parse_jd_html(html)
            save_job_detail(conn, job_id, parsed, min_length)
            succeeded += 1
            print(f"[OK] {job_id}: {sum(len(parsed[k]) for k in MAIN_FIELDS)} ký tự JD")
        except AccessRestricted as exc:
            kind = "RATE_LIMITED" if isinstance(exc, RateLimited) else "ACCESS_RESTRICTED"
            set_status(conn, job_id, "BLOCKED", str(exc), error_kind=kind, http_status=exc.status)
            record_source_block(conn, exc)
            if exc.retry_after_raw:
                print(f"[HTTP] Retry-After={exc.retry_after_raw!r}; parsed={exc.retry_after_at}")
            print(f"[STOP] {exc}. Giữ nguyên dữ liệu đã lưu.")
            raise
        except PageNotFound as exc:
            set_status(conn, job_id, "NOT_FOUND", str(exc), error_kind="NOT_FOUND")
            print(f"[NOT_FOUND] {job_id}: {exc}")
        except BrowserReadError as exc:
            # A browser/session failure is not a job-level failure. Stop now so
            # subsequent jobs are not incorrectly mass-marked FAILED.
            set_status(conn, job_id, "RETRY_PENDING", str(exc), error_kind="BROWSER_TRANSIENT")
            print(f"[STOP] browser/CDP tại {job_id}: {exc}")
            raise
        except InvalidJobData as exc:
            set_status(conn, job_id, "INVALID_DATA", str(exc), error_kind="INVALID_DATA")
            print(f"[INVALID_DATA] {job_id}: {exc}")
        except Exception as exc:
            set_status(
                conn,
                job_id,
                "FAILED",
                f"{type(exc).__name__}: {exc}"[:500],
                error_kind=type(exc).__name__.upper(),
            )
            print(f"[FAILED] {job_id}: {exc}")
    return succeeded


def import_saved_html(
    conn: sqlite3.Connection, file_path: Path, job_url: str, min_length: int = MIN_JD_LENGTH
) -> None:
    if file_path.suffix.lower() not in (".html", ".htm"):
        raise ValueError("Chỉ hỗ trợ HTML. Trong Chrome hãy lưu dạng Webpage, HTML Only.")
    url = normalize_url(job_url)
    parsed = parse_jd_html(file_path.read_text(encoding="utf-8-sig", errors="replace"))
    if not is_valid_jd(parsed, min_length):
        raise ValueError("File HTML không chứa JD đủ dài; không thay đổi database")
    job_id = job_id_from_url(url)
    conn.execute(
        """INSERT OR IGNORE INTO job_queue (job_id,url,title,company_name)
                    VALUES (?,?,?,?)""",
        (job_id, url, parsed.get("title"), parsed.get("company_name")),
    )
    try:
        save_job_detail(conn, job_id, parsed, min_length)
    except Exception:
        conn.rollback()
        raise
    print(f"[IMPORT] Đã lưu JD {job_id} từ {file_path} (không mở trình duyệt)")


def import_listing_csv(conn: sqlite3.Connection, file_path: Path) -> tuple[int, int, int]:
    """Import a previously collected TopCV listing CSV without using the network."""
    if file_path.suffix.lower() != ".csv":
        raise ValueError("--import-listing-csv chỉ hỗ trợ file CSV")
    with file_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = set(reader.fieldnames or ())
        missing = {"title", "url"} - headers
        if missing:
            raise ValueError(f"CSV thiếu cột bắt buộc: {', '.join(sorted(missing))}")
        jobs: list[dict[str, str]] = []
        invalid = 0
        for row in reader:
            try:
                url = normalize_url(row.get("url") or "")
                job_id = job_id_from_url(url)
            except ValueError:
                invalid += 1
                continue
            title = cleaned(row.get("title"))
            if not title:
                invalid += 1
                continue
            jobs.append(
                {
                    "job_id": job_id,
                    "url": url,
                    "title": title,
                    "company_name": cleaned(row.get("company")),
                    "salary_preview": cleaned(row.get("salary")),
                    "location_preview": cleaned(row.get("location")),
                    "experience_preview": cleaned(row.get("experience")),
                    "posted_at": cleaned(row.get("date_posted")),
                }
            )
    added = store_listing(conn, jobs)
    duplicates = len(jobs) - added
    print(
        f"[IMPORT LIST] Thêm mới {added}/{len(jobs)} URL từ {file_path}; "
        f"trùng={duplicates} không hợp lệ={invalid} (không dùng mạng)"
    )
    return added, duplicates, invalid


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TopCV ingestion với Nodriver, SQLite và JSONL")
    parser.add_argument("--pages", type=int, default=1, help="Số trang danh sách, mặc định 1")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument(
        "--limit", type=int, default=10, help="Số JD tối đa mỗi lần chạy, mặc định 10"
    )
    parser.add_argument(
        "--target-total",
        type=int,
        default=None,
        help="Dừng khi tổng số JD COMPLETED đạt mục tiêu; không xử lý vượt mục tiêu",
    )
    parser.add_argument(
        "--details-only", action="store_true", help="Chỉ xử lý hàng đợi PENDING trong SQLite"
    )
    parser.add_argument(
        "--reset-dom-failures",
        action="store_true",
        help="Chỉ chuyển các FAILED do lỗi trạng thái DOM cũ về PENDING, không dùng mạng",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Chỉ báo cáo trạng thái SQLite, không dùng mạng và không export",
    )
    parser.add_argument(
        "--export-only", action="store_true", help="Chỉ xuất JSONL từ SQLite, không dùng mạng"
    )
    parser.add_argument(
        "--clear-source-block",
        action="store_true",
        help=(
            "Mở khóa nguồn bằng thao tác chủ động sau khi đã xác minh quyền/chính sách; "
            "không reset job BLOCKED"
        ),
    )
    parser.add_argument("--no-details", action="store_true", help="Chỉ lấy danh sách, không vào JD")
    parser.add_argument(
        "--import-html", type=Path, help="Nhập JD từ file HTML đã lưu thủ công, không dùng mạng"
    )
    parser.add_argument(
        "--import-listing-csv",
        type=Path,
        help="Nhập hàng đợi URL từ CSV TopCV đã có, không dùng mạng",
    )
    parser.add_argument("--job-url", help="URL của JD; bắt buộc cùng --import-html")
    parser.add_argument("--db", type=Path, default=Path(DEFAULT_DB))
    parser.add_argument("--out", type=Path, default=Path(DEFAULT_OUT))
    parser.add_argument("--seen-file", type=Path, default=Path(DEFAULT_SEEN))
    parser.add_argument("--sources-config", type=Path, default=Path("config/sources.yaml"))
    parser.add_argument("--profile", type=Path, default=Path("data/state/chrome_topcv_profile"))
    parser.add_argument("--chrome-path", default=os.environ.get("CHROME_PATH"))
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Khoảng nghỉ giữa lần tải; không thấp hơn rate_limit_s",
    )
    parser.add_argument(
        "--min-jd-length",
        type=int,
        default=MIN_JD_LENGTH,
        help=f"Độ dài nội dung JD tối thiểu (mặc định {MIN_JD_LENGTH})",
    )
    args = parser.parse_args(argv)
    if args.pages < 1 or args.start_page < 1 or args.limit < 1 or args.min_jd_length < 1:
        parser.error("--pages, --start-page, --limit, --min-jd-length phải >= 1")
    if args.target_total is not None and args.target_total < 1:
        parser.error("--target-total phải >= 1")
    if args.details_only and args.no_details:
        parser.error("--details-only không thể đi cùng --no-details")
    offline_modes = (
        args.reset_dom_failures,
        args.report_only,
        args.export_only,
        args.clear_source_block,
    )
    if sum(bool(mode) for mode in offline_modes) > 1:
        parser.error(
            "--reset-dom-failures/--report-only/--export-only/--clear-source-block phải chạy riêng"
        )
    if any(offline_modes) and (args.details_only or args.no_details or args.import_html):
        parser.error("Chế độ offline quản trị phải chạy riêng")
    if bool(args.import_html) != bool(args.job_url):
        parser.error("--import-html cần đi cùng --job-url (và ngược lại)")
    if args.import_html and (args.details_only or args.no_details):
        parser.error("--import-html không dùng cùng --details-only/--no-details")
    if args.import_listing_csv and (
        args.details_only or args.no_details or args.import_html or any(offline_modes)
    ):
        parser.error("--import-listing-csv phải chạy riêng")
    if args.delay is not None and args.delay < 1:
        parser.error("--delay phải >= 1 giây")
    return args


async def run(args: argparse.Namespace) -> int:
    db_backup = backup_file(args.db)
    if db_backup:
        print(f"[BACKUP] SQLite -> {db_backup}")
    conn = initialize_db(args.db)
    legacy_source_block = migrate_legacy_source_block(conn)
    if legacy_source_block:
        print("[MIGRATION] Khôi phục trạng thái nguồn BLOCKED từ lỗi HTTP 403/429 cũ")
    completed_before = conn.execute(
        "SELECT COUNT(*) FROM job_queue WHERE status='COMPLETED'"
    ).fetchone()[0]
    seen: list[str] = []
    completed = False
    issue: str | None = None
    browser: NodriverBrowser | None = None
    result_code = 0
    new_success = 0
    duplicates = 0
    exported: int | None = None
    online_mode = not any(
        (
            args.reset_dom_failures,
            args.report_only,
            args.export_only,
            args.clear_source_block,
            args.import_html,
            args.import_listing_csv,
        )
    )
    should_export = not (args.report_only or args.clear_source_block or args.import_listing_csv)
    try:
        if args.report_only or args.export_only:
            completed = True
        elif args.clear_source_block:
            source_policy(args.sources_config)
            count = clear_source_block(conn)
            print(
                f"[SOURCE] Đã mở khóa {count} nguồn. Các job BLOCKED được giữ nguyên; "
                "chỉ tiếp tục sau khi quyền truy cập đã được xác minh."
            )
            completed = True
        elif args.reset_dom_failures:
            count = reset_dom_failures(conn)
            print(
                f"[RESET DOM] Đưa {count} tin FAILED do lỗi DOM cũ về PENDING; "
                "giữ nguyên COMPLETED/BLOCKED và các lỗi khác."
            )
            completed = True
        elif args.import_html:
            import_saved_html(conn, args.import_html, args.job_url, args.min_jd_length)
            new_success = 1
            completed = True
        elif args.import_listing_csv:
            _, duplicates, _ = import_listing_csv(conn, args.import_listing_csv)
            completed = True
        else:
            recovered = recover_processing(conn)
            if recovered:
                print(f"[RECOVERY] Đưa {recovered} job PROCESSING cũ về RETRY_PENDING")
            if args.target_total is not None and completed_before >= args.target_total:
                print(
                    f"[TARGET] Đã có {completed_before}/{args.target_total} JD; "
                    "không truy cập mạng."
                )
                completed = True
            else:
                delay = max(source_policy(args.sources_config), args.delay or 0)
                state = get_source_state(conn)
                if state and state["status"] == "BLOCKED":
                    issue = (
                        f"Nguồn đang BLOCKED từ {state['blocked_at']} "
                        f"(HTTP {state['last_http_status']}); không tự mở lại. Chỉ dùng "
                        "--clear-source-block sau khi xác minh quyền/chính sách."
                    )
                    print(f"[STOP] {issue}")
                    result_code = 2
                else:
                    print(
                        f"[POLICY] allowed=true trong {args.sources_config}; "
                        "đây là phê duyệt nội bộ, "
                        f"không phải quyền từ TopCV; nghỉ ít nhất {delay:.1f}s giữa lần tải"
                    )
                    browser = NodriverBrowser(args.profile, args.chrome_path, delay)
                    await browser.start()
                    if not args.details_only:
                        _, duplicates = await crawl_listing(
                            conn, browser, args.start_page, args.pages, seen
                        )
                    if not args.no_details:
                        detail_limit = args.limit
                        if args.target_total is not None:
                            current_total = conn.execute(
                                "SELECT COUNT(*) FROM job_queue WHERE status='COMPLETED'"
                            ).fetchone()[0]
                            remaining = max(args.target_total - current_total, 0)
                            detail_limit = min(detail_limit, remaining)
                            print(
                                f"[TARGET] Hiện có {current_total}/{args.target_total} JD; "
                                f"lượt này xử lý tối đa {detail_limit}."
                            )
                        if detail_limit > 0:
                            new_success = await crawl_details(
                                conn, browser, detail_limit, args.min_jd_length
                            )
                    completed = True
    except AccessRestricted as exc:
        issue = str(exc)
        record_source_block(conn, exc)
        print(f"[STOP] {issue}")
        result_code = 2
    except (Exception, KeyboardInterrupt) as exc:
        issue = f"{type(exc).__name__}: {exc}"
        print(f"[ERROR] {issue}")
        result_code = 1
    finally:
        if browser is not None:
            try:
                await browser.close()
                await asyncio.sleep(0)
            except Exception as exc:
                print(f"[WARN] Không đóng Chrome sạch sẽ: {exc}")
                if result_code == 0:
                    result_code = 1
                    issue = f"BROWSER_CLOSE: {exc}"
        if online_mode:
            try:
                write_seen(args.seen_file, seen, complete=completed, error=issue)
            except Exception as exc:
                print(f"[WARN] Không ghi được seen manifest: {exc}")
                if result_code == 0:
                    result_code = 1
        if should_export:
            try:
                exported = export_jsonl(conn, args.out)
            except Exception as exc:
                print(f"[EXPORT ERROR] {type(exc).__name__}: {exc}")
                if result_code == 0:
                    result_code = 1
        completed_after = conn.execute(
            "SELECT COUNT(*) FROM job_queue WHERE status='COMPLETED'"
        ).fetchone()[0]
        new_success = max(new_success, completed_after - completed_before)
        try:
            print_report(conn, new_success=new_success, duplicates=duplicates, exported=exported)
        finally:
            conn.close()
    return result_code


def main(argv: list[str] | None = None) -> int:
    # Windows terminals may expose cp1252 even when messages contain Vietnamese.
    # Never let console encoding make argparse/help or final cleanup crash.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with suppress(OSError, ValueError):
                reconfigure(errors="replace")
    args = arguments(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
