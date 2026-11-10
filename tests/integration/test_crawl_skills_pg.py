"""S2-D06: sau mỗi lượt crawl, tin mới / đổi nội dung tự có tỉnh, lương, section và kỹ năng.

Bỏ qua nếu không đặt TEST_DATABASE_URL (KHÔNG dùng Supabase production). PgStore commit thật
nên test tự xóa dữ liệu của mình khi xong.
"""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingestion.crawl import label_skills_after_crawl
from ingestion.jsonld import find_job_posting, parse_job_posting
from ingestion.store import PgStore, RunStats

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="cần TEST_DATABASE_URL trỏ tới DB thử")
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "crawl" / "itviec_job.html"


def _posting(job_id: str):
    item = find_job_posting(FIXTURE.read_text(encoding="utf-8"))
    return parse_job_posting(
        item,
        source="itviec",
        source_job_id=job_id,
        url=f"https://itviec.com/it-jobs/d06-{job_id}",
        fetched_at=datetime.now(UTC),
    )


@pytest.fixture
def store():
    s = PgStore(DSN)
    if not s.conn.execute("select to_regclass('core.job_skills') is not null").fetchone()[0]:
        pytest.skip("DB thử thiếu schema")
    from skillkit.levels.db import has_levels_schema

    if not has_levels_schema(s.conn):
        s.close()
        pytest.skip("DB thử chưa chạy 0005_job_skill_levels.sql")
    s.conn.commit()
    yield s
    for job_id in s.changed_job_ids:  # dọn dữ liệu test
        s.conn.execute("delete from core.job_sources where job_id = %s", (job_id,))
        s.conn.execute("delete from core.jobs where id = %s", (job_id,))
    s.conn.commit()
    s.close()


def _skills(conn, job_id: int) -> dict[str, str]:
    return dict(
        conn.execute(
            "select s.slug, js.level::text from core.job_skills js "
            "join ref.skills s on s.id = js.skill_id where js.job_id = %s",
            (job_id,),
        ).fetchall()
    )


def test_new_job_gets_everything_after_crawl(store):
    source_job_id = f"d06-{datetime.now().timestamp():.0f}"
    run_id = store.start_run("itviec", None, "daily")
    posting = _posting(source_job_id)
    assert store.save(posting, "crawl/itviec/d06.html.gz", run_id) == "new"
    assert store.save(posting, "crawl/itviec/d06.html.gz", run_id) == "unchanged"
    store.finish_run(run_id, RunStats(items_seen=2, items_new=1), "success", None)
    [job_id] = store.changed_job_ids  # lần "unchanged" không thêm vào

    assert label_skills_after_crawl(store)
    conn = store.conn
    skills = _skills(conn, job_id)
    assert skills.get("java") == "required" and skills.get("spring_boot") == "required"

    has_province, salary_status, has_section = conn.execute(
        """select exists (select 1 from core.job_locations l where l.job_id = j.id),
                  j.salary_status, j.requirements is not null or j.description is not null
             from core.jobs j where j.id = %s""",
        (job_id,),
    ).fetchone()
    assert has_province and salary_status is not None and has_section

    # Lượt sau không có gì đổi: không gắn lại (labeled_at giữ nguyên).
    before = conn.execute(
        "select max(labeled_at) from core.job_skills where job_id = %s", (job_id,)
    ).fetchone()[0]
    store.changed_job_ids.clear()
    try:
        assert label_skills_after_crawl(store)
    finally:
        store.changed_job_ids.append(job_id)  # để fixture dọn
    after = conn.execute(
        "select max(labeled_at) from core.job_skills where job_id = %s", (job_id,)
    ).fetchone()[0]
    assert after == before


def test_skills_step_failure_does_not_lose_crawl(store, monkeypatch):
    source_job_id = f"d06e-{datetime.now().timestamp():.0f}"
    run_id = store.start_run("itviec", None, "daily")
    store.save(_posting(source_job_id), "crawl/itviec/d06e.html.gz", run_id)
    store.finish_run(run_id, RunStats(items_seen=1, items_new=1), "success", None)

    def boom(*args, **kwargs):
        raise RuntimeError("lỗi giả")

    monkeypatch.setattr("skillkit.levels.db.label_and_write", boom)
    assert label_skills_after_crawl(store) is False
    [job_id] = store.changed_job_ids
    assert store.conn.execute("select 1 from core.jobs where id = %s", (job_id,)).fetchone()
