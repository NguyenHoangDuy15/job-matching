"""S3-T04: gần trùng trên Postgres thật (cần migration 0011).

Bỏ qua nếu không đặt TEST_DATABASE_URL. Chỉ chạy với DB thử, KHÔNG dùng Supabase production.
"""

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingestion.dedup_pg import run_near_dedup
from ingestion.jsonld import find_job_posting, parse_job_posting
from ingestion.store import PgStore

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="cần TEST_DATABASE_URL trỏ tới DB thử")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "crawl"
SOURCES = {"itviec": 2, "vietnamworks": 1, "careerviet": 3}

BASE = (
    "Chúng tôi tìm Data Engineer xây dựng pipeline dữ liệu cho nền tảng thương mại điện tử. "
    "Bạn sẽ thiết kế luồng ETL bằng Python và Airflow, tối ưu truy vấn PostgreSQL, "
    "xây kho dữ liệu trên BigQuery, giám sát chất lượng dữ liệu hằng ngày, phối hợp với đội "
    "phân tích để đưa báo cáo lên Looker. Yêu cầu tối thiểu hai năm kinh nghiệm, thành thạo SQL, "
    "hiểu mô hình dữ liệu dạng sao, có kinh nghiệm Spark là lợi thế. Quyền lợi lương tháng 13, "
    "bảo hiểm sức khỏe, làm việc hybrid hai ngày mỗi tuần tại văn phòng quận 1."
)
EXTRA = (
    " Môi trường trẻ trung năng động, đồng nghiệp thân thiện, được đào tạo bài bản và có lộ trình"
    " thăng tiến rõ ràng mỗi năm."
)


@pytest.fixture
def store():
    s = PgStore(DSN)
    if not s.can_dedup:
        s.close()
        pytest.skip("DB thử chưa chạy db/migrations/0011_exact_dedup.sql")
    yield s
    s.close()


def _save(store, source: str, tag: str, text: str) -> int:
    item = find_job_posting((FIXTURES / "itviec_job.html").read_text(encoding="utf-8"))
    job_id = f"{source[:3]}{uuid.uuid4().hex[:10]}"
    posting = parse_job_posting(
        item,
        source=source,
        source_job_id=job_id,
        url=f"https://{source}.example.test/jobs/{job_id}",
        fetched_at=datetime.now(UTC),
    ).model_copy(
        update={
            "title": "Data Engineer",
            "company_name": f"Công ty T04 {tag}",  # công ty riêng cho mỗi test
            "description_text": text,
            "valid_through": None,
        }
    )
    run_id = store.start_run(source, SOURCES[source], "manual")
    store.save(posting, None, run_id)
    row = store.conn.execute(
        "select job_id from core.job_sources where source_id = %s and source_job_id = %s",
        (SOURCES[source], job_id),
    ).fetchone()
    store.conn.commit()
    return row[0]


def _run(store):
    with store.conn.transaction():
        return run_near_dedup(store.conn)


def _job(store, job_id: int) -> tuple:
    row = store.conn.execute(
        "select status::text, close_reason, duplicate_of from core.jobs where id = %s", (job_id,)
    ).fetchone()
    store.conn.commit()
    return row


def _candidate(store, a: int, b: int):
    row = store.conn.execute(
        "select status, similarity from core.dedup_candidates where job_a = %s and job_b = %s",
        (min(a, b), max(a, b)),
    ).fetchone()
    store.conn.commit()
    return row


def test_merge_close_copy_and_queue_edited_copy(store):
    tag = uuid.uuid4().hex[:8]
    a = _save(store, "itviec", tag, BASE)
    b = _save(store, "vietnamworks", tag, BASE.replace("quận 1", "Quận 1, TP.HCM"))
    c = _save(store, "careerviet", tag, BASE + EXTRA)
    assert len({a, b, c}) == 3  # khác vài chữ: trùng chính xác (S3-T03) không bắt được

    report = _run(store)
    assert report.merged >= 1 and report.queued >= 1

    assert _job(store, a) == ("open", None, None)
    assert _job(store, b) == ("closed", "duplicate", a)
    sources = store.conn.execute(
        "select count(*) from core.job_sources where job_id = %s", (a,)
    ).fetchone()[0]
    store.conn.commit()
    assert sources == 2
    status, similarity = _candidate(store, a, c)
    assert status == "pending" and 0.70 <= similarity < 0.85
    assert _candidate(store, b, c) is None  # tin đã gộp không vào hàng chờ


def test_admin_distinct_is_not_requeued_and_closed_pairs_are_cleaned(store):
    tag = uuid.uuid4().hex[:8]
    a = _save(store, "itviec", tag, BASE)
    c = _save(store, "careerviet", tag, BASE + EXTRA)
    _run(store)
    assert _candidate(store, a, c)[0] == "pending"

    # Admin xác nhận hai tin khác nhau: lượt sau không đưa lại vào hàng chờ, không gộp
    store.conn.execute(
        "update core.dedup_candidates set status = 'distinct' where job_a = %s and job_b = %s",
        (min(a, c), max(a, c)),
    )
    store.conn.commit()
    report = _run(store)
    assert report.skipped_distinct >= 1
    assert _candidate(store, a, c)[0] == "distinct"
    assert _job(store, c) == ("open", None, None)

    # Cặp đang chờ mà một tin đã đóng thì được dọn
    tag2 = uuid.uuid4().hex[:8]
    x = _save(store, "itviec", tag2, BASE)
    y = _save(store, "careerviet", tag2, BASE + EXTRA)
    _run(store)
    assert _candidate(store, x, y)[0] == "pending"
    store.conn.execute(
        "update core.jobs set status = 'expired', close_reason = 'expired' where id = %s", (y,)
    )
    store.conn.commit()
    report = _run(store)
    assert report.stale_removed >= 1
    assert _candidate(store, x, y) is None
