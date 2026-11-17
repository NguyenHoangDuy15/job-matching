"""S4-D03: M (bắt buộc ×2, ưu tiên ×1), X, gộp H và chia lại trọng số khi thiếu thành phần."""

import pytest

from ranking.components import combine, load_ranker_config, m_score, x_score
from skillkit.levels.pipeline import SKILLS_YAML
from skillkit.taxonomy import load_taxonomy


@pytest.fixture(scope="module")
def tax():
    return load_taxonomy(SKILLS_YAML)


@pytest.fixture(scope="module")
def cfg():
    return load_ranker_config()


# Ví dụ tính tay trong proposal (tab "Kế hoạch thực thi", mục F5): CV Data Engineer 2 năm,
# JD Data Engineer (Middle) yêu cầu 3 năm.
PROPOSAL_JD = [
    ("python", "required"),
    ("sql", "required"),
    ("airflow", "required"),
    ("spark", "required"),
    ("kafka", "preferred"),
    ("aws", "preferred"),
]
PROPOSAL_CV = {"python": "strong", "sql": "strong", "airflow": "listed", "aws": "listed"}


def test_proposal_example_m_is_0_61(tax, cfg):
    """Σ r·b = 2 + 2 + 1,4 + 0 + 0 + 0,7 = 6,1; Σ r = 10 → M = 0,61."""
    m = m_score(PROPOSAL_JD, PROPOSAL_CV, tax, cfg)
    assert m.score == pytest.approx(0.61)
    assert [r.skill_id for r in m.missing] == ["spark", "kafka"]  # bắt buộc trước
    assert {r.skill_id for r in m.matched} == {"python", "sql", "airflow", "aws"}


def test_proposal_example_x_is_2_of_3():
    assert x_score(2, 3) == pytest.approx(2 / 3)


def test_proposal_example_h(tax, cfg):
    """K = 0,90 (BM25 cao hơn 90% tin), E = 0,57 theo ví dụ, M = 0,61, X = 0,67:
    H = 100 × (0,25·0,90 + 0,35·0,61 + 0,30·0,57 + 0,10·0,667) = 67,6."""
    m = m_score(PROPOSAL_JD, PROPOSAL_CV, tax, cfg).score
    h = combine({"K": 0.90, "M": m, "E": 0.57, "X": x_score(2, 3)}, cfg)
    assert h.h == 67.6
    assert h.missing == [] and sum(h.weights_used.values()) == pytest.approx(1.0)


def test_required_counts_twice_preferred(tax, cfg):
    req = m_score([("python", "required"), ("aws", "preferred")], {"python": "strong"}, tax, cfg)
    pref = m_score([("python", "required"), ("aws", "preferred")], {"aws": "strong"}, tax, cfg)
    assert req.score == pytest.approx(2 / 3) and pref.score == pytest.approx(1 / 3)


def test_mentioned_skills_ignored_and_no_skills_gives_none(tax, cfg):
    assert m_score([("python", "mentioned")], {"python": "strong"}, tax, cfg) is None
    assert m_score([], {"python": "strong"}, tax, cfg) is None


def test_evidence_weights(tax, cfg):
    jd = [("python", "required")]
    assert m_score(jd, {"python": "strong"}, tax, cfg).score == 1.0
    assert m_score(jd, {"python": "listed"}, tax, cfg).score == pytest.approx(0.7)
    assert m_score(jd, {"python": "user_added"}, tax, cfg).score == pytest.approx(0.7)
    assert m_score(jd, {}, tax, cfg).score == 0.0  # CV không có kỹ năng: M = 0, không None


def test_tree_child_parent_sibling(tax, cfg):
    # JD Java, CV Spring Boot (con) → đủ điểm
    child = m_score([("java", "required")], {"spring_boot": "strong"}, tax, cfg)
    assert child.score == 1.0 and child.rows[0].relation == "child"
    # JD Spring Boot, CV chỉ có Java (cha) → 0,5
    parent = m_score([("spring_boot", "required")], {"java": "strong"}, tax, cfg)
    assert parent.score == pytest.approx(0.5) and parent.rows[0].relation == "parent_only"
    # JD Spring Boot, CV Hibernate (anh em cùng cha Java cấp 2) → 0,3
    sib = m_score([("spring_boot", "required")], {"hibernate": "strong"}, tax, cfg)
    assert sib.score == pytest.approx(0.3) and sib.rows[0].relation == "sibling"
    # JD Python, CV Java: cùng nhóm cấp 1 "lập trình" nhưng KHÔNG tính
    assert m_score([("python", "required")], {"java": "strong"}, tax, cfg).score == 0.0


def test_best_relation_wins(tax, cfg):
    """CV có cả kỹ năng đúng (listed) và kỹ năng cha (strong): lấy điểm cao nhất."""
    m = m_score(
        [("spring_boot", "required")], {"spring_boot": "listed", "java": "strong"}, tax, cfg
    )
    assert m.score == pytest.approx(0.7) and m.rows[0].relation == "exact"


def test_adding_a_required_skill_never_lowers_m(tax, cfg):
    """Tính chất: CV thêm một kỹ năng JD yêu cầu thì M không giảm."""
    before = m_score(PROPOSAL_JD, PROPOSAL_CV, tax, cfg).score
    after = m_score(PROPOSAL_JD, {**PROPOSAL_CV, "spark": "listed"}, tax, cfg).score
    assert after > before


def test_duplicate_jd_skill_counted_once(tax, cfg):
    m = m_score([("python", "required"), ("python", "required")], {"python": "strong"}, tax, cfg)
    assert m.score == 1.0 and len(m.rows) == 1


@pytest.mark.parametrize(
    ("cv", "jd", "expected"),
    [(2, 3, 2 / 3), (5, 3, 1.0), (0, 2, 0.0), (2, None, None), (2, 0, None), (None, 3, None)],
)
def test_x_score(cv, jd, expected):
    got = x_score(cv, jd)
    assert got == (pytest.approx(expected) if expected is not None else None)


def test_redistribute_when_x_missing(cfg):
    """JD không ghi số năm: X bỏ, 0,90 trọng số còn lại chia lại thành tổng 1."""
    h = combine({"K": 0.9, "M": 0.61, "E": 0.57, "X": None}, cfg)
    assert h.missing == ["X"]
    assert h.weights_used == pytest.approx({"K": 0.25 / 0.9, "M": 0.35 / 0.9, "E": 0.30 / 0.9})
    assert h.h == pytest.approx(100 * (0.25 * 0.9 + 0.35 * 0.61 + 0.30 * 0.57) / 0.9, abs=0.05)


def test_redistribute_when_m_missing(cfg):
    h = combine({"K": 0.5, "M": None, "E": 0.5, "X": 1.0}, cfg)
    assert h.missing == ["M"] and h.h == pytest.approx(100 * (0.125 + 0.15 + 0.1) / 0.65, abs=0.05)


def test_all_missing_gives_none(cfg):
    assert combine({"K": None, "M": None, "E": None, "X": None}, cfg).h is None


def test_h_bounds_and_perfect_match(cfg):
    assert combine({"K": 1, "M": 1, "E": 1, "X": 1}, cfg).h == 100.0
    assert combine({"K": 0, "M": 0, "E": 0, "X": 0}, cfg).h == 0.0


def test_weights_sum_to_one(cfg):
    assert sum(cfg.weights.values()) == pytest.approx(1.0)
    assert cfg.weights == {"K": 0.25, "M": 0.35, "E": 0.30, "X": 0.10}
