"""Mã lỗi trích văn bản và thông điệp tiếng Việt cho giao diện.

Mã lỗi ghi vào app.cvs.parse_error. `detail` không bao giờ chứa nội dung file.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    EMPTY_FILE = "empty_file"
    TOO_LARGE = "too_large"
    UNSUPPORTED_TYPE = "unsupported_type"
    ENCRYPTED = "encrypted"
    CORRUPT_FILE = "corrupt_file"
    OCR_REQUIRED = "ocr_required"
    UNREADABLE_TEXT = "unreadable_text"
    TIMEOUT = "timeout"
    INTERNAL_ERROR = "internal_error"


MESSAGES_VI: dict[ErrorCode, str] = {
    ErrorCode.EMPTY_FILE: "File rỗng, hãy chọn lại file CV.",
    ErrorCode.TOO_LARGE: "File vượt quá 5 MB, hãy giảm dung lượng rồi tải lại.",
    ErrorCode.UNSUPPORTED_TYPE: (
        "Chỉ nhận file PDF hoặc DOCX. File .doc hãy mở bằng Word và lưu lại thành .docx."
    ),
    ErrorCode.ENCRYPTED: "File đang đặt mật khẩu, hãy gỡ mật khẩu rồi tải lại.",
    ErrorCode.CORRUPT_FILE: "File bị hỏng hoặc tải lên chưa đủ, hãy tải lại.",
    ErrorCode.OCR_REQUIRED: (
        "CV có vẻ là ảnh scan nên không đọc được chữ. "
        "Hãy tải bản PDF xuất trực tiếp từ Word, Google Docs hoặc Canva."
    ),
    ErrorCode.UNREADABLE_TEXT: (
        "Không đọc được chữ trong file (lỗi phông chữ). Hãy xuất lại PDF rồi tải lên."
    ),
    ErrorCode.TIMEOUT: "Xử lý file quá lâu, hệ thống sẽ thử lại.",
    ErrorCode.INTERNAL_ERROR: "Lỗi hệ thống khi đọc file, hệ thống sẽ thử lại.",
}

# Lỗi do chính file: thử lại cũng không khác. Worker lô (S6-D03) đánh failed ngay.
PERMANENT: frozenset[ErrorCode] = frozenset(ErrorCode) - {
    ErrorCode.TIMEOUT,
    ErrorCode.INTERNAL_ERROR,
}


class ExtractionError(Exception):
    """Lỗi của file đầu vào; extract_document() đổi thành status='failed'."""

    def __init__(self, code: ErrorCode, detail: str | None = None) -> None:
        super().__init__(code.value if detail is None else f"{code.value}: {detail}")
        self.code = code
        self.detail = detail
