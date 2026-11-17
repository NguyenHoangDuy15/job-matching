"""S3-T05: lấy mẫu cặp tin và tính precision/recall có trọng số."""

import csv
import importlib.util
from pathlib import Path

import pytest

from ingestion.dedup_eval import (
    CSV_FIELDS,
    CURRENT_RULE,
    LabeledPair,
    Pair,
    Rule,
    all_pairs,
    best_rule,
    evaluate,
    read_labels,
    sample_pairs,
    stratum_of,
    wilson_lower,
)
from ingestion.near_dedup import JobDoc, find_near_duplicates

BASE = (
    "Chúng tôi tìm Data Engineer xây dựng pipeline dữ liệu cho nền tảng thương mại điện tử. "
    "Bạn sẽ thiết kế luồng ETL bằng Python và Airflow, tối ưu truy vấn PostgreSQL, "
    "xây kho dữ liệu trên BigQuery, giám sát chất lượng dữ liệu hằng ngày, phối hợp với đội "
    "phân tích để đưa báo cáo lên Looker. Yêu cầu tối thiểu hai năm kinh nghiệm, thành thạo SQL, "
    "hiểu mô hình dữ liệu dạng sao, có kinh nghiệm Spark là lợi thế. Quyền lợi lương tháng 13, "
    "bảo hiểm sức khỏe, làm việc hybrid hai ngày mỗi tuần tại văn phòng quận 1."
)
EXTRA = " Môi trường trẻ trung năng động, đồng nghiệp thân thiện, được đào tạo bài bản."


def _doc(i, title="Data Engineer", text=BASE, company=1, provinces=(79,)):
    return JobDoc(id=i, company_id=company, provinces=frozenset(provinces), title=title, text=text)


def test_all_pairs_scope_matches_near_dedup():
    docs = [
        _doc(1),
        _doc(2, text=BASE + EXTRA),
        _doc(3, company=2),  # khác công ty
        _doc(4, provinces=(1,)),  # khác tỉnh
        _doc(5, company=None),
        _doc(6, title="Kế toán", text="Hạch toán sổ sách, lập báo cáo thuế hằng tháng."),
    ]
    pairs = all_pairs(docs)
    assert [(p.job_a, p.job_b) for p in pairs] == [(1, 2)]
    # Cùng độ giống chính xác với ingestion.near_dedup (chỉ khác: không qua LSH)
    near = find_near_duplicates(docs)
    assert pairs[0].similarity == near[0].similarity
    assert pairs[0].title_similarity == 1.0


