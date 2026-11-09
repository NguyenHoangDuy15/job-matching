"""Nạp file JSONL tin tuyển dụng đã thu thập sẵn (ví dụ topcv.jsonl) vào Supabase.

Dùng chung đường ghi với crawler (ingestion.store.PgStore): raw.job_snapshots giữ nguyên
bản ghi gốc, core.jobs + job_sources + job_locations được chuẩn hóa tỉnh/lương như S2-T03.

    uv run python scripts/load_jsonl.py data/raw/topcv.jsonl --source topcv --dry-run
    uv run python scripts/load_jsonl.py data/raw/topcv.jsonl --source topcv

Đọc được 2 định dạng đang có trong data/ (khóa thiếu thì bỏ qua):
- TopCV (data/raw/topcv*.jsonl): job_id, job_url, title, company, location, salary,
  experience_level, date_posted, valid_through, description, job_description,
  requirements, benefits, work_location, skills, details_status
- VietnamWorks (data/clean/vietnamworks_jobs.jsonl): source_job_id, source_url, title,
  company, location, locations, salary, posted_at, expired_on, description, skills
"""

import argparse
import json
import re
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

from ingestion.jsonld import mask_contacts
from ingestion.location import default_index
from ingestion.models import JobPostingRaw, LocationRaw, SalaryRaw
from ingestion.store import LocalStore, PgStore, RunStats

_JOB_ID = re.compile(r"(\d+)\.html?(?:[?#].*)?$")
_YEARS = re.compile(r"(\d+(?:[.,]\d+)?)")


def job_id_from_url(url: str) -> str | None:
    match = _JOB_ID.search(url or "")
    return match.group(1) if match else None


def years_from_text(text: str | None) -> float | None:
    """'2 năm' → 2; 'Dưới 1 năm' / 'Không yêu cầu kinh nghiệm' → 0; 'Trên 5 năm' → 5."""
    if not text:
        return None
    lowered = text.lower()
    if "không yêu cầu" in lowered or "chưa có" in lowered or "dưới 1" in lowered:
        return 0.0
    match = _YEARS.search(lowered)
    return float(match.group(1).replace(",", ".")) if match else None


def locations_from_record(record: dict) -> list[LocationRaw]:
    """Lấy tỉnh từ `location`, `locations` và các dòng tiêu đề 'Tỉnh:' trong `work_location`."""
    names: list[str] = []
    if record.get("location"):
        names.append(str(record["location"]))
    extra = record.get("locations")
    if isinstance(extra, list):
        names.extend(str(x) for x in extra if x)
    for line in str(record.get("work_location") or "").splitlines():
        line = line.strip()
        if line.endswith(":") and len(line) < 60:
            names.append(line[:-1].strip())
    seen = dict.fromkeys(n for n in names if n)
    return [LocationRaw(locality=name) for name in seen]


def _date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def record_to_posting(record: dict, source: str, fetched_at: datetime) -> JobPostingRaw | None:
    """Một dòng JSONL → JobPostingRaw. Trả None nếu bản ghi không dùng được."""
    if record.get("details_status") not in (None, "ok"):
        return None
    url = record.get("job_url") or record.get("url") or record.get("source_url")
    job_id = str(record.get("job_id") or record.get("source_job_id") or "") or None
    job_id = job_id or job_id_from_url(url)
    title = " ".join(str(record.get("title") or "").split())
    if not (url and job_id and title):
        return None
    description = record.get("description") or "\n\n".join(
        str(record[k]) for k in ("job_description", "requirements", "benefits") if record.get(k)
    )
    salary = record.get("salary")
    skills = record.get("skills")
    return JobPostingRaw(
        source=source,
        source_job_id=job_id,
        url=url,
        title=title,
        company_name=record.get("company") or None,
        description_text=mask_contacts(description),
        date_posted=_date(record.get("date_posted")) or _date(record.get("posted_at")),
        valid_through=_date(record.get("valid_through")) or _date(record.get("expired_on")),
        employment_type=record.get("employment_type") or None,
        locations=locations_from_record(record),
        remote=False,
        salary=SalaryRaw(text=str(salary)) if salary else None,
        years_exp_min=years_from_text(record.get("experience_level")),
        skills_text=", ".join(map(str, skills)) if isinstance(skills, list) else skills or None,
        json_ld=record,  # lưu nguyên bản ghi vào raw.job_snapshots.payload
        fetched_at=fetched_at,
    )


def read_jsonl(path: Path) -> Iterator[tuple[int, dict]]:
    with path.open(encoding="utf-8-sig") as fh:
        for line_no, line in enumerate(fh, start=1):
            if line.strip():
                yield line_no, json.loads(line)


def load_file(path: Path, store, source: str, run_type: str = "backfill") -> RunStats:
    stats = RunStats()
    fetched_at = datetime.now(UTC)
    run_id = store.start_run(source, None, run_type)
    status, error = "success", None
    try:
        for line_no, record in read_jsonl(path):
            posting = record_to_posting(record, source, fetched_at)
            if posting is None:
                stats.skip("invalid")
                print(
                    f"  dòng {line_no}: bỏ qua (thiếu url/mã tin/tiêu đề hoặc details_status lỗi)"
                )
                continue
            result = store.save(posting, None, run_id)
            stats.count(result)
            print(f"  dòng {line_no}: {result:9} {posting.title[:70]}")
    except Exception as exc:
        status, error = "failed", repr(exc)
        raise
    finally:
        if status == "success" and stats.skipped:
            status = "partial"
        store.finish_run(run_id, stats, status, error)
    print(
        f"KẾT QUẢ: {status} · mới {stats.items_new} · cập nhật {stats.items_updated}"
        f" · không đổi {stats.items_seen - stats.items_new - stats.items_updated}"
        f" · bỏ qua {sum(stats.skipped.values())}"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    from ingestion.crawl import _database_url

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Nạp file JSONL tin tuyển dụng vào Supabase")
    parser.add_argument("path", type=Path)
    parser.add_argument("--source", required=True, help="mã nguồn trong ops.sources.code")
    parser.add_argument("--dry-run", action="store_true", help="không ghi DB")
    args = parser.parse_args(argv)

    if args.dry_run:
        store = LocalStore(default_index())
    else:
        dsn = _database_url()
        if not dsn:
            parser.error("thiếu DATABASE_URL (biến môi trường hoặc file .env)")
        store = PgStore(dsn)
        if not store.salary_v2:
            print("! DB chưa chạy 0002_fx_rates.sql: chỉ ghi các cột lương của schema v2.0.")
    try:
        stats = load_file(args.path, store, args.source)
    finally:
        store.close()
    return 0 if stats.items_seen else 1


if __name__ == "__main__":
    sys.exit(main())
