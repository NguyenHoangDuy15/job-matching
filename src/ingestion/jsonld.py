"""Đọc khối JSON-LD JobPosting (schema.org) trong trang chi tiết tin tuyển dụng."""

import html
import json
import re
from datetime import date, datetime
from typing import Any

from ingestion.models import JobPostingRaw, LocationRaw, SalaryRaw

LD_JSON = re.compile(
    r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE
)
_BLOCK_TAGS = r"br|div|h[1-6]|li|p|tr|ul|ol"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\d.,])(?:\+?84|0)(?:[\s.-]?\d){8,10}(?![\d])")


def html_to_text(fragment: str) -> str:
    """Đổi HTML thành văn bản thuần, mỗi khối một dòng."""
    text = re.sub(rf"</?(?:{_BLOCK_TAGS})\b[^>]*>", "\n", fragment, flags=re.IGNORECASE)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def mask_contacts(text: str) -> str:
    """Che email và số điện thoại để mô tả không mang PII sang bước embedding hay LLM."""
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))


def _walk(node: Any):
    """Duyệt mọi dict trong JSON-LD, kể cả trong list và @graph."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _is_job_posting(item: dict) -> bool:
    kind = item.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return "JobPosting" in kinds


def find_job_posting(page: str) -> dict | None:
    """Trả khối JobPosting đầu tiên trong trang, hoặc None."""
    for block in LD_JSON.findall(page):
        try:
            data = json.loads(html.unescape(block) if "&quot;" in block else block, strict=False)
        except json.JSONDecodeError:
            continue
        for item in _walk(data):
            if _is_job_posting(item):
                return item
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("name") or value.get("value")
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value if v)
    text = " ".join(str(value).split())
    return text or None


def _date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.]", "", value.replace(",", ""))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def _locations(value: Any) -> list[LocationRaw]:
    items = value if isinstance(value, list) else [value] if value else []
    result = []
    for place in items:
        if not isinstance(place, dict):
            continue
        address = place.get("address") or {}
        if isinstance(address, str):
            result.append(LocationRaw(locality=address))
            continue
        country = address.get("addressCountry")
        loc = LocationRaw(
            street=_text(address.get("streetAddress")),
            locality=_text(address.get("addressLocality")),
            region=_text(address.get("addressRegion")),
            country=_text(country.get("name") if isinstance(country, dict) else country),
        )
        if any((loc.street, loc.locality, loc.region)):
            result.append(loc)
    return result


def _salary(value: Any) -> SalaryRaw | None:
    if not isinstance(value, dict):
        return None
    amount = value.get("value")
    unit = None
    low = high = None
    if isinstance(amount, dict):
        unit = _text(amount.get("unitText"))
        low = _number(amount.get("minValue"))
        high = _number(amount.get("maxValue"))
        single = _number(amount.get("value"))
        if low is None and high is None and single is not None:
            low = high = single
    else:
        low = high = _number(amount)
    if low is None and high is None:
        return None
    return SalaryRaw(
        currency=_text(value.get("currency")), min_value=low, max_value=high, unit=unit
    )


def _years(value: Any) -> float | None:
    if isinstance(value, dict):
        months = _number(value.get("monthsOfExperience"))
        return round(months / 12, 1) if months is not None else None
    return None


def parse_job_posting(
    item: dict,
    *,
    source: str,
    source_job_id: str,
    url: str,
    fetched_at: datetime,
    http_status: int = 200,
) -> JobPostingRaw:
    """Chuyển khối JSON-LD JobPosting thành JobPostingRaw."""
    org = item.get("hiringOrganization") or {}
    if isinstance(org, str):
        org = {"name": org}
    description_html = html.unescape(str(item.get("description") or ""))
    logo = org.get("logo")
    location_type = _text(item.get("jobLocationType")) or ""
    return JobPostingRaw(
        source=source,
        source_job_id=source_job_id,
        url=url,
        title=_text(item.get("title")) or "",
        company_name=_text(org.get("name")),
        company_url=_text(org.get("sameAs") or org.get("url")),
        company_logo=_text(logo.get("url") if isinstance(logo, dict) else logo),
        description_html=description_html,
        description_text=mask_contacts(html_to_text(description_html)),
        date_posted=_date(item.get("datePosted")),
        valid_through=_date(item.get("validThrough")),
        employment_type=_text(item.get("employmentType")),
        locations=_locations(item.get("jobLocation")),
        remote="TELECOMMUTE" in location_type.upper(),
        salary=_salary(item.get("baseSalary")),
        years_exp_min=_years(item.get("experienceRequirements")),
        skills_text=_text(item.get("skills")),
        industry=_text(item.get("industry") or item.get("occupationalCategory")),
        json_ld=item,
        http_status=http_status,
        fetched_at=fetched_at,
    )
