"""S3-T03: khử trùng chính xác trên Postgres thật (cần migration 0011).

Bỏ qua nếu không đặt TEST_DATABASE_URL. Chỉ chạy với DB thử, KHÔNG dùng Supabase production.
"""

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingestion.dedup_pg import REMAINING_SQL, backfill_exact
from ingestion.jsonld import find_job_posting, parse_job_posting
from ingestion.store import PgStore

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="cần TEST_DATABASE_URL trỏ tới DB thử")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "crawl"
ITVIEC, VNW = ("itviec", 2), ("vietnamworks", 1)


def _jd(tag: str) -> str:
    return (
        f"Mã nội bộ {tag}.\n"
        "Mô tả công việc:\n• Xây dựng pipeline dữ liệu bằng Python, Airflow và PostgreSQL.\n"
        "• Thiết kế mô hình dữ liệu cho hệ thống gợi ý việc làm hai chiều.\n"
        "Yêu cầu:\n- Tối thiểu 2 năm kinh nghiệm Data Engineer.\n"
        "- Thành thạo SQL; Spark là lợi thế.\n"
    )


def _posting(source: str, job_id: str, tag: str, **changes):
    item = find_job_posting((FIXTURES / "itviec_job.html").read_text(encoding="utf-8"))
    posting = parse_job_posting(
        item,
        source=source,
        source_job_id=job_id,
        url=f"https://{source}.example.test/jobs/{job_id}",
        fetched_at=datetime.now(UTC),
    )
    return posting.model_copy(
        update={"title": f"T03 Data Engineer {tag}", "description_text": _jd(tag), **changes}
    )


@pytest.fixture
def store():
    s = PgStore(DSN)
    if not s.can_dedup:
        s.close()
        pytest.skip("DB thử chưa chạy db/migrations/0011_exact_dedup.sql")
    yield s
    s.close()


def _save(store, source, posting) -> str:
    run_id = store.start_run(source[0], source[1], "manual")
    return store.save(posting, None, run_id)


def _jobs_with_title(store, title: str) -> list[tuple]:
    rows = store.conn.execute(
        """select j.id, j.status::text, j.close_reason, j.duplicate_of,
                  (select count(*) from core.job_sources s where s.job_id = j.id)
             from core.jobs j where j.title = %s order by j.id""",
        (title,),
    ).fetchall()
    store.conn.commit()
    return rows


def _job_of(store, source_id: int, source_job_id: str) -> int:
    job_id = store.conn.execute(
        "select job_id from core.job_sources where source_id = %s and source_job_id = %s",
        (source_id, source_job_id),
    ).fetchone()[0]
    store.conn.commit()
    return job_id


def test_same_posting_on_two_sources_is_one_job(store):
    tag = uuid.uuid4().hex[:8]
    a = _posting("itviec", f"a{tag}", tag)
    # VietnamWorks trình bày khác: chữ hoa, gạch đầu dòng, xuống dòng; khác mã, URL, hạn nộp
    b = _posting(
        "vietnamworks",
        f"b{tag}",
        tag,
        title=a.title.upper() + "  ",
        description_text=a.description_text.replace("• ", "- ").replace("\n", "\n\n"),
        valid_through=None,
    )
    assert _save(store, ITVIEC, a) == "new"
    changed = len(store.changed_job_ids)
    assert _save(store, VNW, b) == "duplicate"
    assert len(store.changed_job_ids) == changed  # không gắn lại kỹ năng / vector cho tin trùng
    assert _save(store, VNW, b) == "unchanged"  # lần sau nhận ra ngay bằng (nguồn, mã tin)

    jobs = _jobs_with_title(store, a.title)
    assert len(jobs) == 1 and jobs[0][4] == 2  # một tin chuẩn, hai nguồn
    assert _job_of(store, 1, b.source_job_id) == _job_of(store, 2, a.source_job_id)


def test_same_url_with_other_id_is_same_posting(store):
    tag = uuid.uuid4().hex[:8]
    a = _posting("itviec", f"u{tag}", tag)
    # Nạp lại từ file JSONL: mã tin khác nhưng cùng link (khác www, dấu /, query)
    b = a.model_copy(
        update={
            "source_job_id": f"jsonl-{tag}",
            "url": a.url.replace("https://", "http://www.") + "/?utm_source=x",
        }
    )
    assert _save(store, ITVIEC, a) == "new"
    assert _save(store, ITVIEC, b) == "unchanged"
    assert _job_of(store, 2, b.source_job_id) == _job_of(store, 2, a.source_job_id)


def test_closed_job_is_not_reused(store):
    tag = uuid.uuid4().hex[:8]
    a = _posting("itviec", f"c{tag}", tag)
    assert _save(store, ITVIEC, a) == "new"
    store.mark_gone(a.source_job_id)  # tin bị gỡ → closed
    b = _posting("vietnamworks", f"c{tag}", tag)
    assert _save(store, VNW, b) == "new"  # đăng lại sau khi đóng là đợt tuyển mới


def test_short_description_is_never_merged(store):
    tag = uuid.uuid4().hex[:8]
    a = _posting("itviec", f"s{tag}", tag, description_text="Java, Spring")
    b = _posting("vietnamworks", f"s{tag}", tag, description_text="Java, Spring")
    assert _save(store, ITVIEC, a) == "new"
    assert _save(store, VNW, b) == "new"


def test_backfill_merges_old_duplicates(store):
    """Tin nạp trước migration 0011 (không khử trùng lúc ghi) được gộp bằng backfill_exact."""
    tag = uuid.uuid4().hex[:8]
    a = _posting("itviec", f"o{tag}", tag)
    b = _posting("vietnamworks", f"o{tag}", tag)
    store.can_dedup = False  # giả lập crawler cũ
    assert _save(store, ITVIEC, a) == "new"
    assert _save(store, VNW, b) == "new"
    store.can_dedup = True
    keep, dup = _job_of(store, 2, a.source_job_id), _job_of(store, 1, b.source_job_id)
    assert keep < dup

    # Người dùng đã lưu tin bị gộp: chuyển sang tin giữ lại
    user = store.conn.execute("select id from auth.users order by id limit 1").fetchone()
    if user is None:
        user = store.conn.execute(
            "insert into auth.users (id, email) values (gen_random_uuid(), %s) returning id",
            (f"t03-{tag}@x.vn",),
        ).fetchone()
    store.conn.execute(
        "insert into app.saved_jobs (user_id, job_id) values (%s, %s)", (user[0], dup)
    )
    store.conn.commit()

    with store.conn.transaction():
        report = backfill_exact(store.conn)
    assert report.merged >= 1 and report.remaining == 0
    assert (keep, dup, "hash") in report.samples

    jobs = {row[0]: row for row in _jobs_with_title(store, a.title)}
    assert jobs[keep][1:] == ("open", None, None, 2)
    assert jobs[dup][1:] == ("closed", "duplicate", keep, 0)
    saved = store.conn.execute(
        "select job_id from app.saved_jobs where user_id = %s and job_id in (%s, %s)",
        (user[0], keep, dup),
    ).fetchall()
    store.conn.commit()
    assert saved == [(keep,)]

    # Chạy lại: không còn gì để gộp
    with store.conn.transaction():
        again = backfill_exact(store.conn)
    assert again.merged == 0
    assert store.conn.execute(REMAINING_SQL).fetchone()[0] == 0
    store.conn.commit()
