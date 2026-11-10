"""Chuyển JobPostingRaw thành dòng core.jobs và ghi vào Supabase (hoặc file khi chạy thử).

Một tin = một transaction:
  raw.job_snapshots (bản gốc, không ghi đè) → core.companies → core.jobs
  → core.job_sources (nguồn gốc) → core.job_locations (tỉnh chuẩn, dùng location.py của S2-D01).
Lương dùng salary.py của S2-D02; các cột salary_* mới chỉ ghi khi DB đã chạy
db/migrations/0002_fx_rates.sql.
"""

import gzip
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from ingestion.fx import FxRate, FxSyncResult, load_latest_pg, sync_rates_pg
from ingestion.location import ProvinceIndex, build_index, normalize_key, normalize_location
from ingestion.models import JobPostingRaw
from ingestion.salary import parse_salary, to_vnd

try:  # S2-D03 (PR #618): tách JD thành 4 section. Chưa có thì ghi toàn văn vào description.
    from skillkit.sections import split_text
except ImportError:  # pragma: no cover - chỉ xảy ra trước khi #618 được merge
    split_text = None

SaveResult = Literal["new", "updated", "unchanged"]

DATA_RAW = Path(__file__).resolve().parents[2] / "data" / "raw"

# Từ chỉ loại hình doanh nghiệp: bỏ khi so khớp tên công ty giữa các nguồn.
_LEGAL_WORDS = (
    "loai hinh doanh nghiep",
    "tong cong ty",
    "cong ty co phan",
    "cong ty tnhh",
    "cong ty",
    "trach nhiem huu han",
    "mot thanh vien",
    "co phan",
    "tnhh",
    "mtv",
    "jsc",
    "company limited",
    "co ltd",
    "limited",
    "ltd",
    "corporation",
    "corp",
    "inc",
    "llc",
)
# Cột salary_* thêm bởi db/migrations/0002_fx_rates.sql (S2-D02).
SALARY_V2_COLUMNS = (
    "salary_amount_min",
    "salary_amount_max",
    "salary_currency",
    "salary_pay_type",
    "salary_status",
    "salary_fx_date",
)


def company_name_norm(name: str) -> str:
    key = f" {normalize_key(name)} "
    for word in _LEGAL_WORDS:
        key = key.replace(f" {word} ", " ")
    return " ".join(key.split()) or normalize_key(name)


def section_columns(text: str) -> dict[str, str | None]:
    """4 cột section của core.jobs. Không tách được thì giữ toàn văn ở description."""
    if split_text is not None and text:
        cols = split_text(text).columns()
        if any(cols.values()):
            return cols
    return {"description": text or None, "requirements": None, "preferred": None, "benefits": None}


def content_hash(posting: JobPostingRaw) -> bytes:
    """SHA-256 nội dung LẤY TỪ NGUỒN: đổi thì mới cập nhật core.jobs.

    Không đưa kết quả tách section vào đây: cải tiến bộ tách không được làm tin "đổi nội dung".
    Đổi tên khóa hay thêm khóa sẽ làm mọi tin đã nạp bị coi là đã đổi ở lần crawl kế tiếp.
    """
    payload = {
        "title": posting.title,
        "company": posting.company_name,
        "description": posting.description_text,
        "salary": posting.salary_text(),
        "location": posting.location_text(),
        "remote": posting.remote,
        "valid_through": posting.valid_through.isoformat() if posting.valid_through else None,
        "employment_type": posting.employment_type,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).digest()


@dataclass
class JobRow:
    """Các cột core.jobs + phụ trợ cho companies/job_locations."""

    columns: dict[str, Any]
    company_name: str | None
    province_codes: tuple[int, ...]
    address_raw: str
    unmatched_locations: tuple[str, ...] = ()


def build_job_row(
    posting: JobPostingRaw,
    index: ProvinceIndex,
    fx_rates: Mapping[str, FxRate],
    today: date,
) -> JobRow:
    loc = normalize_location(posting.location_text(), title=posting.title, index=index)
    work_mode = "remote" if posting.remote else loc.work_mode

    parsed = parse_salary(posting.salary_text())
    vnd = to_vnd(parsed, fx_rates)
    expired = posting.valid_through is not None and posting.valid_through < today

    columns: dict[str, Any] = {
        "origin": "crawled",
        "title": posting.title,
        "title_norm": normalize_key(posting.title),
        "work_mode": work_mode,
        "employment_type": posting.employment_type,
        "years_exp_min": posting.years_exp_min,
        "salary_raw": parsed.raw or None,
        "salary_min_vnd": vnd.min_vnd,
        "salary_max_vnd": vnd.max_vnd,
        "salary_is_negotiable": parsed.status == "negotiable",
        "salary_amount_min": parsed.amount_min,
        "salary_amount_max": parsed.amount_max,
        "salary_currency": parsed.currency,
        "salary_pay_type": parsed.pay_type,
        "salary_status": parsed.status,
        "salary_fx_date": vnd.fx_date,
        "jd_text": posting.description_text,  # migration 0003; DB chưa có cột thì bị bỏ qua
        **section_columns(posting.description_text),
        "posted_at": posting.date_posted,
        "valid_through": posting.valid_through,
        "apply_url": posting.url,
        "status": "expired" if expired else "open",
        "content_hash": content_hash(posting),
    }
    return JobRow(
        columns=columns,
        company_name=posting.company_name,
        province_codes=loc.province_codes,
        address_raw=posting.location_text(),
        unmatched_locations=loc.unmatched,
    )


