"""Chuỗi đọc một CV: trích văn bản (D01) → che PII (D03) → section (D02) → hồ sơ (D04).

Dùng bởi API POST /cv/parse (S3-D05) và worker đọc lô (S6-D03). Hàm thuần: bytes vào, dict ra
(ra JSON được, gửi qua tiến trình được). Văn bản GỐC không bao giờ ra khỏi hàm: chỉ trả văn bản
đã che PII.
"""

import time
from datetime import date

from cvparser.extract import extract_document
from cvparser.extract.models import ExtractOptions
from cvparser.profile import build_profile
from cvparser.redact import redact
from cvparser.sections import split_sections


def parse_cv(
    data: bytes,
    *,
    filename: str | None = None,
    known_names: tuple[str, ...] | list[str] = (),
    as_of: date,
    options: ExtractOptions | None = None,
) -> dict:
    """{"status": "parsed" | "failed", "error": {code, message_vi} | None, "text_redacted",
    "sections", "profile", "parser_version", "timings_ms"}."""
    timings: dict[str, float] = {}
    t = time.perf_counter()
    extraction = extract_document(data, filename=filename, options=options)
    timings["extract"] = _ms(t)
    if extraction.status == "failed":
        return {
            "status": "failed",
            "error": extraction.error.model_dump(mode="json"),
            "parser_version": extraction.parser_version,
            "timings_ms": timings,
        }
    t = time.perf_counter()
    red = redact(extraction.text, known_names=known_names)
    timings["redact"] = _ms(t)
    t = time.perf_counter()
    sections = split_sections(red.text)
    profile = build_profile(red.text, sections, extraction.tables, as_of=as_of)
    timings["profile"] = _ms(t)
    return {
        "status": "parsed",
        "error": None,
        "text_redacted": red.text,
        "sections": sections.to_jsonb(),
        "profile": profile.model_dump(mode="json"),
        "province_codes": red.province_codes,
        "parser_version": "|".join(
            [extraction.parser_version, red.version, sections.version, profile.version]
        ),
        "warnings": [w.code for w in extraction.warnings] + red.warnings + profile.warnings,
        "timings_ms": timings,
    }


def warm_up() -> None:
    """Nạp trước Presidio/spaCy, từ điển kỹ năng, PDFium (gọi khi khởi động API / worker)."""
    from cvparser.redact import warm_up as warm_redact

    warm_redact()
    parse_cv(
        b"%PDF-1.4 warm-up", as_of=date(2026, 1, 1)
    )  # đi qua nhánh lỗi: nạp PDFium, không tốn thời gian
    build_profile("KỸ NĂNG\nPython", split_sections("KỸ NĂNG\nPython"), as_of=date(2026, 1, 1))


def _ms(t: float) -> float:
    return round((time.perf_counter() - t) * 1000, 1)