def test_all_pairs_keeps_low_similarity_for_recall():
    half = " ".join(BASE.split()[: len(BASE.split()) // 2])
    pairs = all_pairs([_doc(1), _doc(2, text=half + " hoàn toàn khác phần sau của mô tả")])
    assert pairs and 0.40 <= pairs[0].similarity < 0.70  # dưới ngưỡng hàng chờ nhưng vẫn đo
    assert all_pairs([_doc(1), _doc(2, text=half)], min_similarity=0.9) == []


def test_stratum_of():
    assert stratum_of(1.0) == "gop"
    assert stratum_of(0.85) == "gop"
    assert stratum_of(0.8499) == "hang_cho"
    assert stratum_of(0.70) == "hang_cho"
    assert stratum_of(0.5) == "duoi_nguong"
    assert stratum_of(0.39) == "thap"
    assert stratum_of(0.19) is None


def _pairs(n, sim):
    return [Pair(i, i + 10_000, sim, 1.0, 100) for i in range(n)]


def test_sample_pairs_quota_and_redistribution():
    pairs = _pairs(200, 0.95) + _pairs(10, 0.75) + _pairs(300, 0.5)
    sampled = sample_pairs(pairs, total=100, seed=1)
    taken = {}
    for _, name, size, k in sampled:
        taken[name] = k
        assert size == {"gop": 200, "hang_cho": 10, "duoi_nguong": 300}[name]
    assert len(sampled) == 100
    assert taken["hang_cho"] == 10  # ít hơn chỉ tiêu 35 → lấy hết, phần dư chuyển tầng khác
    assert taken["gop"] == 70  # nhận phần dư trước (ưu tiên vùng gộp)
    assert taken["duoi_nguong"] == 20
    assert sample_pairs(pairs, total=100, seed=1) == sampled  # cố định theo seed


def test_sample_pairs_small_store_takes_everything():
    sampled = sample_pairs(_pairs(3, 0.9) + _pairs(2, 0.6), total=100)
    assert len(sampled) == 5


def test_sample_pairs_low_stratum_only_fills_spare():
    full = sample_pairs(_pairs(200, 0.95) + _pairs(200, 0.75) + _pairs(200, 0.5) + _pairs(50, 0.3))
    assert all(name != "thap" for _, name, *_ in full)
    small = sample_pairs(_pairs(19, 0.9) + _pairs(10, 0.75) + _pairs(47, 0.5) + _pairs(80, 0.3))
    taken = {name: k for _, name, _, k in small}
    assert taken == {"gop": 19, "hang_cho": 10, "duoi_nguong": 47, "thap": 24}


def test_rule_decide_matches_near_dedup():
    from ingestion.near_dedup import decide

    for sim, title, n in [
        (0.5, 1.0, 50),
        (0.4, 1.0, 50),
        (0.9, 1.0, 50),
        (0.9, 0.8, 50),
        (0.9, 1.0, 10),
        (0.75, 1, 50),
        (0.6, 1, 50),
    ]:
        expected = decide(sim, title, n) or "none"
        assert CURRENT_RULE.decide(sim, title, n) == expected


def test_evaluate_weighted_precision_recall():
    rows = [
        # vùng gộp: 4 cặp mẫu đại diện 40 cặp (trọng số 10), 1 cặp gộp nhầm
        LabeledPair(Pair(1, 2, 0.95, 1.0, 100), 10, "gop", True),
        LabeledPair(Pair(3, 4, 0.92, 1.0, 100), 10, "gop", True),
        LabeledPair(Pair(5, 6, 0.90, 1.0, 100), 10, "gop", True),
        LabeledPair(Pair(7, 8, 0.88, 1.0, 100), 10, "gop", False),
        # hàng chờ: 2 cặp đại diện 20 cặp, 1 trùng thật
        LabeledPair(Pair(9, 10, 0.80, 1.0, 100), 10, "hang_cho", True),
        LabeledPair(Pair(11, 12, 0.72, 1.0, 100), 10, "hang_cho", False),
        # dưới ngưỡng: 1 cặp đại diện 100 cặp, là trùng thật bị bỏ sót
        LabeledPair(Pair(13, 14, 0.5, 1.0, 100), 100, "duoi_nguong", True),
    ]
    m = evaluate(rows, Rule(merge=0.85))  # luật S3-T04: gộp từ 0,85
    assert m.precision == pytest.approx(30 / 40)
    assert m.recall == pytest.approx(30 / (30 + 10 + 100))
    assert m.recall_with_review == pytest.approx(40 / 140)
    assert (m.merged_sampled, m.merged_wrong) == (4, 1)
    assert m.fp_examples == [Pair(7, 8, 0.88, 1.0, 100)]
    stricter = evaluate(rows, Rule(merge=0.89))
    assert stricter.precision == 1.0
    assert best_rule([m, stricter]).rule == Rule(merge=0.89)


def test_best_rule_none_when_target_missed():
    rows = [LabeledPair(Pair(1, 2, 0.95, 1.0, 100), 1, "gop", False)]
    assert best_rule([evaluate(rows, CURRENT_RULE)]) is None


def test_wilson_lower():
    assert wilson_lower(0, 0) is None
    assert 0.80 < wilson_lower(40, 40) < 0.95  # 40/40 đúng vẫn chưa chứng minh được ≥ 0,95
    assert wilson_lower(95, 100) < 0.95


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})


def _row(pid, a, sim, label, tang="gop", size=10, taken=3):
    return {
        "pair_id": pid,
        "tang": tang,
        "so_cap_tang": size,
        "so_cap_mau_tang": taken,
        "job_a": a,
        "job_b": a + 1,
        "do_giong": sim,
        "do_giong_chuc_danh": 1.0,
        "so_tu_it_hon": 100,
        "nhan": label,
    }


def test_read_labels_reweights_by_labeled_rows(tmp_path):
    path = tmp_path / "pairs.csv"
    _write_csv(path, [_row(1, 1, 0.9, "1"), _row(2, 3, 0.9, "0"), _row(3, 5, 0.9, "")])
    rows, warnings = read_labels(path)
    assert len(rows) == 2 and len(warnings) == 1
    assert [r.weight for r in rows] == [5.0, 5.0]  # 10 cặp / 2 cặp có nhãn


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "eval_dedup.py"
    spec = importlib.util.spec_from_file_location("eval_dedup", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_score_command_writes_report(tmp_path):
    path = tmp_path / "pairs.csv"
    _write_csv(path, [_row(i, i * 2, 0.95, "1", taken=20) for i in range(1, 21)])
    report = tmp_path / "score.md"
    code = _load_script().main(["score", str(path), "--report", str(report)])
    text = report.read_text(encoding="utf-8")
    assert code == 0
    assert "### Luật hiện tại" in text and "**Đề xuất:**" in text


def test_diff_html_marks_changes():
    a, b = _load_script()._diff_html("tuyển Java <b>", "tuyển Python <b>")
    assert "<del>Java</del>" in a and "<ins>Python</ins>" in b
    assert "&lt;b&gt;" in a  # nội dung tin được escape
