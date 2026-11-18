"""S4-D04: rank() — lọc cứng, hợp nhất top BM25 + top vector, chấm H, sắp, giải thích."""

from datetime import date

import numpy as np
import pytest

from ranking.components import load_ranker_config
from ranking.engine import JobMeta, Snapshot
from ranking.rank import CvInput, MatchFilters, allowed_jobs, rank, skill_rows
from ranking.semantic import SemanticIndex
from retrieval.bm25 import JobDoc, KeywordIndex, query_from_profile
from skillkit.levels.pipeline import SKILLS_YAML
from skillkit.taxonomy import load_taxonomy

TODAY = date(2026, 11, 25)
HN, HCM = 1, 79


def _unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _job(i, title, *, skills=(), provinces=(HN,), mode="onsite", until=None, years=None):
    return JobMeta(
        id=i, public_id=f"p{i}", title=title, company=f"Công ty {i}", work_mode=mode,
        valid_through=until, apply_url=f"https://x/{i}", years_exp_min=years,
        provinces=tuple(provinces), province_names=tuple(str(p) for p in provinces),
        skills=tuple(skills),
    )  # fmt: skip


@pytest.fixture(scope="module")
def tax():
    return load_taxonomy(SKILLS_YAML)


@pytest.fixture(scope="module")
def cfg():
    return load_ranker_config()


@pytest.fixture(scope="module")
def snapshot():
    jobs = [
        _job(1, "Data Engineer", years=3, until=date(2026, 12, 31),
             skills=[("python", "Python", "required"), ("sql", "SQL", "required"),
                     ("airflow", "Airflow", "preferred")]),
        _job(2, "Data Engineer (Remote)", mode="remote", provinces=(HCM,),
             skills=[("python", "Python", "required"), ("spark", "Spark", "required")]),
        _job(3, "Kế toán tổng hợp", skills=[("excel", "Excel", "required")]),
        _job(4, "Data Engineer hết hạn", until=date(2026, 11, 1),
             skills=[("python", "Python", "required")]),
        _job(5, "Chuyên viên dữ liệu", provinces=(HCM,), mode="hybrid"),  # không có kỹ năng
        _job(6, "Kỹ sư xử lý dữ liệu lớn", provinces=()),  # không ghi tỉnh, chỉ vector khớp
    ]  # fmt: skip
    docs = [
        JobDoc(1, "Data Engineer", "Thành thạo Python, SQL. Có Airflow", None, "Xây dựng pipeline"),
        JobDoc(2, "Data Engineer (Remote)", "Python, Spark", None, "ETL"),
        JobDoc(3, "Kế toán tổng hợp", "Thành thạo Excel", None, "Báo cáo tài chính"),
        JobDoc(4, "Data Engineer hết hạn", "Python", None, None),
        JobDoc(5, "Chuyên viên dữ liệu", None, None, "Làm sạch dữ liệu"),
        JobDoc(6, "Kỹ sư xử lý dữ liệu lớn", None, None, "Vận hành cụm"),
    ]
    vecs = {1: _unit(1, 0.1), 2: _unit(1, 0.2), 3: _unit(0, 1), 4: _unit(1, 0), 5: _unit(1, 0.5),
            6: _unit(1, 0.05)}  # fmt: skip
    ids = sorted(vecs)
    return Snapshot(
        {j.id: j for j in jobs},
        KeywordIndex.build(docs),
        SemanticIndex(ids, np.stack([vecs[i] for i in ids]), model="test"),
    )


def _cv(skills=None, title="Data Engineer", years=5.0, vec=(1.0, 0.0)):
    skills = skills if skills is not None else {"python": "strong", "sql": "strong"}
    profile = {
        "target_title": title,
        "skills": [{"skill_id": s, "evidence_level": e} for s, e in skills.items()],
    }
    return CvInput(
        skills=skills,
        skill_names={s: s.title() for s in skills},
        years_exp=years,
        query_tokens=query_from_profile(profile),
        vectors=None if vec is None else np.stack([_unit(*vec)]),
        vectors_model="test",
    )