def html_key(posting: JobPostingRaw) -> str:
    day = posting.fetched_at.date().isoformat()
    return f"crawl/{posting.source}/{day}/{posting.source_job_id}.html.gz"


def save_html(key: str, page_html: str, root: Path = DATA_RAW) -> None:
    """Lưu HTML gốc nén gzip (ADR-003: lưu file local, chưa dùng object storage)."""
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(page_html.encode("utf-8")))


@dataclass
class RunStats:
    pages_fetched: int = 0
    items_seen: int = 0
    items_new: int = 0
    items_updated: int = 0
    http_errors: int = 0
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def count(self, result: SaveResult) -> None:
        self.items_seen += 1
        if result == "new":
            self.items_new += 1
        elif result == "updated":
            self.items_updated += 1


class LocalStore:
    """--dry-run: không ghi DB, ghi mỗi tin một dòng JSONL để xem lại."""

    def __init__(self, index: ProvinceIndex, out_dir: Path = DATA_RAW / "crawl"):
        self.index = index
        self.fx_rates: dict[str, FxRate] = {}
        self.out_dir = out_dir
        self._seen: set[tuple[str, str]] = set()

    def start_run(self, source_name: str, source_id: int | None, run_type: str) -> int | None:
        return None

    def save(self, posting: JobPostingRaw, key: str, run_id: int | None) -> SaveResult:
        row = build_job_row(posting, self.index, self.fx_rates, posting.fetched_at.date())
        out = self.out_dir / posting.source / f"{posting.fetched_at.date()}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "posting": posting.model_dump(mode="json", exclude={"json_ld", "description_html"}),
            "row": {k: v for k, v in row.columns.items() if k != "content_hash"},
            "province_codes": row.province_codes,
            "unmatched_locations": row.unmatched_locations,
            "html_key": key,
        }
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        ident = (posting.source, posting.source_job_id)
        result: SaveResult = "unchanged" if ident in self._seen else "new"
        self._seen.add(ident)
        return result

    def finish_run(self, run_id, stats: RunStats, status: str, error: str | None) -> None:
        return None

    def close(self) -> None:
        return None


