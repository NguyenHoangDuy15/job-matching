"""Kho tin đang mở trong RAM cho API Top N (S4-D04): BM25 (K), ma trận vector (E), thông tin tin.

Ba phần nạp trong CÙNG một giao dịch REPEATABLE READ qua role chỉ đọc `matcher_ro`, nên cùng
một tập tin; `corpus_size` là N dùng tính phân vị K, E. API giữ snapshot bằng
`ranking.refresh.RefreshingIndex` (dựng lại mỗi giờ ở luồng nền).
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass, field
from datetime import date

from ranking.semantic import SemanticIndex
from retrieval.bm25 import KeywordIndex, load_open_jobs

_OPEN = (
    "j.origin = 'crawled' and j.status = 'open' "
    "and (j.valid_through is null or j.valid_through >= current_date)"
)
_META_SQL = f"""
select j.id, j.public_id::text, j.title, c.name, j.work_mode::text, j.valid_through, j.apply_url,
       j.years_exp_min::float8,
       coalesce(array_agg(l.province_code order by l.province_code)
                filter (where l.province_code is not null), '{{}}') as provinces,
       coalesce(array_agg(p.name order by l.province_code)
                filter (where p.name is not null), '{{}}') as province_names
  from core.jobs j
  left join core.companies c on c.id = j.company_id
  left join core.job_locations l on l.job_id = j.id
  left join ref.provinces p on p.code = l.province_code
 where {_OPEN}
 group by j.id, c.name
"""
_SKILLS_SQL = f"""
select js.job_id, s.slug, s.name, js.level::text
  from core.job_skills js
  join core.jobs j on j.id = js.job_id
  join ref.skills s on s.id = js.skill_id
 where {_OPEN} and js.level in ('required', 'preferred')
 order by js.job_id, js.level, s.slug
"""
_STILL_OPEN_SQL = f"select j.id from core.jobs j where j.id = any(%(ids)s) and {_OPEN}"


@dataclass(frozen=True)
class JobMeta:
    id: int
    public_id: str | None
    title: str
    company: str | None
    work_mode: str
    valid_through: date | None
    apply_url: str | None
    years_exp_min: float | None
    provinces: tuple[int, ...] = ()
    province_names: tuple[str, ...] = ()
    skills: tuple[tuple[str, str, str], ...] = ()  # (slug, tên, required | preferred)


@dataclass(frozen=True)
class Snapshot:
    jobs: dict[int, JobMeta]
    keyword: KeywordIndex
    semantic: SemanticIndex
    built_at: float = field(default_factory=time.time)
    load_seconds: float = 0.0

    @property
    def corpus_size(self) -> int:
        return len(self.jobs)


def load_snapshot(conn) -> Snapshot:
    """Đọc kho tin qua `conn` (matcher_ro). Giao dịch REPEATABLE READ: một ảnh chụp nhất quán."""
    import psycopg

    t = time.perf_counter()
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    with conn.transaction():
        meta_rows = conn.execute(_META_SQL).fetchall()
        skill_rows = conn.execute(_SKILLS_SQL).fetchall()
        docs = load_open_jobs(conn)
        semantic = SemanticIndex.from_db(conn)
    skills: dict[int, list[tuple[str, str, str]]] = {}
    for job_id, slug, name, level in skill_rows:
        skills.setdefault(job_id, []).append((slug, name, level))
    jobs = {
        r[0]: JobMeta(
            id=r[0],
            public_id=r[1],
            title=r[2],
            company=r[3],
            work_mode=r[4],
            valid_through=r[5],
            apply_url=r[6],
            years_exp_min=r[7],
            provinces=tuple(r[8]),
            province_names=tuple(r[9]),
            skills=tuple(skills.get(r[0], ())),
        )
        for r in meta_rows
    }
    keyword = KeywordIndex.build([d for d in docs if d.id in jobs])
    return Snapshot(jobs, keyword, semantic, load_seconds=time.perf_counter() - t)


class MatcherDB:
    """Kết nối chỉ đọc dùng lại giữa các request (kiểm tin còn mở) và để dựng snapshot."""

    def __init__(self, dsn: str, connect_timeout: int = 10):
        self.dsn = dsn
        self.connect_timeout = connect_timeout
        self._conn = None
        self._lock = threading.Lock()

    def connect(self):
        import psycopg

        return psycopg.connect(
            self.dsn,
            connect_timeout=self.connect_timeout,
            prepare_threshold=None,  # an toàn khi đi qua pooler Supavisor
            options="-c default_transaction_read_only=on",
        )

    def build_snapshot(self) -> Snapshot:
        with self.connect() as conn:
            return load_snapshot(conn)

    def warm(self) -> None:
        """Mở sẵn kết nối lúc khởi động: lượt Top N đầu không phải chờ mở kết nối (~0,5 s)."""
        with contextlib.suppress(Exception):  # lỗi mạng lúc khởi động: lượt đầu thử lại
            self.still_open([0])

    def still_open(self, ids: list[int]) -> set[int]:
        """Trong `ids`, các tin vẫn còn mở và còn hạn NGAY LÚC NÀY (snapshot có thể cũ ≤ 1 giờ)."""
        if not ids:
            return set()
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._conn is None or self._conn.closed:
                        self._conn = self.connect()
                        self._conn.autocommit = True
                    rows = self._conn.execute(_STILL_OPEN_SQL, {"ids": ids}).fetchall()
                    return {r[0] for r in rows}
                except Exception:
                    self._conn = None  # kết nối hỏng (pooler đóng): mở lại một lần
                    if attempt == 2:
                        raise
        return set()
