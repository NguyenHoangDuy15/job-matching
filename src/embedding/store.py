"""Ghi vector tin tuyển dụng vào core.job_chunks (S3-D07). Kết nối bằng DATABASE_URL (RLS của
job_chunks chỉ cho service_role / chủ DB), giống bước gắn kỹ năng sau crawl.

Tin cần làm = tin đang mở mà tập đoạn (section, số thứ tự, md5 nội dung) hoặc model khác với đoạn
đang lưu: tin mới, tin đổi nội dung, thẻ kỹ năng đổi (đoạn summary đổi), đổi model. Đoạn không đổi
thì không gọi model (không tốn quota). Mỗi nhóm tin ghi trong một giao dịch: xóa đoạn cũ → chèn mới.
"""

import hashlib
from collections import Counter
from collections.abc import Iterable

from embedding.chunker import Chunk, JobText, TokenCounter, bge_m3_counter, job_chunks
from embedding.embedder import Embedder, EmbedderError

OPEN = (
    "j.origin = 'crawled' and j.status = 'open' "
    "and (j.valid_through is null or j.valid_through >= current_date)"
)
GROUP_JOBS = 20  # số tin mỗi lần gọi model + mỗi giao dịch ghi

_JOBS_SQL = """
select j.id, j.title, c.name, j.seniority::text, j.work_mode::text,
       j.description, j.requirements, j.preferred, j.jd_text,
       coalesce((select array_agg(s.name order by s.name) from core.job_skills k
                  join ref.skills s on s.id = k.skill_id
                 where k.job_id = j.id and k.level = 'required'), '{{}}'),
       coalesce((select array_agg(s.name order by s.name) from core.job_skills k
                  join ref.skills s on s.id = k.skill_id
                 where k.job_id = j.id and k.level = 'preferred'), '{{}}')
from core.jobs j
left join core.companies c on c.id = j.company_id
where {where}
order by j.id
"""


def _vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def digest(chunks: Iterable[Chunk], model: str) -> tuple:
    return (
        model,
        tuple(sorted((c.section, c.chunk_no, _md5(c.content)) for c in chunks)),
    )


def load_jobs(conn, ids: list[int] | None = None) -> list[tuple[int, JobText]]:
    where = "j.id = any(%(ids)s)" if ids is not None else OPEN
    rows = conn.execute(_JOBS_SQL.format(where=where), {"ids": ids or []}).fetchall()
    out = []
    for jid, title, company, seniority, mode, desc, req, pref, jd, req_s, pref_s in rows:
        out.append(
            (
                jid,
                JobText(
                    title=title,
                    company=company,
                    seniority=seniority,
                    work_mode=mode,
                    skills_required=tuple(req_s),
                    skills_preferred=tuple(pref_s),
                    sections={"description": desc, "requirements": req, "preferred": pref},
                    jd_text=jd,
                ),
            )
        )
    return out


def load_existing(conn, job_ids: list[int]) -> dict[int, tuple]:
    rows = conn.execute(
        "select job_id, section, chunk_no, md5(content), model from core.job_chunks "
        "where job_id = any(%s)",
        (job_ids,),
    ).fetchall()
    by_job: dict[int, list] = {}
    models: dict[int, str] = {}
    for jid, section, no, md5, model in rows:
        by_job.setdefault(jid, []).append((section, no, md5))
        models[jid] = model
    return {jid: (models[jid], tuple(sorted(v))) for jid, v in by_job.items()}


def write_chunks(conn, job_id: int, chunks: list[Chunk], vectors: list[list[float]], model: str):
    conn.execute("delete from core.job_chunks where job_id = %s", (job_id,))
    with conn.cursor() as cur:
        cur.executemany(
            "insert into core.job_chunks (job_id, section, chunk_no, content, embedding, model) "
            "values (%s, %s, %s, %s, %s::extensions.halfvec, %s)",
            [
                (job_id, c.section, c.chunk_no, c.content, _vector_literal(v), model)
                for c, v in zip(chunks, vectors, strict=True)
            ],
        )


def embed_jobs(
    conn,
    embedder: Embedder,
    *,
    ids: list[int] | None = None,
    limit: int | None = None,
    apply: bool = True,
    count: TokenCounter | None = None,
) -> Counter:
    """Tính, ghi vector cho các tin cần làm. Lỗi model (hết quota…): dừng gọn, giữ phần đã ghi."""
    count = count or bge_m3_counter()
    stats: Counter = Counter()
    jobs = load_jobs(conn, ids)
    existing = load_existing(conn, [jid for jid, _ in jobs])
    todo = []
    for jid, job in jobs:
        chunks = job_chunks(job, count)
        stats["tin"] += 1
        if not chunks:
            stats["tin_rong"] += 1
            continue
        if existing.get(jid) != digest(chunks, embedder.model):
            todo.append((jid, chunks))
    stats["can_lam"] = len(todo)
    if limit is not None:
        todo = todo[:limit]
    stats["doan_can_lam"] = sum(len(c) for _, c in todo)
    if not apply:
        return stats
    for i in range(0, len(todo), GROUP_JOBS):
        group = todo[i : i + GROUP_JOBS]
        texts = [c.content for _, chunks in group for c in chunks]
        try:
            vectors = embedder.embed(texts)
        except EmbedderError as e:
            stats["dung_vi"] = 1
            stats[f"loi: {e}"] = 1
            conn.rollback()
            break
        pos = 0
        for jid, chunks in group:
            write_chunks(conn, jid, chunks, vectors[pos : pos + len(chunks)], embedder.model)
            pos += len(chunks)
            stats["da_ghi_tin"] += 1
            stats["da_ghi_doan"] += len(chunks)
        conn.commit()
    return stats


def prune_closed(conn, days: int = 30) -> int:
    """Xóa đoạn của tin đã đóng / hết hạn quá `days` ngày (giữ DB miễn phí nhỏ)."""
    cur = conn.execute(
        """delete from core.job_chunks c using core.jobs j
            where j.id = c.job_id
              and ((j.status <> 'open' and coalesce(j.closed_at, j.last_seen_at)
                                           < now() - make_interval(days => %(d)s))
                   or j.valid_through < current_date - %(d)s)""",
        {"d": days},
    )
    conn.commit()
    return cur.rowcount


def coverage_report(conn, model: str | None = None) -> dict:
    """Độ phủ (AC S3-D07: 100% tin đang mở có vector) + dung lượng bảng."""
    total, covered, chunks = conn.execute(
        f"""select count(*),
                   count(*) filter (where exists (select 1 from core.job_chunks c
                       where c.job_id = j.id and (%(m)s::text is null or c.model = %(m)s))),
                   coalesce(sum((select count(*) from core.job_chunks c where c.job_id = j.id)), 0)
              from core.jobs j where {OPEN}""",
        {"m": model},
    ).fetchone()
    models = dict(conn.execute("select model, count(*) from core.job_chunks group by 1").fetchall())
    size = conn.execute("select pg_total_relation_size('core.job_chunks')").fetchone()[0]
    return {
        "open_jobs": total,
        "with_vectors": covered,
        "pct": round(100 * covered / total, 1) if total else 0.0,
        "chunks_open": int(chunks),
        "avg_chunks": round(chunks / total, 1) if total else 0.0,
        "models": models,
        "table_mb": round(size / 1024 / 1024, 1),
    }
