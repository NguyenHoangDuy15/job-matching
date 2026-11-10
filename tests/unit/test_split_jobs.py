"""Tách section cho tin đã có trong DB: đọc jd_text, ghi 4 cột (cần skillkit.sections, #618)."""

import pytest

pytest.importorskip("skillkit.sections")

from ingestion.split_jobs import plan  # noqa: E402

JD = (
    "Mô tả công việc\nPhát triển API bằng Java.\n\n"
    "Yêu cầu ứng viên\nCó 2 năm kinh nghiệm Java.\n\n"
    "Quyền lợi ứng viên\nThưởng tháng 13."
)


def test_plan_splits_from_jd_text_and_is_idempotent():
    updates, stats = plan([(1, JD, JD, None, None, None)])
    assert stats["tach_duoc"] == 1 and stats["can_cap_nhat"] == 1
    job_id, description, requirements, preferred, benefits = updates[0]
    assert job_id == 1
    assert "Phát triển API" in description and "kinh nghiệm" not in description
    assert "2 năm kinh nghiệm" in requirements
    assert "Thưởng tháng 13" in benefits
    assert preferred is None
    # Chạy lại trên kết quả vừa ghi: không còn gì để cập nhật.
    again, stats2 = plan([(1, JD, description, requirements, preferred, benefits)])
    assert again == [] and stats2["can_cap_nhat"] == 0


def test_plan_without_headings_keeps_full_text_in_description():
    text = "Tuyển lập trình viên Java làm việc tại Hà Nội."
    updates, stats = plan([(7, text, text, None, None, None)])
    assert updates == []
    assert stats["khong_co_heading"] == 1