class PgStore:
    """Ghi vào Supabase Postgres bằng psycopg (chuỗi kết nối DATABASE_URL)."""

    def __init__(self, dsn: str):
        import psycopg  # import muộn để test không cần thư viện DB

        dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
        # prepare_threshold=None: an toàn cả khi đi qua Supavisor transaction mode (cổng 6543).
        self.conn = psycopg.connect(dsn, prepare_threshold=None)
        self.columns = self._job_columns()
        missing = [c for c in SALARY_V2_COLUMNS if c not in self.columns]
        self.salary_v2 = not missing
        self.index = self._province_index()
        self.fx_rates = self._fx_rates() if self.salary_v2 else {}

    # ---- đọc tham chiếu ---------------------------------------------------
    def _job_columns(self) -> set[str]:
        rows = self.conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'core' and table_name = 'jobs'"
        ).fetchall()
        self.conn.commit()
        return {r[0] for r in rows}

    def _province_index(self) -> ProvinceIndex:
        provinces = dict(self.conn.execute("select code, name from ref.provinces").fetchall())
        aliases = dict(
            self.conn.execute("select alias_norm, province_code from ref.province_legacy")
        )
        self.conn.commit()
        return build_index(provinces, aliases)

    def _fx_rates(self) -> dict[str, FxRate]:
        exists = self.conn.execute("select to_regclass('ref.fx_latest') is not null").fetchone()[0]
        rates = load_latest_pg(self.conn) if exists else {}
        self.conn.commit()
        return rates

    def sync_fx(self, today: date) -> FxSyncResult:
        """Bước ① trước crawl: cập nhật tỷ giá, tính lại lương tin ngoại tệ, nạp lại bảng tỷ giá
        để tin mới trong lượt này dùng cùng tỷ giá với tin cũ."""
        result = sync_rates_pg(self.conn, today)
        self.fx_rates = self._fx_rates()
        return result

    def source_id(self, code: str) -> int:
        row = self.conn.execute("select id from ops.sources where code = %s", (code,)).fetchone()
        self.conn.commit()
        if row is None:
            raise ValueError(f"ops.sources không có nguồn '{code}'")
        return row[0]

    # ---- ops.crawl_runs ----------------------------------------------------
    def start_run(self, source_name: str, source_id: int | None, run_type: str) -> int:
        self._source_id = source_id or self.source_id(source_name)
        with self.conn.transaction():
            run_id = self.conn.execute(
                "insert into ops.crawl_runs (source_id, run_type) values (%s, %s) returning id",
                (self._source_id, run_type),
            ).fetchone()[0]
            self.conn.execute(
                "update ops.sources set robots_checked_at = current_date where id = %s",
                (self._source_id,),
            )
        return run_id

    def finish_run(self, run_id: int, stats: RunStats, status: str, error: str | None) -> None:
        with self.conn.transaction():
            self.conn.execute(
                """update ops.crawl_runs
                      set finished_at = now(), status = %s, pages_fetched = %s,
                          items_seen = %s, items_new = %s, items_updated = %s,
                          http_errors = %s, error_sample = %s
                    where id = %s""",
                (
                    status,
                    stats.pages_fetched,
                    stats.items_seen,
                    stats.items_new,
                    stats.items_updated,
                    stats.http_errors,
                    (error or "")[:2000] or None,
                    run_id,
                ),
            )

    # ---- ghi một tin ------------------------------------------------------
    def _company_id(self, name: str | None, posting: JobPostingRaw) -> int | None:
        if not name:
            return None
        return self.conn.execute(
            """insert into core.companies (name, name_norm, website, logo_url)
               values (%s, %s, %s, %s)
               on conflict (name_norm) do update
                 set website = coalesce(core.companies.website, excluded.website),
                     logo_url = coalesce(core.companies.logo_url, excluded.logo_url)
               returning id""",
            (name, company_name_norm(name), posting.company_url, posting.company_logo),
        ).fetchone()[0]

    def _job_values(self, row: JobRow, company_id: int | None) -> dict[str, Any]:
        values = {k: v for k, v in row.columns.items() if k in self.columns}
        values["company_id"] = company_id
        return values

    def save(self, posting: JobPostingRaw, key: str, run_id: int) -> SaveResult:
        from psycopg.types.json import Jsonb

        row = build_job_row(posting, self.index, self.fx_rates, posting.fetched_at.date())
        digest = row.columns["content_hash"]
        with self.conn.transaction():
            snapshot_id = self.conn.execute(
                """insert into raw.job_snapshots
                     (source_id, source_job_id, url, run_id, fetched_at, http_status,
                      content_hash, payload, html_object_key)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                (
                    self._source_id,
                    posting.source_job_id,
                    posting.url,
                    run_id,
                    posting.fetched_at,
                    posting.http_status,
                    digest,
                    Jsonb(posting.json_ld),
                    key,
                ),
            ).fetchone()[0]

            existing = self.conn.execute(
                """select job_id, last_content_hash from core.job_sources
                    where source_id = %s and source_job_id = %s""",
                (self._source_id, posting.source_job_id),
            ).fetchone()

            if existing and bytes(existing[1] or b"") == digest:
                job_id, result = existing[0], "unchanged"
                self.conn.execute(
                    """update core.jobs set last_seen_at = now(), missed_runs = 0
                        where id = %s""",
                    (job_id,),
                )
            else:
                values = self._job_values(row, self._company_id(row.company_name, posting))
                if existing:
                    job_id, result = existing[0], "updated"
                    assignments = ", ".join(f"{col} = %({col})s" for col in values)
                    self.conn.execute(
                        f"""update core.jobs set {assignments},
                                   last_seen_at = now(), missed_runs = 0
                             where id = %(job_id)s""",
                        {**values, "job_id": job_id},
                    )
                else:
                    result = "new"
                    cols = ", ".join(values)
                    params = ", ".join(f"%({col})s" for col in values)
                    job_id = self.conn.execute(
                        f"insert into core.jobs ({cols}) values ({params}) returning id", values
                    ).fetchone()[0]
                self.conn.execute("delete from core.job_locations where job_id = %s", (job_id,))
                for code in row.province_codes:
                    self.conn.execute(
                        """insert into core.job_locations (job_id, province_code, address_raw)
                           values (%s, %s, %s)""",
                        (job_id, code, row.address_raw or None),
                    )

            self.conn.execute(
                """insert into core.job_sources
                     (source_id, source_job_id, job_id, url, last_snapshot_id, last_content_hash)
                   values (%s, %s, %s, %s, %s, %s)
                   on conflict (source_id, source_job_id) do update
                     set last_seen_at = now(), url = excluded.url, is_active = true,
                         last_snapshot_id = excluded.last_snapshot_id,
                         last_content_hash = excluded.last_content_hash""",
                (self._source_id, posting.source_job_id, job_id, posting.url, snapshot_id, digest),
            )
        return result

    def close(self) -> None:
        self.conn.close()