def test_hard_filters(snapshot):
    assert allowed_jobs(snapshot, MatchFilters(), TODAY) == {1, 2, 3, 5, 6}  # tin 4 hết hạn
    # Hà Nội: tin remote (2) và tin không ghi tỉnh (6) vẫn qua; tin HCM onsite/hybrid (5) bị loại
    assert allowed_jobs(snapshot, MatchFilters(provinces=(HN,)), TODAY) == {1, 2, 3, 6}
    assert allowed_jobs(snapshot, MatchFilters(work_modes=("remote",)), TODAY) == {2}
    assert allowed_jobs(snapshot, MatchFilters((HCM,), ("hybrid", "remote")), TODAY) == {2, 5}


def test_expired_never_returned(snapshot, tax, cfg):
    out = rank(snapshot, _cv(), MatchFilters(), TODAY, tax, cfg)
    assert 4 not in {s.job.id for s in out.results}


def test_best_job_first_and_sorted(snapshot, tax, cfg):
    out = rank(snapshot, _cv(), MatchFilters(), TODAY, tax, cfg)
    scores = [s.score for s in out.results]
    assert out.results[0].job.id == 1 and scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)


def test_union_keeps_vector_only_candidates(snapshot, tax, cfg):
    """Tin 6 không khớp từ nào (BM25 = 0) nhưng gần về nghĩa: vẫn được chấm nhờ top vector."""
    out = rank(snapshot, _cv(), MatchFilters(), TODAY, tax, cfg, per_source=2)
    ids = {s.job.id for s in out.results}
    assert 6 in ids and len(ids) == len(out.results)  # không trùng tin


def test_k_and_e_on_whole_corpus_not_filtered_set(snapshot, tax, cfg):
    all_jobs = rank(snapshot, _cv(), MatchFilters(), TODAY, tax, cfg)
    hanoi = rank(snapshot, _cv(), MatchFilters(provinces=(HN,)), TODAY, tax, cfg)

    def comps(out, job_id):
        return next(s.combined.components for s in out.results if s.job.id == job_id)

    for key in ("K", "E"):
        assert comps(all_jobs, 1)[key] == comps(hanoi, 1)[key]


def test_missing_components_redistribute(snapshot, tax, cfg):
    out = rank(snapshot, _cv(), MatchFilters(), TODAY, tax, cfg)
    by_id = {s.job.id: s for s in out.results}
    assert by_id[2].combined.missing == ["X"]  # tin 2 không ghi số năm
    assert sum(by_id[2].combined.weights_used.values()) == pytest.approx(1.0)
    assert by_id[6].combined.components["M"] is None  # tin không có kỹ năng
    assert "không ghi kỹ năng" in by_id[6].explanation


def test_no_vectors_still_ranks_without_e(snapshot, tax, cfg):
    out = rank(snapshot, _cv(vec=None), MatchFilters(), TODAY, tax, cfg)
    assert out.results and all(s.combined.components["E"] is None for s in out.results)
    assert any("E không xác định" in n for n in out.notes)


def test_explanation_and_skill_rows(snapshot, tax, cfg):
    out = rank(snapshot, _cv(), MatchFilters(), TODAY, tax, cfg)
    top = out.results[0]
    assert top.explanation.startswith("Khớp 2/2 kỹ năng bắt buộc · 0/1 kỹ năng ưu tiên")
    assert "đủ kinh nghiệm (yêu cầu 3 năm)" in top.explanation
    matched, missing = skill_rows(top.match, {"python": "Python", "airflow": "Airflow"})
    assert {m["skill_id"] for m in matched} == {"python", "sql"}
    assert missing == [{"skill_id": "airflow", "skill": "Airflow", "level": "preferred"}]


def test_fewer_results_when_filters_tight(snapshot, tax, cfg):
    out = rank(snapshot, _cv(), MatchFilters(work_modes=("remote",)), TODAY, tax, cfg)
    assert [s.job.id for s in out.results] == [2] and out.allowed == 1


def test_cv_without_signals_scored_by_m_x(snapshot, tax, cfg):
    cv = CvInput(skills={"excel": "strong"}, skill_names={}, years_exp=None, query_tokens=[],
                 vectors=None)  # fmt: skip
    out = rank(snapshot, cv, MatchFilters(), TODAY, tax, cfg)
    assert out.results[0].job.id == 3
