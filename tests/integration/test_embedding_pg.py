"""S3-D07: ghi core.job_chunks (pgvector). Bỏ qua nếu không đặt TEST_DATABASE_URL.

Chạy trong transaction rồi rollback (KHÔNG dùng Supabase production).
"""

import os

import pytest

from embedding.embedder import FakeEmbedder
from embedding.store import coverage_report, embed_jobs, prune_closed

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="cần TEST_DATABASE_URL trỏ tới DB thử")


def words(text: str) -> int:
    return len(text.split()) + 2


class _Commitless:
    """Bọc kết nối: commit() thành no-op để test chạy trong một transaction rồi rollback."""

    def __init__(self, conn) -> None:
        self._c = conn

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def __getattr__(self, name):
        return getattr(self._c, name)


@pytest.fixture
def conn():
    import psycopg

    with psycopg.connect(DSN) as c, c.transaction(force_rollback=True):
        if not c.execute("select to_regclass('core.job_chunks')").fetchone()[0]:
            pytest.skip("DB thử chưa có core.job_chunks")
        c.execute(
            "update core.jobs set status = 'closed' where status = 'open'"
        )  # chỉ đếm tin test
        yield _Commitless(c)


def _job(conn, title: str, req: str) -> int:
    return conn.execute(
        "insert into core.jobs (title, title_norm, apply_url, requirements, origin, status) "
        "values (%s, %s, 'https://example.com/e', %s, 'crawled', 'open') returning id",
        (title, title.lower(), req),
    ).fetchone()[0]


def test_embed_rerun_change_coverage_and_prune(conn):
    a = _job(conn, "Backend Developer", "- Java Spring Boot\n- PostgreSQL")
    b = _job(conn, "Data Engineer", "- Airflow, dbt\n- BigQuery")
    emb = FakeEmbedder()

    first = embed_jobs(conn, emb, count=words)
    assert first["da_ghi_tin"] == 2
    report = coverage_report(conn, emb.model)
    assert (report["open_jobs"], report["with_vectors"], report["pct"]) == (2, 2, 100.0)

    again = embed_jobs(conn, emb, count=words)
    assert again["can_lam"] == 0  # không đổi gì → không gọi model

    conn.execute("update core.jobs set requirements = '- Java\n- Kafka' where id = %s", (a,))
    changed = embed_jobs(conn, emb, count=words)
    assert changed["can_lam"] == 1 and changed["da_ghi_tin"] == 1
    contents = [r[0] for r in conn.execute(
        "select content from core.job_chunks where job_id = %s and section = 'requirements'", (a,)
    ).fetchall()]  # fmt: skip
    assert contents == ["Backend Developer — Yêu cầu: - Java\n- Kafka"]

    # Truy vấn top-k bằng toán tử cosine của pgvector (index HNSW)
    vec = "[" + ",".join(map(str, emb.embed(["Backend Developer"])[0])) + "]"
    top = conn.execute(
        "select job_id from core.job_chunks "
        "order by embedding OPERATOR(extensions.<=>) %s::extensions.halfvec limit 1",
        (vec,),
    ).fetchone()[0]
    assert top in (a, b)

    conn.execute(
        "update core.jobs set status = 'closed', closed_at = now() - interval '40 days' "
        "where id = %s",
        (b,),
    )
    assert prune_closed(conn) >= 1
    assert (
        conn.execute("select count(*) from core.job_chunks where job_id = %s", (b,)).fetchone()[0]
        == 0
    )
