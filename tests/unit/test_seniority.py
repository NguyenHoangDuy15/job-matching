"""Suy cấp bậc tin tuyển dụng (lọc "Cấp bậc" trên /viec-lam)."""

from datetime import UTC, date, datetime

import pytest

from ingestion.location import load_index_from_seed
from ingestion.models import JobPostingRaw
from ingestion.seniority import from_title, infer_seniority, source_signals
from ingestion.store import build_job_row


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("Senior Backend Developer (Java)", "senior"),
        ("Sr. Data Engineer", "senior"),
        ("Chuyên Viên Cao Cấp Phân Tích Dữ Liệu", "senior"),
        ("Junior Frontend Developer", "junior"),
        ("Jr. QA Engineer", "junior"),
        ("Middle .NET Developer", "middle"),
        ("Mid-level Python Engineer", "middle"),
        ("Fresher Java", "fresher"),
        ("Intern BE Developer", "intern"),
        ("Thực Tập Sinh IT", "intern"),
        ("TTS Marketing", "intern"),
        ("Tech Lead Java Developer", "lead"),
        ("Team Leader QA", "lead"),
        ("Trưởng Nhóm Hạ Tầng Công Nghệ Thông Tin", "lead"),
        ("Lead Data Engineer", "lead"),
        ("Principal Software Engineer", "lead"),
        ("Trưởng Phòng Kỹ Thuật", "manager"),
        ("Phó Phòng Thanh Toán Điện Tử", "manager"),
        ("Head of Product", "manager"),
        ("Giám Đốc Công Nghệ", "manager"),
        ("Engineering Manager", "manager"),
        ("Senior Manager, Software Development", "manager"),  # cấp cao xét trước
        ("Junior/Senior Java Developer", "senior"),
        ("Project Manager", None),  # vai trò, không phải cấp quản lý
        ("Product Manager / Product Owner", None),
        ("Senior Project Manager", "senior"),
        ("Account Manager", None),
        ("Chuyên Viên Lead Generation", None),
        ("Backend Developer", None),
        ("Nhân Viên Quản Lý Chất Lượng", None),
        ("Trợ Lý Giám Đốc", None),
        ("Assistant To The Chief Technology Officer", None),
        ("Trợ Lý CTO Khối Công Nghệ", None),
    ],
)
def test_from_title(title, level):
    assert from_title(title) == level


@pytest.mark.parametrize(
    ("years", "level"),
    [(0, "fresher"), (1, "junior"), (2, "junior"), (3, "middle"), (4, "middle"), (5, "senior")],
)
def test_years_fallback(years, level):
    assert infer_seniority("Backend Developer", years) == (level, "years")


def test_signal_order_source_title_years():
    assert infer_seniority("Kỹ sư phần mềm", 2, vnw_level_id=7) == ("manager", "source")
    assert infer_seniority("Kỹ sư phần mềm", 2, vnw_level_id=5) == ("junior", "years")  # 5 quá rộng
    assert infer_seniority("Senior Java", 0) == ("senior", "title")  # tiêu đề thắng số năm
    assert infer_seniority("Kỹ sư", None, source_level_text="Trưởng nhóm") == ("lead", "source")
    assert infer_seniority("Kỹ sư", None, source_level_text="Nhân viên") == ("unknown", "none")
    assert infer_seniority("", None) == ("unknown", "none")


def test_source_signals_from_payload():
    assert source_signals({"job_level": "Trưởng phòng"}) == ("Trưởng phòng", None)
    assert source_signals({"vnw": {"jobLevelId": 3}}) == (None, 3)
    assert source_signals(None) == (None, None)


def test_build_job_row_writes_seniority():
    posting = JobPostingRaw(
        source="topcv",
        source_job_id="1",
        url="https://example.com/1",
        title="Senior Java Developer",
        years_exp_min=1,
        fetched_at=datetime(2026, 11, 17, tzinfo=UTC),
    )
    row = build_job_row(posting, load_index_from_seed(), {}, date(2026, 11, 17))
    assert row.columns["seniority"] == "senior"
