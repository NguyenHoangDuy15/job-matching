"""Mỗi định dạng là một Extractor. Thêm định dạng (OCR ảnh, .doc qua LibreOffice) = viết lớp
mới rồi register(), không sửa extract_document() hay nơi gọi."""

from typing import Protocol

from cvparser.extract.models import ExtractOptions, FileKind, RawDocument


class Extractor(Protocol):
    kind: FileKind
    version: str  # tăng khi đổi logic → kết quả cũ hết hiệu lực (khóa sha256 + version)

    def extract(self, data: bytes, options: ExtractOptions) -> RawDocument:
        """Ném ExtractionError cho lỗi của file; không ghi log nội dung."""
        ...


_REGISTRY: dict[str, Extractor] = {}


def register(extractor: Extractor) -> None:
    _REGISTRY[extractor.kind] = extractor


def get_extractor(kind: str) -> Extractor | None:
    return _REGISTRY.get(kind)
