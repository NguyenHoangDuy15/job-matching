"""Ghi kết quả gắn mức vào core.job_skills (migration 0004).

Mỗi tin: upsert các kỹ năng tìm được, xóa kỹ năng không còn trong JD. Dòng extractor = 'human'
(sửa tay) không bao giờ bị ghi đè hay xóa.
"""

from collections import Counter
from collections.abc import Iterable

from skillkit.levels.cascade import JobSkill
from skillkit.levels.pipeline import SkillLabeler

_DB_SECTION = {"DESC": "description", "REQ": "requirements", "PREF": "preferred", "NONE": "none"}
EVIDENCE_MAX = 500

UPSERT = """
insert into core.job_skills (job_id, skill_id, level, evidence, extractor, confidence, section,
                             source_detail, mention_count, model_version, labeled_at)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
on conflict (job_id, skill_id) do update set
  level = excluded.level, evidence = excluded.evidence, extractor = excluded.extractor,
  confidence = excluded.confidence, section = excluded.section,
  source_detail = excluded.source_detail, mention_count = excluded.mention_count,
  model_version = excluded.model_version, labeled_at = now()
where core.job_skills.extractor <> 'human'
"""
DELETE_STALE = """
delete from core.job_skills
where job_id = %s and extractor <> 'human' and not (skill_id = any(%s))
"""


def has_levels_schema(conn) -> bool:
    return bool(
        conn.execute(
            "select 1 from information_schema.columns where table_schema = 'core' "
            "and table_name = 'job_skills' and column_name = 'source_detail'"
        ).fetchone()
    )


def skill_ids(conn) -> dict[str, int]:
    """slug → ref.skills.id (chỉ kỹ năng đang dùng)."""
    return dict(conn.execute("select slug, id from ref.skills where is_active").fetchall())


def label_jobs(labeler: SkillLabeler, rows: Iterable[tuple]) -> dict[int, list[JobSkill]]:
    """rows: (id, jd_text, description, requirements, preferred, benefits)."""
    out = {}
    for job_id, jd_text, desc, req, pref, ben in rows:
        if jd_text:
            out[job_id] = labeler.label_text(str(job_id), jd_text)
        else:
            cols = {"description": desc, "requirements": req, "preferred": pref, "benefits": ben}
            out[job_id] = labeler.label_columns(str(job_id), cols)
    return out


def write_job_skills(
    conn, labeled: dict[int, list[JobSkill]], ids: dict[str, int], model_version: str
) -> Counter:
    stats: Counter = Counter()
    with conn.cursor() as cur:
        for job_id, skills in labeled.items():
            params = []
            for r in skills:
                if r.skill_id not in ids:
                    stats["thieu_trong_ref_skills"] += 1
                    continue
                stats[r.level] += 1
                params.append(
                    (
                        job_id,
                        ids[r.skill_id],
                        r.level,
                        r.evidence[:EVIDENCE_MAX],
                        r.extractor,
                        r.confidence,
                        _DB_SECTION[r.section],
                        r.source,
                        r.mention_count,
                        model_version,
                    )
                )
            if params:
                cur.executemany(UPSERT, params)
            cur.execute(DELETE_STALE, (job_id, [p[1] for p in params]))
            stats["tin"] += 1
    return stats
