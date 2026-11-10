"""S2-T03: ghi tin vào Postgres thật (schema.sql v2.0 + seed + fx_rates.sql).

Bỏ qua nếu không đặt TEST_DATABASE_URL, nên CI hiện tại không chạy file này.
Chạy tay với một DB thử (KHÔNG dùng Supabase production):
    TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres uv run pytest tests/integration
"""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingestion.jsonld import find_job_posting, parse_job_posting
from ingestion.store import PgStore, RunStats

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="cần TEST_DATABASE_URL trỏ tới DB thử")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "crawl"


def _posting(job_id: str, name: str = "itviec_job.html"):
    item = find_job_posting((FIXTURES / name).read_text(encoding="utf-8"))
    return parse_job_posting(
        item,
        source="itviec",
        source_job_id=job_id,
        url=f"https://itviec.com/it-jobs/test-{job_id}",
        fetched_at=datetime.now(UTC),
    )


@pytest.fixture
def store():
    s = PgStore(DSN)
    yield s
    s.close()


def test_new_unchanged_updated_cycle(store):
    job_id = f"t{datetime.now().timestamp():.0f}"
    run_id = store.start_run("itviec", None, "manual")

    first = _posting(job_id)
    assert store.save(first, "crawl/itviec/test.html.gz", run_id) == "new"
    assert store.save(_posting(job_id), "crawl/itviec/test.html.gz", run_id) == "unchanged"
    edited = first.model_copy(update={"description_text": first.description_text + "\nMới"})
    assert store.save(edited, "crawl/itviec/test.html.gz", run_id) == "updated"

    stats = RunStats(pages_fetched=1, items_seen=3, items_new=1, items_updated=1)
    store.finish_run(run_id, stats, "success", None)

    conn = store.conn
    job = conn.execute(
        """select j.id, j.title, j.status, j.work_mode, j.search_tsv is not null,
                  c.name_norm, j.salary_status
             from core.job_sources s join core.jobs j on j.id = s.job_id
             left join core.companies c on c.id = j.company_id
            where s.source_id = 2 and s.source_job_id = %s""",
        (job_id,),
    ).fetchone()
    assert job[1] == "Backend Developer (Java, Spring Boot)"
    assert job[2] == "open" and job[3] == "onsite" and job[4] is True
    assert job[5] == "cong nghe a"
    assert job[6] == "missing"
    provinces = conn.execute(
        "select province_code from core.job_locations where job_id = %s", (job[0],)
    ).fetchall()
    assert provinces == [(79,)]
    snapshots = conn.execute(
        "select count(*) from raw.job_snapshots where source_id = 2 and source_job_id = %s",
        (job_id,),
    ).fetchone()[0]
    assert snapshots == 3  # mỗi lần tải giữ một bản gốc, không ghi đè
    run = conn.execute(
        "select status, items_new, finished_at is not null from ops.crawl_runs where id = %s",
        (run_id,),
    ).fetchone()
    assert run == ("success", 1, True)
    # search_jobs không dấu tìm ra tin vừa ghi
    hits = conn.execute(
        "select title from api.search_jobs(q => 'spring boot', provinces => array[79]::smallint[])"
    ).fetchall()
    conn.commit()
    assert ("Backend Developer (Java, Spring Boot)",) in hits


def test_vnw_salary_columns_written(store):
    job_id = f"v{datetime.now().timestamp():.0f}"
    store._source_id = 1
    run_id = store.start_run("vietnamworks", 1, "manual")
    posting = _posting(job_id, "vietnamworks_job.html").model_copy(
        update={"source": "vietnamworks"}
    )
    assert store.save(posting, "crawl/vietnamworks/test.html.gz", run_id) == "new"
    row = store.conn.execute(
        """select j.salary_min_vnd, j.salary_max_vnd, j.status, j.work_mode
             from core.job_sources s join core.jobs j on j.id = s.job_id
            where s.source_id = 1 and s.source_job_id = %s""",
        (job_id,),
    ).fetchone()
    store.conn.commit()
    assert row == (25_000_000, 40_000_000, "expired", "remote")
