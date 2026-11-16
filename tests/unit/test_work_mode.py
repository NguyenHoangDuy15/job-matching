"""Suy hình thức làm việc từ tiêu đề, địa điểm và nội dung JD (lọc "Hình thức làm việc").

Câu mẫu lấy từ JD thật trên production (17/11/2026), kể cả câu bẫy.
"""

from datetime import UTC, date, datetime

import pytest

from ingestion.location import load_index_from_seed
from ingestion.models import JobPostingRaw
from ingestion.store import build_job_row
from ingestion.work_mode import infer_work_mode, mode_from_text


@pytest.mark.parametrize(
    ("text", "mode"),
    [
        # hybrid: ngày làm từ xa hằng tuần hoặc ghi rõ hybrid
        ("Chế độ làm việc: Hybrid, remote 1 ngày/tuần. Thứ 2 – Thứ 6", "hybrid"),
        ("Hybrid working model (flexible between office and home).", "hybrid"),
        ("Có thể làm việc remote 1 ngày/tuần.", "hybrid"),
        ("Thời gian làm việc: Từ thứ 2 - thứ 6 (Thứ 6 làm remote, Nghỉ thứ 7, CN).", "hybrid"),
        ("Working Monday – Friday. Work from home on Wednesday across whole group", "hybrid"),
        ("Chỉ cần làm việc 2 - 3 ngày tại văn phòng / tuần, còn lại làm tại nhà", "hybrid"),
        ("Chế độ hybrid, lên cty 2-3 ngày/tuần", "hybrid"),
        ("Hình thức làm việc Hybrid (áp dụng tại văn phòng miền Nam)", "hybrid"),
        ("Thứ 2 ~ Thứ 6, 8:00 ~ 17:00 (làm việc tại nhà vào thứ 4)", "hybrid"),
        ("Quyền lợi: Làm việc từ xa linh hoạt với môi trường chuyên nghiệp", "hybrid"),
        ("Chế độ làm việc remote mỗi tháng tối đa 30% thời gian làm việc.", "hybrid"),
        # remote toàn phần
        ("Quyền lợi được hưởng: Remote 100% - linh hoạt địa điểm làm việc.", "remote"),
        ("Môi trường: làm việc từ xa (remote) linh hoạt, không gò bó vị trí địa lý.", "remote"),
        ("Có thể làm việc theo hình thức online (remote work)", "remote"),
        ("Fully remote, work from anywhere in Vietnam", "remote"),
        # phúc lợi WFH theo tháng/quý/năm: vẫn là làm tại văn phòng
        ("12 ngày nghỉ phép năm, 01 ngày WFH mỗi tháng.", None),
        ("Chính sách làm việc remote linh hoạt 2 ngày/tháng.", None),
        ("24 ngày làm việc từ xa (Remote) mỗi năm", None),
        ("01-day remote work per month", None),
        ("Chính sách làm việc linh hoạt: 01 ngày remote mỗi quý", None),
        ("Flexible working hours (work from home on working Saturdays)", None),
        ("Sáng thứ 7 làm việc online", None),
        # thuật ngữ kỹ thuật, chữ trùng, phủ định, giới thiệu công ty
        ("Quản trị hệ thống Hybrid Cloud (On-premises & Cloud)", None),
        ("Remote access VPN, Firebase Remote Config", None),
        ("Hỗ trợ trực tiếp (on-site) hoặc từ xa (remote) cho nhân viên", None),
        ("Kinh nghiệm làm việc trong môi trường Scrum/Hybrid", None),
        ("Mô hình hybrid monetization (subscription/IAP + IAA)", None),
        ("Phát triển game hybrid casual puzzle", None),
        ("We are working on-site, hybrid, remote and hiring from all over the world", None),
        ("Làm việc theo ca, tại công ty (không làm việc online)", None),
        ("Không hỗ trợ remote", None),
        ("Giảng dạy theo hình thức online và offline", None),
        ("Làm việc trực tiếp tại nhà máy", None),
        ("Ưu tiên ứng viên từng làm việc tại Nhật", None),
    ],
)
def test_mode_from_text(text, mode):
    assert mode_from_text(text) == mode


def test_title_and_location_win_and_order():
    assert infer_work_mode("Account Manager (Remote)", "Hải Phòng", "", has_province=True) == (
        "remote",
        "text",
    )
    assert infer_work_mode("Fullstack (Hybrid Work)", None, "", has_province=True)[0] == "hybrid"
    assert infer_work_mode("Dev (Remote/Hybrid)", None, "", has_province=True)[0] == "hybrid"
    assert infer_work_mode("Remote Sensing Engineer", None, "", has_province=True)[0] == "onsite"
    assert infer_work_mode("Dev", None, "", has_province=True) == ("onsite", "province")
    assert infer_work_mode("Dev", None, "", has_province=False) == ("unknown", "none")
    assert infer_work_mode("Dev", None, "", has_province=True, telecommute=True)[0] == "remote"


def test_build_job_row_reads_jd():
    posting = JobPostingRaw(
        source="topcv",
        source_job_id="1",
        url="https://example.com/1",
        title="Data Analyst",
        description_text="Quyền lợi\n- Có thể làm việc remote 1 ngày/tuần.",
        fetched_at=datetime(2026, 11, 17, tzinfo=UTC),
    )
    row = build_job_row(posting, load_index_from_seed(), {}, date(2026, 11, 17))
    assert row.columns["work_mode"] == "hybrid"
