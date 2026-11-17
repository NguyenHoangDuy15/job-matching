"""S4-D01: K · điểm Từ khóa = phân vị BM25 trên toàn kho tin đang mở."""

import time

import numpy as np
import pytest

from retrieval.bm25 import (
    JobDoc,
    KeywordIndex,
    RefreshingIndex,
    job_tokens,
    percentile_k,
    query_from_profile,
)
from retrieval.text import Analyzer


@pytest.fixture(scope="module")
def analyzer():
    return Analyzer()


DOCS = [
    JobDoc(
        1, "Backend Developer (Java)", "Thành thạo Java, Spring Boot, MySQL", None, "Phát triển API"
    ),
    JobDoc(
        2, "Frontend Developer", "Có kinh nghiệm ReactJS, TypeScript", None, "Xây dựng giao diện"
    ),
    JobDoc(3, "Data Engineer", "Python, Airflow, Spark", None, "Xây dựng pipeline dữ liệu"),
    JobDoc(4, "Kế toán tổng hợp", "Thành thạo Excel", None, "Lập báo cáo tài chính"),
    JobDoc(5, "Nhân viên kinh doanh", None, None, None, jd_text="Tư vấn khách hàng, chăm sóc"),
]


@pytest.fixture(scope="module")
def index(analyzer):
    return KeywordIndex.build(DOCS, analyzer)


def _profile(skills=(), title=None):
    return {
        "target_title": title,
        "skills": [{"skill_id": s, "evidence_level": lvl} for s, lvl in skills],
    }


def test_aliases_become_one_skill_token(analyzer):
    """ "ReactJS", "React.js", "React" (có ngữ cảnh) ra cùng một token: CV chỉ cần hỏi sk:react.
    "react" đứng một mình là alias nhập nhằng, từ điển cần ngữ cảnh mới nhận."""
    texts = ("ReactJS", "React.js", "Thành thạo React, TypeScript")
    assert all("sk:react" in analyzer.tokens(t) for t in texts)
    assert "react" not in analyzer.tokens("Thành thạo React, TypeScript")


def test_accents_removed_so_unaccented_text_matches(analyzer):
    assert analyzer.tokens("Lập trình viên") == analyzer.tokens("Lap trinh vien")


def test_stopwords_and_single_letters_dropped(analyzer):
    assert analyzer.tokens("và các a của") == []
    assert "2026" in analyzer.tokens("năm 2026")


def test_title_weighs_more_than_description(analyzer):
    in_title = KeywordIndex.build(
        [JobDoc(1, "Kiểm thử", None, None, "khác"), JobDoc(2, "khác", None, None, "Kiểm thử")],
        analyzer,
    )
    r = in_title.score(analyzer.tokens("kiểm thử"))
    assert r.scores[0] > r.scores[1] > 0


def test_jd_text_used_when_no_sections(analyzer):
    assert "tu" in job_tokens(DOCS[4], analyzer) or "van" in job_tokens(DOCS[4], analyzer)


def test_percentile_bounds_monotone_and_ties():
    s = np.array([0.0, 1.0, 2.0, 2.0, 5.0, 0.0], dtype=np.float32)
    k = percentile_k(s)
    assert ((k >= 0) & (k <= 1)).all()
    assert k[4] > k[2] == k[3] > k[1] > 0  # cao hơn thì K cao hơn; hòa điểm cùng K
    assert k[0] == k[5] == 0.0  # không khớp từ nào → 0, không lấy "phân vị giữa"


def test_percentile_empty():
    assert percentile_k(np.zeros(0)).shape == (0,)


def test_java_cv_ranks_java_backend_first(index, analyzer):
    q = query_from_profile(
        _profile([("java", "strong"), ("spring_boot", "listed")], "Backend Developer"), analyzer
    )
    r = index.score(q)
    assert r.k_of(1) == max(r.k)
    assert r.k_of(4) == 0.0 and r.k_of(5) == 0.0
    assert index.top_k(r, 1) == [(1, pytest.approx(float(r.scores[0])))]


