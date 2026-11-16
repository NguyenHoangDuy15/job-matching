"""Trích nhiều file song song bằng nhiều TIẾN TRÌNH (S3-D01; S6-D03 dùng lại cho hàng đợi).

- Không dùng thread: PDFium (thư viện C) không an toàn đa luồng, và thread không ngắt được nó.
- max_tasks_per_child: tiến trình con được thay sau N file để chặn rò bộ nhớ.
- Một file lỗi, kể cả làm chết tiến trình con, chỉ ra status="failed" cho file đó; lô chạy tiếp.
- Trả kết quả theo thứ tự xong trước (để cập nhật tiến độ từng file).

Timeout cứng từng file (kill tiến trình) chưa làm ở đây: ProcessPoolExecutor không hủy được
task đang chạy. S3-D05 / S6-D03 bọc extract_document() trong process riêng có timeout.
"""

import hashlib
import os
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context
from pathlib import Path

from cvparser.extract import extract_document, failed
from cvparser.extract.errors import ErrorCode
from cvparser.extract.models import ExtractionResult, ExtractOptions, FileInfo

Item = tuple[str, bytes | Path]  # (khóa: cv_id hoặc tên file, nội dung hoặc đường dẫn)


def _run(key: str, source: bytes | Path, options: ExtractOptions | None) -> ExtractionResult:
    if isinstance(source, Path):
        data, name = source.read_bytes(), source.name
    else:
        data, name = source, key
    return extract_document(data, filename=name, options=options)


def _crashed(source: bytes | Path, key: str) -> ExtractionResult:
    try:
        data = source.read_bytes() if isinstance(source, Path) else source
    except OSError:
        data = b""
    info = FileInfo(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
    return failed(info, ErrorCode.INTERNAL_ERROR, "worker_crashed")


def extract_many(
    items: Iterable[Item],
    *,
    workers: int | None = None,
    options: ExtractOptions | None = None,
    max_tasks_per_child: int = 50,
) -> Iterator[tuple[str, ExtractionResult]]:
    """workers=1: chạy ngay trong tiến trình hiện tại (test, debug). Mặc định: số CPU."""
    items = list(items)
    workers = workers or min(os.cpu_count() or 1, max(len(items), 1))
    if workers == 1:
        for key, source in items:
            yield key, _run(key, source, options)
        return
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=get_context("spawn"),  # không fork tiến trình đã nạp PDFium
        max_tasks_per_child=max_tasks_per_child,
    ) as pool:
        futures = {pool.submit(_run, key, source, options): (key, source) for key, source in items}
        for future in as_completed(futures):
            key, source = futures[future]
            try:
                yield key, future.result()
            except BrokenProcessPool:
                yield key, _crashed(source, key)
            except Exception:
                yield key, _crashed(source, key)
