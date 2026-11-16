"""Nhận loại file theo nội dung (magic bytes), không tin đuôi file hay mime trình duyệt gửi."""

import io
import zipfile

from cvparser.extract.errors import ErrorCode, ExtractionError
from cvparser.extract.models import ExtractOptions, FileKind

_DOCX_MAIN = "wordprocessingml.document.main+xml"
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_IMAGES = (
    b"\xff\xd8\xff",
    b"\x89PNG\r\n\x1a\n",
    b"GIF87a",
    b"GIF89a",
    b"BM",
    b"II*\x00",
    b"MM\x00*",
)


def detect_kind(data: bytes, options: ExtractOptions | None = None) -> FileKind:
    """'pdf' | 'docx', hoặc ném ExtractionError với mã lỗi phù hợp."""
    options = options or ExtractOptions()
    if not data:
        raise ExtractionError(ErrorCode.EMPTY_FILE)
    if len(data) > options.max_bytes:
        raise ExtractionError(ErrorCode.TOO_LARGE, f"{len(data)} bytes")
    if b"%PDF-" in data[:1024]:  # một số trình tạo PDF chèn vài byte rác trước header
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        _check_docx_zip(data, options)
        return "docx"
    if data.startswith(_OLE):
        # Vỏ OLE: Word 97–2003 (.doc), hoặc file Office đặt mật khẩu (luồng EncryptedPackage).
        if "EncryptedPackage".encode("utf-16-le") in data:
            raise ExtractionError(ErrorCode.ENCRYPTED, "office")
        raise ExtractionError(ErrorCode.UNSUPPORTED_TYPE, "legacy_doc")
    if data.startswith(_IMAGES) or data[8:12] in (b"WEBP", b"ftyp") or data[4:8] == b"ftyp":
        raise ExtractionError(ErrorCode.UNSUPPORTED_TYPE, "image")
    raise ExtractionError(ErrorCode.UNSUPPORTED_TYPE, "other")


def _check_docx_zip(data: bytes, options: ExtractOptions) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            unzipped = sum(i.file_size for i in infos)
            if unzipped > options.max_unzipped_bytes or (
                unzipped > 1024 * 1024 and unzipped / max(len(data), 1) > options.max_zip_ratio
            ):
                raise ExtractionError(ErrorCode.TOO_LARGE, "unzipped")
            try:
                content_types = zf.read("[Content_Types].xml").decode("utf-8", "replace")
            except KeyError:
                raise ExtractionError(ErrorCode.UNSUPPORTED_TYPE, "zip") from None
    except zipfile.BadZipFile:
        raise ExtractionError(ErrorCode.CORRUPT_FILE, "bad_zip") from None
    if _DOCX_MAIN not in content_types:
        # xlsx, pptx, odt, .docm (macroEnabled), .dotx (template) cùng vỏ ZIP.
        raise ExtractionError(ErrorCode.UNSUPPORTED_TYPE, "office_other")
