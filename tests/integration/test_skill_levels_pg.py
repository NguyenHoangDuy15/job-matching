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
