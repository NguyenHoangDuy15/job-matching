"""Khử trùng trên Postgres: trùng chính xác cho tin cũ (S3-T03) và gần trùng (S3-T04).

Tin mới crawl được khử trùng ngay trong PgStore.save. Module này dành cho dữ liệu đã có:
  1. Điền core.job_sources.url_norm còn trống
  2. Tính lại core.jobs.content_hash theo dedup hash (ingestion.dedup)
  3. Gộp các tin chuẩn cùng url_norm, hoặc cùng dedup hash mà đều đang mở,
     bằng core.merge_jobs (migration 0011): giữ tin id nhỏ nhất, đóng tin còn lại.
Gần trùng: run_near_dedup (ingestion.near_dedup), chạy sau mỗi lượt crawl.
Gọi tay qua scripts/dedup_exact.py và scripts/dedup_near.py.
"""

from dataclasses import dataclass, field

from ingestion.dedup import canonical_url, dedup_hash
from ingestion.near_dedup import JobDoc, find_near_duplicates

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


# ---- Gần trùng (S3-T04) --------------------------------------------------------------------
_OPEN_DOCS_SQL = """
select j.id, j.company_id,
       coalesce(array_agg(l.province_code) filter (where l.province_code is not null), '{}'),
       j.title,
       coalesce(j.jd_text,
                concat_ws(E'\\n', j.description, j.requirements, j.preferred, j.benefits))
from core.jobs j
left join core.job_locations l on l.job_id = j.id
where j.origin = 'crawled' and j.status = 'open' and j.duplicate_of is null
group by j.id
"""


@dataclass
class NearReport:
    compared: int = 0
    merged: int = 0
    queued: int = 0
    skipped_distinct: int = 0  # admin đã xác nhận là hai tin khác nhau
    stale_removed: int = 0  # cặp chờ có tin đã đóng
    samples: list[tuple[int, int, float, str]] = field(default_factory=list)


def load_open_docs(conn) -> list[JobDoc]:
    return [
        JobDoc(id=r[0], company_id=r[1], provinces=frozenset(r[2]), title=r[3], text=r[4] or "")
        for r in conn.execute(_OPEN_DOCS_SQL)
    ]


def run_near_dedup(conn) -> NearReport:
    """Tìm cặp gần trùng giữa các tin đang mở; gộp cặp ≥ 0,85 đủ chắc, đưa cặp còn lại vào
    core.dedup_candidates (status pending). Chạy trong transaction hiện tại của conn."""
    report = NearReport()
    docs = load_open_docs(conn)
    report.compared = len(docs)
    pairs = find_near_duplicates(docs)
    distinct = {
        (a, b)
        for a, b in conn.execute(
            "select job_a, job_b from core.dedup_candidates where status = 'distinct'"
        )
    }

    def root(job_id: int) -> int:
        return conn.execute(
            "select coalesce(duplicate_of, id) from core.jobs where id = %s", (job_id,)
        ).fetchone()[0]

    # Gộp trước (giống nhất trước), rồi mới xếp hàng chờ theo tin còn lại sau khi gộp
    for pair in (p for p in pairs if p.decision == "merge"):
        if (pair.job_a, pair.job_b) in distinct:
            report.skipped_distinct += 1
            continue
        a, b = root(pair.job_a), root(pair.job_b)
        if a == b:
            continue
        merge_jobs(conn, min(a, b), max(a, b))
        report.merged += 1
        report.samples.append((min(a, b), max(a, b), pair.similarity, "merge"))

    for pair in (p for p in pairs if p.decision == "review"):
        a, b = sorted((root(pair.job_a), root(pair.job_b)))
        if a == b:
            continue
        if (a, b) in distinct:
            report.skipped_distinct += 1
            continue
        inserted = conn.execute(
            """insert into core.dedup_candidates (job_a, job_b, similarity)
               values (%s, %s, %s)
               on conflict (job_a, job_b) do update set similarity = excluded.similarity
                 where core.dedup_candidates.status = 'pending'
               returning (xmax = 0)""",
            (a, b, pair.similarity),
        ).fetchone()
        if inserted is not None:
            report.queued += 1
            report.samples.append((a, b, pair.similarity, "review"))

    # Cặp đang chờ mà một tin đã đóng (hết hạn, bị gỡ, bị gộp): admin không cần xét nữa
    report.stale_removed = conn.execute(
        """delete from core.dedup_candidates c
            where c.status = 'pending'
              and exists (select 1 from core.jobs j
                           where j.id in (c.job_a, c.job_b) and j.status <> 'open')"""
    ).rowcount
    return report
