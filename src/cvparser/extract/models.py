"""Kiểu dữ liệu của tầng trích văn bản (pydantic v2, bất biến, ra JSON được)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cvparser.extract.errors import MESSAGES_VI, ErrorCode

FileKind = Literal["pdf", "docx"]
BlockKind = Literal["heading", "paragraph", "list_item", "table_row"]
BlockSource = Literal["body", "header", "footer", "textbox", "table"]
BBox = tuple[float, float, float, float]

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ExtractOptions(BaseModel):
    model_config = _FROZEN

    max_bytes: int = 5 * 1024 * 1024  # khớp app.cvs.size_bytes và bucket cvs
    max_pages: int = 10
    max_chars: int = 100_000
    extract_tables: bool = True  # pdfplumber là bước chậm nhất; tắt được khi chạy lô
    max_unzipped_bytes: int = 50 * 1024 * 1024  # chặn zip bomb khi mở DOCX
    max_zip_ratio: float = 100.0


class RawBlock(BaseModel):
    """Một khối chữ do extractor trả về, chưa chuẩn hóa, chưa có offset."""

    model_config = _FROZEN

    kind: BlockKind = "paragraph"
    source: BlockSource = "body"
    text: str
    page: int | None = None
    bbox: BBox | None = None
    style: str | None = None


class Table(BaseModel):
    model_config = _FROZEN

    page: int | None = None
    bbox: BBox | None = None
    kind: Literal["data", "layout"] = "data"
    rows: list[list[str]]


class Warning_(BaseModel):
    model_config = _FROZEN

    code: str  # truncated_pages, pages_without_text, extension_mismatch, tables_failed, ...
    page: int | None = None


class RawDocument(BaseModel):
    """Kết quả thô của một Extractor."""

    model_config = _FROZEN

    blocks: list[RawBlock]
    tables: list[Table] = []
    page_count: int | None = None
    metadata: dict[str, str] = {}
    warnings: list[Warning_] = []


class Block(BaseModel):
    """Khối đã chuẩn hóa; [start, end) là vị trí trong ExtractionResult.text."""

    model_config = _FROZEN

    kind: BlockKind
    source: BlockSource
    text: str
    page: int | None = None
    bbox: BBox | None = None
    style: str | None = None
    start: int
    end: int


class Quality(BaseModel):
    model_config = _FROZEN

    char_count: int  # ký tự không phải khoảng trắng
    word_count: int
    letter_ratio: float  # chữ cái / ký tự không trắng
    garbled_ratio: float  # (cid:n), U+FFFD, ký tự vùng riêng, ký tự điều khiển / ký tự không trắng
    vi_diacritic_ratio: float  # từ có dấu tiếng Việt / từ có chữ cái
    readable: bool
    reasons: list[str] = []


class ErrorInfo(BaseModel):
    model_config = _FROZEN

    code: ErrorCode
    detail: str | None = None
    message_vi: str

    @classmethod
    def of(cls, code: ErrorCode, detail: str | None = None) -> "ErrorInfo":
        return cls(code=code, detail=detail, message_vi=MESSAGES_VI[code])


class FileInfo(BaseModel):
    model_config = _FROZEN

    sha256: str
    size_bytes: int
    kind: FileKind | None = None
    declared_ext: str | None = None
    page_count: int | None = None


class ExtractionResult(BaseModel):
    model_config = _FROZEN

    schema_version: Literal[1] = 1
    parser_version: str
    status: Literal["ok", "partial", "failed"]
    error: ErrorInfo | None = None
    file: FileInfo
    text: str = ""
    blocks: list[Block] = []
    tables: list[Table] = []
    metadata: dict[str, str] = {}
    warnings: list[Warning_] = []
    quality: Quality | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status != "failed"
