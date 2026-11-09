"""Model dữ liệu thô của một tin tuyển dụng sau khi crawl (S2-T03, US-03)."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LocationRaw(BaseModel):
    """Một địa điểm trong jobLocation của JSON-LD, giữ nguyên chuỗi gốc."""

    model_config = ConfigDict(frozen=True)

    street: str | None = None
    locality: str | None = None
    region: str | None = None
    country: str | None = None

    def as_text(self) -> str:
        """Chuỗi để đưa vào ingestion.location.normalize_location()."""
        parts = [self.locality, self.region]
        return ", ".join(p for p in dict.fromkeys(parts) if p)


class SalaryRaw(BaseModel):
    """baseSalary của JSON-LD. Chuỗi `text` đưa vào ingestion.salary.parse_salary()."""

    model_config = ConfigDict(frozen=True)

    currency: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    unit: str | None = None  # HOUR / DAY / WEEK / MONTH / YEAR
    text: str | None = None  # chuỗi lương hiển thị trên trang, nếu có


class JobPostingRaw(BaseModel):
    """Tin tuyển dụng đọc từ trang chi tiết, chưa chuẩn hóa tỉnh/lương/kỹ năng."""

    source: str  # mã nguồn trong ops.sources.code: itviec, vietnamworks...
    source_job_id: str
    url: str
    title: str
    company_name: str | None = None
    company_url: str | None = None
    company_logo: str | None = None
    description_html: str = ""
    description_text: str = ""  # đã bỏ thẻ HTML và che email/SĐT
    date_posted: date | None = None
    valid_through: date | None = None
    employment_type: str | None = None
    locations: list[LocationRaw] = Field(default_factory=list)
    remote: bool = False  # jobLocationType = TELECOMMUTE
    salary: SalaryRaw | None = None
    years_exp_min: float | None = None
    skills_text: str | None = None
    industry: str | None = None
    json_ld: dict[str, Any] = Field(default_factory=dict)  # bản gốc, lưu vào raw.job_snapshots
    http_status: int = 200
    fetched_at: datetime

    def location_text(self) -> str:
        return "; ".join(t for t in (loc.as_text() for loc in self.locations) if t)

    def salary_text(self) -> str | None:
        """Chuỗi lương cho parse_salary(): ưu tiên chữ trên trang, không có thì dựng từ số."""
        s = self.salary
        if s is None:
            return None
        if s.text:
            return s.text
        if s.min_value is None and s.max_value is None:
            return None
        values = [v for v in (s.min_value, s.max_value) if v is not None]
        amount = " - ".join(f"{v:,.0f}" for v in dict.fromkeys(values))
        period = {"YEAR": " / year", "HOUR": " / hour", "DAY": " / day", "WEEK": " / week"}
        return f"{amount} {s.currency or ''}{period.get((s.unit or '').upper(), '')}".strip()
