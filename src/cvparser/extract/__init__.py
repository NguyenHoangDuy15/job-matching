"""Trích văn bản từ PDF/DOCX (S3-D01, US-12). Hàm thuần: bytes vào, ExtractionResult ra.

    from cvparser.extract import extract_document
    result = extract_document(data, filename="cv.pdf")
    if result.ok: result.text, result.blocks, result.tables

Không biết gì về DB, Storage, API hay hàng đợi, nên API 1 file (S3-D05), worker lô (S6-D03) và
JD tải lên (US-20, US-23) cùng gọi hàm này. Không ném lỗi vì file xấu: lỗi của file thành
status="failed" + error.code. Văn bản thô chỉ nằm trong bộ nhớ, không ghi log.
"""

import hashlib
import time
from pathlib import PurePath

from cvparser.extract.docx import DocxExtractor
from cvparser.extract.errors import ErrorCode, ExtractionError
from cvparser.extract.models import (
    Block,
    ErrorInfo,
    ExtractionResult,
    ExtractOptions,
    FileInfo,
    RawDocument,
    Warning_,
)
from cvparser.extract.normalize import is_bullet, normalize_text
from cvparser.extract.pdf import PdfExtractor
from cvparser.extract.quality import measure
from cvparser.extract.registry import get_extractor, register
from cvparser.extract.sniff import detect_kind

PIPELINE_VERSION = "cvparser-1"
# Cảnh báo làm kết quả thành "partial": vẫn dùng được nhưng có thể thiếu nội dung.
HEAVY_WARNINGS = {"truncated_pages", "pages_without_text", "tables_failed", "truncated_chars"}

register(PdfExtractor())
register(DocxExtractor())

__all__ = [
    "PIPELINE_VERSION",
    "ErrorCode",
    "ExtractOptions",
    "ExtractionResult",
    "extract_document",
    "parser_version",
]


def parser_version(kind: str | None) -> str:
    extractor = get_extractor(kind) if kind else None
    return f"{PIPELINE_VERSION}/{extractor.version}" if extractor else PIPELINE_VERSION


def extract_document(
    data: bytes, *, filename: str | None = None, options: ExtractOptions | None = None
) -> ExtractionResult:
    options = options or ExtractOptions()
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    ext = PurePath(filename).suffix.lower().lstrip(".") or None if filename else None
    info = FileInfo(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data), declared_ext=ext)
    kind = None
    try:
        kind = detect_kind(data, options)
        info = info.model_copy(update={"kind": kind})
        timings["sniff"] = _ms(t0)
        t1 = time.perf_counter()
        raw = get_extractor(kind).extract(data, options)
        timings["extract"] = _ms(t1)
        t2 = time.perf_counter()
        text, blocks, warnings = _assemble(raw, options)
        timings["normalize"] = _ms(t2)
        if ext and ext != kind:
            warnings.append(Warning_(code="extension_mismatch"))
        quality = measure(text)
        if not text.strip():
            raise ExtractionError(ErrorCode.OCR_REQUIRED, "no_text")
        if "garbled" in quality.reasons:
            raise ExtractionError(ErrorCode.UNREADABLE_TEXT, f"garbled={quality.garbled_ratio}")
        heavy = any(w.code in HEAVY_WARNINGS for w in warnings) or not quality.readable
        timings["total"] = _ms(t0)
        return ExtractionResult(
            parser_version=parser_version(kind),
            status="partial" if heavy else "ok",
            file=info.model_copy(update={"page_count": raw.page_count}),
            text=text,
            blocks=blocks,
            tables=raw.tables,
            metadata=raw.metadata,
            warnings=warnings,
            quality=quality,
            timings_ms=timings,
        )
    except ExtractionError as e:
        return failed(info, e.code, e.detail, kind, timings, t0)
    except Exception as e:  # lỗi lập trình: chỉ ghi tên lớp, message có thể chứa nội dung file
        return failed(info, ErrorCode.INTERNAL_ERROR, type(e).__name__, kind, timings, t0)


def failed(
    info: FileInfo,
    code: ErrorCode,
    detail: str | None = None,
    kind: str | None = None,
    timings: dict[str, float] | None = None,
    t0: float | None = None,
) -> ExtractionResult:
    timings = dict(timings or {})
    if t0 is not None:
        timings["total"] = _ms(t0)
    return ExtractionResult(
        parser_version=parser_version(kind),
        status="failed",
        error=ErrorInfo.of(code, detail),
        file=info,
        timings_ms=timings,
    )


def _assemble(raw: RawDocument, options: ExtractOptions) -> tuple[str, list[Block], list]:
    """Chuẩn hóa từng khối rồi nối: dòng trống giữa các trang, nguồn khác nhau, trước heading."""
    warnings = list(raw.warnings)
    parts: list[str] = []
    blocks: list[Block] = []
    pos = 0
    prev = None
    for rb in raw.blocks:
        bullet = rb.kind == "list_item" or is_bullet(rb.text.lstrip())
        text = normalize_text(rb.text)
        if not text:
            continue
        kind = "list_item" if bullet and rb.kind == "paragraph" else rb.kind
        if kind == "list_item" and not is_bullet(text):
            text = "- " + text
        if prev is not None:
            new_group = rb.page != prev.page or rb.source != prev.source or kind == "heading"
            sep = "\n\n" if new_group else "\n"
            parts.append(sep)
            pos += len(sep)
        if pos + len(text) > options.max_chars:
            warnings.append(Warning_(code="truncated_chars"))
            break
        blocks.append(
            Block(
                kind=kind, source=rb.source, text=text, page=rb.page, bbox=rb.bbox,
                style=rb.style, start=pos, end=pos + len(text),
            )
        )  # fmt: skip
        parts.append(text)
        pos += len(text)
        prev = rb
    return "".join(parts), blocks, warnings


def _ms(t: float) -> float:
    return round((time.perf_counter() - t) * 1000, 2)
