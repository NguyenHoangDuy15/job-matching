"""Khử trùng trên Postgres: tính lại khóa cho tin cũ và gộp tin trùng (S3-T03).

Tin mới crawl được khử trùng ngay trong PgStore.save. Module này dành cho dữ liệu đã có:
  1. Điền core.job_sources.url_norm còn trống
  2. Tính lại core.jobs.content_hash theo dedup hash (ingestion.dedup)
  3. Gộp các tin chuẩn cùng url_norm, hoặc cùng dedup hash mà đều đang mở,
     bằng core.merge_jobs (migration 0011): giữ tin id nhỏ nhất, đóng tin còn lại.
Gọi qua scripts/dedup_exact.py.
"""

from dataclasses import dataclass, field

from ingestion.dedup import canonical_url, dedup_hash

# Cùng các trường store.build_job_row dùng: title, công ty (name_norm), tỉnh, mô tả gốc (jd_text).
_JOBS_SQL = """
select j.id, j.title, c.name_norm,
       coalesce(array_agg(l.province_code) filter (where l.province_code is not null), '{}'),
       coalesce(j.jd_text,
                concat_ws(E'\\n', j.description, j.requirements, j.preferred, j.benefits)),
       j.content_hash
from core.jobs j
left join core.companies c on c.id = j.company_id
left join core.job_locations l on l.job_id = j.id
where j.origin = 'crawled' and j.duplicate_of is null
group by j.id, c.name_norm
"""

# Nhóm cùng URL: tin giữ lại ưu tiên tin đang mở, rồi id nhỏ nhất.
_URL_GROUPS_SQL = """
select array_agg(distinct s.job_id)
from core.job_sources s join core.jobs j on j.id = s.job_id
where s.url_norm is not null and j.duplicate_of is null
group by s.url_norm
having count(distinct s.job_id) > 1
"""

_HASH_GROUPS_SQL = """
select array_agg(id order by id)
from core.jobs
where origin = 'crawled' and status = 'open' and duplicate_of is null and content_hash is not null
group by content_hash
having count(*) > 1
"""

# Còn trùng chính xác sau khi gộp (nghiệm thu S3-T03: phải bằng 0)
REMAINING_SQL = f"""
select (select count(*) from ({_URL_GROUPS_SQL}) u) + (select count(*) from ({_HASH_GROUPS_SQL}) h)
"""


@dataclass
class ExactReport:
    url_filled: int = 0
    hash_updated: int = 0
    url_groups: int = 0
    hash_groups: int = 0
    merged: int = 0
    remaining: int = 0
    samples: list[tuple[int, int, str]] = field(default_factory=list)  # (giữ, gộp, lý do)


def merge_jobs(conn, keep: int, dup: int) -> int:
    """core.merge_jobs (migration 0011); trả id tin giữ lại."""
    return conn.execute("select core.merge_jobs(%s, %s)", (keep, dup)).fetchone()[0]


def fill_url_norm(conn) -> int:
    rows = conn.execute(
        "select source_id, source_job_id, url from core.job_sources where url_norm is null"
    ).fetchall()
    with conn.cursor() as cur:
        cur.executemany(
            """update core.job_sources set url_norm = %s
                where source_id = %s and source_job_id = %s""",
            [(canonical_url(url), sid, sjid) for sid, sjid, url in rows],
        )
    return len(rows)


def refresh_content_hash(conn) -> int:
    updates = []
    for job_id, title, company_norm, provinces, text, old in conn.execute(_JOBS_SQL):
        new = dedup_hash(title, company_norm, provinces, text)
        if (bytes(old) if old is not None else None) != new:
            updates.append((new, job_id))
    with conn.cursor() as cur:
        cur.executemany("update core.jobs set content_hash = %s where id = %s", updates)
    return len(updates)


def _keeper(conn, ids: list[int]) -> int:
    return conn.execute(
        """select id from core.jobs where id = any(%s)
            order by (status = 'open') desc, id limit 1""",
        (ids,),
    ).fetchone()[0]


def _roots(conn, ids: list[int]) -> list[int]:
    """Tin đã bị gộp ở nhóm trước thay bằng tin giữ lại của nó (core.merge_jobs không để chuỗi)."""
    rows = conn.execute(
        "select distinct coalesce(duplicate_of, id) from core.jobs where id = any(%s)", (ids,)
    ).fetchall()
    return [r[0] for r in rows]


def merge_exact_duplicates(conn, report: ExactReport) -> None:
    for (group,) in conn.execute(_URL_GROUPS_SQL).fetchall():
        ids = _roots(conn, group)  # một tin có thể nằm ở hai nhóm URL (hai nguồn)
        if len(ids) < 2:
            continue
        report.url_groups += 1
        keep = _keeper(conn, ids)
        for dup in sorted(set(ids) - {keep}):
            keep = merge_jobs(conn, keep, dup)
            report.merged += 1
            report.samples.append((keep, dup, "url"))
    # Tính nhóm hash SAU khi gộp theo URL: tin đã bị gộp không còn duplicate_of null.
    for (ids,) in conn.execute(_HASH_GROUPS_SQL).fetchall():
        report.hash_groups += 1
        keep = ids[0]
        for dup in ids[1:]:
            keep = merge_jobs(conn, keep, dup)
            report.merged += 1
            report.samples.append((keep, dup, "hash"))


def backfill_exact(conn) -> ExactReport:
    """Chạy cả 3 bước trong transaction hiện tại của conn (người gọi commit hoặc rollback)."""
    report = ExactReport()
    report.url_filled = fill_url_norm(conn)
    report.hash_updated = refresh_content_hash(conn)
    merge_exact_duplicates(conn, report)
    report.remaining = conn.execute(REMAINING_SQL).fetchone()[0]
    return report
