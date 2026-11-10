"""S2-T06: tự đóng tin hết hạn / bị gỡ trên Postgres thật (cần migration 0004).

Bỏ qua nếu không đặt TEST_DATABASE_URL. Chỉ chạy với DB thử, KHÔNG dùng Supabase production.
"""

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from ingestion.jsonld import find_job_posting, parse_job_posting
from ingestion.store import PgStore

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="cần TEST_DATABASE_URL trỏ tới DB thử")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "crawl"
_seq = iter(range(10**6))


def _posting(job_id: str, source: str = "itviec", **changes):
    item = find_job_posting((FIXTURES / "itviec_job.html").read_text(encoding="utf-8"))
    posting = parse_job_posting(
        item,
        source=source,
        source_job_id=job_id,
        url=f"https://example.test/{source}/{job_id}",
        fetched_at=datetime.now(UTC),
    )
    # Mỗi tin một tiêu đề riêng để dễ tìm trong api.v_open_jobs.
    return posting.model_copy(update={"title": f"T06 {job_id}", **changes})


def _new_id(prefix: str) -> str:
    return f"{prefix}{datetime.now().timestamp():.0f}{next(_seq)}"


@pytest.fixture
def store():
    s = PgStore(DSN)
    if not s.can_close:
        s.close()
        pytest.skip("DB thử chưa chạy db/migrations/0004_close_stale_jobs.sql")
    yield s
    s.close()


def _job(store, job_id: str, source_id: int = 2):
    row = store.conn.execute(
        """select j.id, j.status::text, j.close_reason, j.closed_at is not null, j.missed_runs,
                  s.is_active, s.missed_runs
             from core.job_sources s join core.jobs j on j.id = s.job_id
            where s.source_id = %s and s.source_job_id = %s""",
        (source_id, job_id),
    ).fetchone()
    store.conn.commit()
    return dict(
        zip(
            ("id", "status", "reason", "has_closed_at", "missed", "src_active", "src_missed"),
            row,
            strict=True,
        )
    )


def _in_open_view(store, title: str) -> bool:
    found = store.conn.execute(
        "select count(*) from api.v_open_jobs where title = %s", (title,)
    ).fetchone()[0]
    store.conn.commit()
    return found == 1


def _run(store, saves=(), source="itviec", source_id=2):
    """Một lượt crawl giả: ghi các tin trong `saves`, trả run_id."""
    store.conn.execute("select pg_sleep(0.02)")  # last_seen_at của lượt trước < started_at lượt này
    store.conn.commit()
    run_id = store.start_run(source, source_id, "manual")
    for posting in saves:
        store.save(posting, None, run_id)
    return run_id


def test_missing_three_full_sweeps_closes_then_reappearing_reopens(store):
    a, b = _posting(_new_id("a")), _posting(_new_id("b"))
    _run(store, [a, b])
    assert _in_open_view(store, b.title)

    for expected_missed in (1, 2):
        run_id = _run(store, [a])  # b không còn trong danh sách
        assert store.mark_missing(run_id) == 0
        state = _job(store, b.source_job_id)
        assert (state["status"], state["src_missed"], state["missed"]) == (
            "open",
            expected_missed,
            expected_missed,
        )

    run_id = _run(store, [a])
    assert store.mark_missing(run_id) == 1  # lượt vắng thứ 3 → đóng
    state = _job(store, b.source_job_id)
    assert (state["status"], state["reason"], state["has_closed_at"]) == ("closed", "missing", True)
    assert state["src_active"] is False
    assert not _in_open_view(store, b.title)  # ẩn khỏi web...
    assert _job(store, a.source_job_id)["status"] == "open"  # ...tin vẫn gặp thì không bị đụng
    snapshots = store.conn.execute(
        "select count(*) from raw.job_snapshots where source_id = 2 and source_job_id = %s",
        (b.source_job_id,),
    ).fetchone()[0]
    store.conn.commit()
    assert snapshots == 1  # lịch sử còn nguyên

    _run(store, [a, b])  # b xuất hiện lại, nội dung không đổi
    state = _job(store, b.source_job_id)
    assert (state["status"], state["reason"], state["has_closed_at"]) == ("open", None, False)
    assert (state["src_active"], state["src_missed"], state["missed"]) == (True, 0, 0)
    assert _in_open_view(store, b.title)


def test_seen_again_resets_missed_counter(store):
    a = _posting(_new_id("r"))
    _run(store, [a])
    store.mark_missing(_run(store))
    store.mark_missing(_run(store))
    assert _job(store, a.source_job_id)["src_missed"] == 2
    _run(store, [a])
    assert _job(store, a.source_job_id)["src_missed"] == 0
    store.mark_missing(_run(store))
    assert _job(store, a.source_job_id)["status"] == "open"  # không cộng dồn qua lần gặp lại


def test_gone_closes_immediately(store):
    a = _posting(_new_id("g"))
    _run(store, [a])
    assert store.mark_gone(a.source_job_id) == 1
    state = _job(store, a.source_job_id)
    assert (state["status"], state["reason"], state["src_active"]) == ("closed", "gone", False)
    assert not _in_open_view(store, a.title)
    assert store.mark_gone(a.source_job_id) == 0  # gọi lại không đổi gì
    assert store.mark_gone("khong-ton-tai") == 0


def test_valid_through_passed_becomes_expired(store):
    a = _posting(_new_id("e"), valid_through=date.today() + timedelta(days=5))
    _run(store, [a])
    job_id = _job(store, a.source_job_id)["id"]
    # Thời gian trôi: hạn nộp lùi về hôm qua, nội dung nguồn không đổi.
    store.conn.execute(
        "update core.jobs set valid_through = current_date - 1 where id = %s", (job_id,)
    )
    store.conn.commit()
    assert store.close_stale() >= 1
    state = _job(store, a.source_job_id)
    assert (state["status"], state["reason"], state["has_closed_at"]) == (
        "expired",
        "expired",
        True,
    )
    assert not _in_open_view(store, a.title)
    kept = store.conn.execute(
        "select title, jd_text is not null from core.jobs where id = %s", (job_id,)
    ).fetchone()
    store.conn.commit()
    assert kept == (a.title, True)  # dòng và nội dung vẫn còn trong core.jobs


def test_job_with_second_source_stays_open(store):
    job_id = _new_id("m")
    a = _posting(job_id)
    _run(store, [a])
    core_id = _job(store, job_id)["id"]
    # Cùng tin đó còn được theo dõi ở nguồn VietnamWorks (đã gộp trùng).
    store.conn.execute(
        """insert into core.job_sources (source_id, source_job_id, job_id, url)
           values (1, %s, %s, 'https://example.test/vnw')""",
        (job_id, core_id),
    )
    store.conn.commit()
    assert store.mark_gone(job_id) == 0  # ITviec gỡ tin, nhưng VietnamWorks vẫn còn
    state = _job(store, job_id)
    assert (state["status"], state["src_active"]) == ("open", False)
    assert _in_open_view(store, a.title)


def test_changed_content_reopens_closed_job(store):
    a = _posting(_new_id("c"))
    _run(store, [a])
    store.mark_gone(a.source_job_id)
    edited = a.model_copy(update={"description_text": a.description_text + "\nBổ sung"})
    _run(store, [edited])
    state = _job(store, a.source_job_id)
    assert (state["status"], state["reason"], state["has_closed_at"]) == ("open", None, False)
