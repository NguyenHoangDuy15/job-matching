"""S3-T04: gần trùng bằng MinHash/LSH."""

from ingestion.near_dedup import (
    MERGE_THRESHOLD,
    REVIEW_THRESHOLD,
    JobDoc,
    decide,
    find_near_duplicates,
    jaccard,
    shingles,
    tokens,
)

BASE = (
    "Chúng tôi tìm Data Engineer xây dựng pipeline dữ liệu cho nền tảng thương mại điện tử. "
    "Bạn sẽ thiết kế luồng ETL bằng Python và Airflow, tối ưu truy vấn PostgreSQL, "
    "xây kho dữ liệu trên BigQuery, giám sát chất lượng dữ liệu hằng ngày, phối hợp với đội "
    "phân tích để đưa báo cáo lên Looker. Yêu cầu tối thiểu hai năm kinh nghiệm, thành thạo SQL, "
    "hiểu mô hình dữ liệu dạng sao, có kinh nghiệm Spark là lợi thế. Quyền lợi lương tháng 13, "
    "bảo hiểm sức khỏe, làm việc hybrid hai ngày mỗi tuần tại văn phòng quận 1."
)


def _doc(i, title="Data Engineer", text=BASE, company=1, provinces=(79,)):
    return JobDoc(id=i, company_id=company, provinces=frozenset(provinces), title=title, text=text)


EXTRA = (
    " Môi trường trẻ trung năng động, đồng nghiệp thân thiện, được đào tạo bài bản và có lộ trình"
    " thăng tiến rõ ràng mỗi năm."
)


def test_shingles_and_jaccard():
    sh = shingles(tokens("Xây dựng pipeline dữ liệu"))
    assert sh == {"xay dung pipeline", "dung pipeline du", "pipeline du lieu"}
    assert shingles(["mot", "tu"]) == {"mot tu"}
    assert jaccard(sh, sh) == 1.0
    assert jaccard(frozenset(), frozenset()) == 0.0


def test_decide_thresholds():
    assert decide(0.95, 1.0, 100) == "merge"
    assert decide(MERGE_THRESHOLD, 1.0, 100) == "merge"
    assert decide(0.84, 1.0, 100) == "review"
    assert decide(REVIEW_THRESHOLD, 1.0, 100) == "review"
    assert decide(0.69, 1.0, 100) is None
    # giống ≥ 0,85 nhưng khác chức danh hoặc quá ngắn: chưa đủ chắc → hàng chờ
    assert decide(0.95, 0.5, 100) == "review"
    assert decide(0.95, 0.89, 100) == "review"
    assert decide(0.95, 1.0, 10) == "review"


def test_identical_text_other_formatting_is_merged():
    other = BASE.upper().replace(". ", ".\n• ")
    pairs = find_near_duplicates([_doc(1), _doc(2, title="DATA ENGINEER", text=other)])
    assert [(p.job_a, p.job_b, p.decision) for p in pairs] == [(1, 2, "merge")]
    assert pairs[0].similarity == 1.0


def test_slightly_edited_text_goes_to_review_queue():
    edited = BASE + EXTRA  # một nguồn thêm đoạn giới thiệu môi trường làm việc
    pairs = find_near_duplicates([_doc(1), _doc(2, text=edited)])
    assert len(pairs) == 1
    assert REVIEW_THRESHOLD <= pairs[0].similarity < MERGE_THRESHOLD
    assert pairs[0].decision == "review"


def test_tiny_edit_is_merged():
    edited = BASE.replace("quận 1", "Quận 1, TP.HCM")
    pairs = find_near_duplicates([_doc(5), _doc(3, text=edited)])
    assert [(p.job_a, p.job_b, p.decision) for p in pairs] == [(3, 5, "merge")]
    assert pairs[0].similarity >= MERGE_THRESHOLD


def test_same_template_other_level_is_not_auto_merged():
    pairs = find_near_duplicates([_doc(1), _doc(2, title="Senior Data Engineer Team Lead")])
    assert [p.decision for p in pairs] == ["review"]


def test_one_word_title_difference_is_not_auto_merged():
    # Dữ liệu thật (TopCV): khác đúng một từ nhưng là hai vị trí khác nhau
    pairs = find_near_duplicates(
        [
            _doc(1, title="Kỹ Thuật Thiết Kế Cơ Khí- Có Kinh Nghiệm"),
            _doc(2, title="Kỹ Thuật Thiết Kế Cơ Khí - Không Kinh Nghiệm"),
        ]
    )
    assert [p.decision for p in pairs] == ["review"]
    assert 0.8 < pairs[0].title_similarity < 1.0


def test_other_company_or_province_never_compared():
    docs = [
        _doc(1),
        _doc(2, company=2),
        _doc(3, provinces=(1,)),
        _doc(4, company=None),
    ]
    assert find_near_duplicates(docs) == []


def test_multi_province_overlap_counts_as_same_place():
    pairs = find_near_duplicates([_doc(1, provinces=(1, 79)), _doc(2, provinces=(79,))])
    assert len(pairs) == 1
    assert find_near_duplicates([_doc(1, provinces=()), _doc(2, provinces=())])  # cả hai remote


def test_unrelated_jobs_same_company_are_ignored():
    other = (
        "Tuyển nhân viên kiểm thử phần mềm thủ công cho ứng dụng ngân hàng di động, "
        "viết test case, báo lỗi trên Jira, kiểm thử hồi quy trước mỗi lần phát hành, "
        "phối hợp với đội phát triển "
        "và đội sản phẩm để xác nhận yêu cầu nghiệp vụ, ưu tiên ứng viên có chứng chỉ ISTQB."
    )
    assert find_near_duplicates([_doc(1), _doc(2, title="Tester", text=other)]) == []
