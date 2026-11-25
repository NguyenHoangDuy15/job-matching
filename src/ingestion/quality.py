"""Báo cáo chất lượng mỗi lượt crawl (S4-T05, US-19) → ops.quality_reports.

Đếm trên các tin đã chuẩn hóa trong lượt (JobRow), không đọc lại DB:
- completeness: tin có đủ tiêu đề, công ty, mô tả, link ứng tuyển, địa điểm.
- validity: tiêu đề có, lương min ≤ max, hạn nộp không trước ngày đăng.
- uniqueness: 1 - tỉ lệ tin trùng với tin chuẩn có sẵn (dedup giữa nguồn).
- salary_parsed_pct: lương đọc được (có số, hoặc "thỏa thuận").
- province_parsed_pct: map được ít nhất một tỉnh/thành.
- schema_errors: số tin bị bỏ qua vì sai cấu trúc (RunStats.skipped).
- freshness_hours: số giờ từ ngày đăng mới nhất (0h giờ Việt Nam) tới lúc kết thúc lượt.

Tỉ lệ là phân số 0–1, 4 chữ số (cột numeric(5,4)); lượt không có tin nào thì None.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

if TYPE_CHECKING:  # tránh import vòng với ingestion.store
    from ingestion.models import JobPostingRaw
    from ingestion.store import JobRow, RunStats

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_SAMPLES = 10


@dataclass
class QualityCounter:
    total: int = 0
    complete: int = 0
    valid: int = 0
    duplicates: int = 0
    salary_parsed: int = 0
    province_parsed: int = 0
    newest_posted: date | None = None
    missing: dict[str, int] = field(default_factory=dict)
    invalid: dict[str, int] = field(default_factory=dict)
    unmatched_locations: list[str] = field(default_factory=list)
    invalid_samples: list[dict[str, str]] = field(default_factory=list)

    def add(self, row: JobRow, posting: JobPostingRaw, result: str) -> None:
        cols = row.columns
        self.total += 1
        if result == "duplicate":
            self.duplicates += 1

        missing = missing_fields(row, posting)
        for name in missing:
            self.missing[name] = self.missing.get(name, 0) + 1
        if not missing:
            self.complete += 1

        problems = invalid_reasons(cols)
        for name in problems:
            self.invalid[name] = self.invalid.get(name, 0) + 1
        if problems:
            if len(self.invalid_samples) < MAX_SAMPLES:
                self.invalid_samples.append(
                    {"source_job_id": posting.source_job_id, "reason": ", ".join(problems)}
                )
        else:
            self.valid += 1

        if salary_parsed(cols):
            self.salary_parsed += 1
        if row.province_codes:
            self.province_parsed += 1
        else:
            for loc in row.unmatched_locations or ((row.address_raw,) if row.address_raw else ()):
                if (
                    loc
                    and loc not in self.unmatched_locations
                    and len(self.unmatched_locations) < MAX_SAMPLES
                ):
                    self.unmatched_locations.append(loc)

        posted = _as_date(cols.get("posted_at"))
        if posted and (self.newest_posted is None or posted > self.newest_posted):
            self.newest_posted = posted


def missing_fields(row: JobRow, posting: JobPostingRaw) -> list[str]:
    cols = row.columns
    out = []
    if not (cols.get("title") or "").strip():
        out.append("title")
    if not (row.company_name or "").strip():
        out.append("company")
    if not ((cols.get("jd_text") or posting.description_text or "").strip()):
        out.append("description")
    if not cols.get("apply_url"):
        out.append("apply_url")
    if not row.province_codes and not (row.address_raw or "").strip():
        out.append("location")
    return out


def invalid_reasons(cols: dict[str, Any]) -> list[str]:
    out = []
    if not (cols.get("title") or "").strip():
        out.append("title_empty")
    lo, hi = cols.get("salary_min_vnd"), cols.get("salary_max_vnd")
    if lo is not None and hi is not None and lo > hi:
        out.append("salary_min_gt_max")
    if lo is not None and lo < 0 or hi is not None and hi < 0:
        out.append("salary_negative")
    posted, until = _as_date(cols.get("posted_at")), _as_date(cols.get("valid_through"))
    if posted and until and until < posted:
        out.append("valid_through_before_posted")
    return out


def salary_parsed(cols: dict[str, Any]) -> bool:
    if cols.get("salary_is_negotiable"):
        return True
    if cols.get("salary_min_vnd") is not None or cols.get("salary_max_vnd") is not None:
        return True
    return cols.get("salary_status") in ("parsed", "negotiable")


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.astimezone(VN_TZ).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return None


def _ratio(part: int, total: int) -> float | None:
    return round(part / total, 4) if total else None


def freshness_hours(newest: date | None, now: datetime) -> float | None:
    if newest is None:
        return None
    start = datetime.combine(newest, time.min, tzinfo=VN_TZ)
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    hours = max((now - start).total_seconds() / 3600, 0.0)
    return round(min(hours, 999_999.99), 2)  # numeric(8,2)


def build_report(counter: QualityCounter, stats: RunStats, now: datetime) -> dict[str, Any]:
    total = counter.total
    return {
        "completeness": _ratio(counter.complete, total),
        "validity": _ratio(counter.valid, total),
        "uniqueness": _ratio(total - counter.duplicates, total),
        "salary_parsed_pct": _ratio(counter.salary_parsed, total),
        "province_parsed_pct": _ratio(counter.province_parsed, total),
        "schema_errors": sum(stats.skipped.values()),
        "freshness_hours": freshness_hours(counter.newest_posted, now),
        "details": {
            "items": total,
            "complete": counter.complete,
            "valid": counter.valid,
            "duplicates": counter.duplicates,
            "salary_parsed": counter.salary_parsed,
            "province_parsed": counter.province_parsed,
            "newest_posted": counter.newest_posted.isoformat() if counter.newest_posted else None,
            "missing": dict(sorted(counter.missing.items())),
            "invalid": dict(sorted(counter.invalid.items())),
            "skipped": dict(sorted(stats.skipped.items())),
            "unmatched_locations": counter.unmatched_locations,
            "invalid_samples": counter.invalid_samples,
        },
    }
