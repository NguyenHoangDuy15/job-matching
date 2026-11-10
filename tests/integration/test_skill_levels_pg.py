"""S2-D04: ghi core.job_skills (migration 0005). Bỏ qua nếu không đặt TEST_DATABASE_URL.

Chạy trong transaction rồi rollback, không để lại dữ liệu (KHÔNG dùng Supabase production).
"""

import os

import pytest

from skillkit.levels.db import has_levels_schema, label_jobs, skill_ids, write_job_skills
from skillkit.levels.pipeline import SkillLabeler

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="cần TEST_DATABASE_URL trỏ tới DB thử")

JD = """Mô tả công việc
- Phát triển API bằng Kafka
Yêu cầu
- Thành thạo Java, ưu tiên biết thêm Kotlin
Quyền lợi
- Được đào tạo AWS"""


@pytest.fixture
def conn():
    import psycopg

    with psycopg.connect(DSN) as c, c.transaction(force_rollback=True):
        if not has_levels_schema(c):
            pytest.skip("DB thử chưa chạy 0005_job_skill_levels.sql")
        if not c.execute("select 1 from ref.skills where slug = 'java'").fetchone():
            pytest.skip("DB thử chưa chạy db/seed/seed_skills.sql")
        yield c


def _levels(conn, job_id):
    rows = conn.execute(
        "select s.slug, js.level::text, js.extractor::text, js.section, js.source_detail "
        "from core.job_skills js join ref.skills s on s.id = js.skill_id where js.job_id = %s",
        (job_id,),
    ).fetchall()
    return {slug: rest for slug, *rest in rows}


def test_write_keeps_human_rows_and_removes_stale(conn):
    job_id = conn.execute(
        "insert into core.jobs (title, title_norm, apply_url, jd_text) "
        "values ('Test', 'test', 'https://example.com/levels', %s) returning id",
        (JD,),
    ).fetchone()[0]
    ids = skill_ids(conn)
    # Dòng sửa tay và một kỹ năng cũ không còn trong JD.
    conn.execute(
        "insert into core.job_skills (job_id, skill_id, level, extractor) values "
        "(%s, %s, 'preferred', 'human'), (%s, %s, 'required', 'dict')",
        (job_id, ids["java"], job_id, ids["python"]),
    )
    labeler = SkillLabeler.default(with_model=False)
    labeled = label_jobs(labeler, [(job_id, JD, None, None, None, None)])
    write_job_skills(conn, labeled, ids, labeler.model_version)

    got = _levels(conn, job_id)
    assert got["java"][:2] == ["preferred", "human"]  # không bị ghi đè
    assert got["kotlin"] == ["preferred", "dict", "requirements", "rule_mixed"]
    assert got["kafka"][0] == "mentioned"
    assert "python" not in got and "aws" not in got

    write_job_skills(conn, labeled, ids, labeler.model_version)  # chạy lại được
    assert _levels(conn, job_id) == got


def _open_job(conn, text: str) -> int:
    return conn.execute(
        "insert into core.jobs (title, title_norm, apply_url, jd_text, origin, status) "
        "values ('Backend', 'backend', 'https://example.com/d05', %s, 'crawled', 'open') "
        "returning id",
        (text,),
    ).fetchone()[0]


def test_stale_selection_and_report(conn):
    from skillkit.levels.db import coverage_report, label_and_write, select_jobs

    labeler = SkillLabeler.default(with_model=False)
    job_id = _open_job(conn, JD)
    ver = labeler.model_version

    def stale_ids():
        rows = select_jobs(conn, model_version=ver, only_open=True, stale=True)
        return {r[0] for r in rows}

    assert job_id in stale_ids()  # chưa gắn
    label_and_write(conn, labeler, select_jobs(conn, model_version=ver, ids=[job_id]))
    assert job_id not in stale_ids()  # đã gắn bằng bản hiện tại
    conn.execute("update core.job_skills set model_version = 'cu' where job_id = %s", (job_id,))
    assert job_id in stale_ids()  # luật/từ điển đổi → gắn lại

    report = coverage_report(conn)
    assert report["open_jobs"] >= 1 and report["with_skill_cards"] >= 1
    assert 0 < report["pct_with_cards"] <= 100


def test_web_view_and_search_skip_mentioned(conn):
    from skillkit.levels.db import label_and_write, select_jobs

    if not conn.execute("select to_regclass('api.v_job_skills')").fetchone()[0]:
        pytest.skip("DB thử chưa chạy 0006_job_skills_api.sql")
    labeler = SkillLabeler.default(with_model=False)
    job_id = _open_job(conn, JD)
    label_and_write(
        conn, labeler, select_jobs(conn, model_version=labeler.model_version, ids=[job_id])
    )
    public_id = conn.execute("select public_id from core.jobs where id = %s", (job_id,)).fetchone()
    cards = dict(
        conn.execute(
            "select skill_slug, level::text from api.v_job_skills where job_public_id = %s",
            public_id,
        ).fetchall()
    )
    assert cards == {"java": "required", "kotlin": "preferred"}  # kafka (mentioned) không hiện

    ids = skill_ids(conn)

    def found(slug):
        rows = conn.execute(
            "select public_id from api.search_jobs(skills => %s)", ([ids[slug]],)
        ).fetchall()
        return public_id in rows

    assert found("java") and not found("kafka")