def test_strong_evidence_weighs_more_than_listed(index, analyzer):
    strong = index.score(query_from_profile(_profile([("python", "strong")]), analyzer))
    listed = index.score(query_from_profile(_profile([("python", "listed")]), analyzer))
    assert strong.scores[2] == pytest.approx(2 * listed.scores[2])


def test_k_does_not_change_with_filters(index, analyzer):
    """K tính trên toàn kho: lọc tỉnh / hình thức (allowed) chỉ đổi top_k, không đổi K."""
    r = index.score(query_from_profile(_profile([("python", "strong")], "Data Engineer"), analyzer))
    before = r.k_of(3)
    assert index.top_k(r, 10, allowed={3, 4}) == [(3, pytest.approx(float(r.scores[2])))]
    assert index.top_k(r, 10, allowed={1, 2}) == []
    assert r.k_of(3) == before


def test_empty_query_gives_undefined_k(index, analyzer):
    assert query_from_profile(_profile(), analyzer) == []
    assert index.score([]) is None


def test_unknown_tokens_give_zero_not_error(index):
    r = index.score(["khongcotrongkho"])
    assert (r.scores == 0).all() and (r.k == 0).all()


def test_profile_model_and_dict_give_same_query(analyzer):
    from cvparser.profile import CvProfile, SkillEvidence

    model = CvProfile(
        version="t",
        as_of="2026-11-17",
        target_title="Java Developer",
        skills=[
            SkillEvidence(
                skill_id="java",
                name="Java",
                evidence_level="strong",
                evidence="Java",
                highlight=(0, 4),
                section="experience",
                mentions=1,
            )
        ],
    )
    assert query_from_profile(model, analyzer) == query_from_profile(
        _profile([("java", "strong")], "Java Developer"), analyzer
    )


def test_top_k_limits_and_orders(index, analyzer):
    r = index.score(analyzer.tokens("Developer Java ReactJS Python"))
    top = index.top_k(r, 2)
    assert len(top) == 2 and top[0][1] >= top[1][1]


def test_k_for_2000_jobs_within_300ms(analyzer):
    """AC #488: K của 1 CV với 2.000 tin ≤ 300 ms (dựng index không tính, làm 1 lần mỗi giờ)."""
    rng = np.random.default_rng(0)
    words = [f"tu{i}" for i in range(3000)]
    skills = ["Java", "Python", "ReactJS", "Docker", "SQL", "AWS", "Excel", "Kubernetes"]
    docs = [
        JobDoc(
            i,
            " ".join(rng.choice(words, 4)),
            " ".join([*rng.choice(skills, 3), *rng.choice(words, 120)]),
            None,
            " ".join(rng.choice(words, 200)),
        )
        for i in range(2000)
    ]
    index = KeywordIndex.build(docs, analyzer)
    q = query_from_profile(
        _profile([("java", "strong"), ("docker", "listed"), ("sql", "listed")], "Backend Java"),
        analyzer,
    )
    index.score(q)  # làm nóng
    t = time.perf_counter()
    for _ in range(20):
        r = index.score(q)
    per_call_ms = (time.perf_counter() - t) * 1000 / 20
    assert len(r.k) == 2000
    assert per_call_ms <= 300, per_call_ms


def test_refreshing_index_rebuilds_in_background_and_keeps_old_on_error():
    import threading

    now = [0.0]
    built = []
    gate = threading.Event()
    gate.set()

    def build():
        gate.wait(2)
        built.append(now[0])
        if len(built) == 3:
            raise RuntimeError("DB lỗi")
        return f"index{len(built)}"

    holder = RefreshingIndex(build, refresh_seconds=10, clock=lambda: now[0])
    assert holder.get() == "index1"
    now[0] = 5
    assert holder.get() == "index1" and len(built) == 1  # chưa tới hạn
    gate.clear()  # lần dựng lại sẽ chờ: request không được phải chờ theo
    now[0] = 11
    assert holder.get() == "index1"  # trả bản cũ ngay
    gate.set()
    _wait(lambda: holder.get() == "index2")
    now[0] = 30
    holder.get()
    _wait(lambda: len(built) == 3 and not holder._building)
    assert holder.get() == "index2"  # lần dựng lỗi: giữ bản cũ


def _wait(cond, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.01)
    raise AssertionError("hết thời gian chờ")
