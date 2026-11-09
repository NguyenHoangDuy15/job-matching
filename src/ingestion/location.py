"""Chuẩn hóa địa điểm tin tuyển dụng về 34 tỉnh/thành mới và gắn hình thức làm việc (S2-D01, US-09).

Bảng tra cứu lấy từ ref.provinces và ref.province_legacy. Khi chạy thật, pipeline nạp hai bảng
này từ DB; khi test hoặc chạy offline thì đọc từ db/seed/seed_reference_data.sql.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

WorkMode = Literal["onsite", "hybrid", "remote", "unknown"]  # khớp enum core.work_mode

DEFAULT_SEED = Path(__file__).resolve().parents[2] / "db" / "seed" / "seed_reference_data.sql"

# Tách một chuỗi nhiều địa điểm: "Hà Nội & Hồ Chí Minh", "Hà Nội, Đà Nẵng".
# Không tách theo "-": sẽ cắt hỏng "Bà Rịa - Vũng Tàu".
_SEPARATORS = re.compile(r"\s*(?:[&,;/|+\n]|\s(?:và|and)\s)\s*", re.IGNORECASE)
_PREFIXES = ("thanh pho ", "tp ", "tinh ")
# Hậu tố TopCV thêm sau tên tỉnh mới: "Hồ Chí Minh (mới)".
_SUFFIX = re.compile(r"\s+(?:moi|cu)$")
_REMOTE = re.compile(r"\b(?:remote|work from home|wfh|lam viec tu xa|tu xa)\b")
_HYBRID = re.compile(r"\bhybrid\b")


class ProvinceDataError(ValueError):
    """Bảng tỉnh hoặc bảng alias không nhất quán."""


def normalize_key(text: str) -> str:
    """Chữ thường, bỏ dấu (cả đ → d), dấu câu thành khoảng trắng: cùng dạng với alias_norm."""
    decomposed = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", no_marks).split())


@dataclass(frozen=True)
class ProvinceIndex:
    names: dict[int, str]  # mã tỉnh → tên chuẩn, 34 dòng
    aliases: dict[str, int]  # khóa đã chuẩn hóa → mã tỉnh


def build_index(provinces: dict[int, str], aliases: dict[str, int]) -> ProvinceIndex:
    """Gộp tên chuẩn và alias thành một bảng tra; báo lỗi nếu alias trỏ sai hoặc trùng."""
    table: dict[str, int] = {}

    def add(raw: str, code: int) -> None:
        if code not in provinces:
            raise ProvinceDataError(f"alias '{raw}' trỏ tới mã tỉnh {code} không tồn tại")
        key = normalize_key(raw)
        owner = table.setdefault(key, code)
        if owner != code:
            raise ProvinceDataError(f"'{key}' trỏ tới cả mã {owner} và {code}")

    for code, name in provinces.items():
        add(name, code)
    for raw, code in aliases.items():
        add(raw, code)
    return ProvinceIndex(names=dict(provinces), aliases=table)


def _insert_block(sql: str, table: str) -> str:
    match = re.search(
        rf"insert into {re.escape(table)}\b.*?values(.*?)on conflict", sql, re.S | re.I
    )
    if not match:
        raise ProvinceDataError(f"không thấy lệnh insert vào {table}")
    return match.group(1)


def load_index_from_seed(path: str | Path = DEFAULT_SEED) -> ProvinceIndex:
    """Đọc hai lệnh insert ref.provinces và ref.province_legacy trong file seed."""
    sql = Path(path).read_text(encoding="utf-8")
    provinces = {
        int(code): name
        for code, name in re.findall(
            r"\(\s*(\d+)\s*,\s*'([^']*)'", _insert_block(sql, "ref.provinces")
        )
    }
    aliases = {
        alias: int(code)
        for alias, code in re.findall(
            r"\(\s*'([^']*)'\s*,\s*(\d+)\s*\)", _insert_block(sql, "ref.province_legacy")
        )
    }
    return build_index(provinces, aliases)


@dataclass(frozen=True)
class LocationResult:
    province_codes: tuple[int, ...]  # giữ thứ tự xuất hiện, không trùng
    work_mode: WorkMode
    unmatched: tuple[str, ...]  # phần không nhận ra, để báo cáo và bổ sung alias

    @property
    def is_parsed(self) -> bool:
        """Đạt theo US-09/AC3: có tỉnh chuẩn hoặc nhãn Remote."""
        return bool(self.province_codes) or self.work_mode == "remote"


def _exact(key: str, aliases: dict[str, int]) -> int | None:
    if key in aliases:
        return aliases[key]
    for prefix in _PREFIXES:
        if key.startswith(prefix) and key[len(prefix) :] in aliases:
            return aliases[key[len(prefix) :]]
    return None


def _scan(key: str, aliases: dict[str, int]) -> list[int]:
    """Tìm alias nằm trong một cụm dài hơn, ví dụ "quận 1 hồ chí minh".

    Chỉ nhận alias từ 2 từ trở lên và ưu tiên cụm dài nhất, để "vinh" không khớp
    nhầm trong "vinh yen" và "vinh long" không bị đọc thành "vinh".
    """
    tokens = key.split()
    found: list[int] = []
    i = 0
    while i < len(tokens):
        for n in range(len(tokens) - i, 1, -1):
            code = aliases.get(" ".join(tokens[i : i + n]))
            if code is not None:
                found.append(code)
                i += n
                break
        else:
            i += 1
    return found


def _segment_codes(segment: str, aliases: dict[str, int]) -> tuple[list[int], bool]:
    """Trả (mã tỉnh, nhận ra được hay không) cho một đoạn địa điểm."""
    key = _SUFFIX.sub("", normalize_key(segment))
    key = " ".join(_HYBRID.sub(" ", _REMOTE.sub(" ", key)).split())
    if not key:  # đoạn chỉ có "Remote"/"Hybrid": không phải địa điểm, cũng không phải lỗi
        return [], True
    code = _exact(key, aliases)
    if code is not None:
        return [code], True
    codes = _scan(key, aliases)
    return codes, bool(codes)


def detect_work_mode(text: str, has_province: bool) -> WorkMode:
    key = normalize_key(text)
    if _HYBRID.search(key):  # "Hybrid/Remote" vẫn có ngày lên văn phòng
        return "hybrid"
    if _REMOTE.search(key):
        return "remote"
    return "onsite" if has_province else "unknown"


def normalize_location(
    location: str | None, title: str | None = None, index: ProvinceIndex | None = None
) -> LocationResult:
    """Chuẩn hóa trường địa điểm thô; tiêu đề chỉ dùng để nhận Remote/Hybrid."""
    index = index or default_index()
    location = location or ""
    codes: list[int] = []
    unmatched: list[str] = []

    whole = _exact(_SUFFIX.sub("", normalize_key(location)), index.aliases)
    if whole is not None:
        codes.append(whole)
    else:
        for segment in filter(None, (s.strip() for s in _SEPARATORS.split(location))):
            found, ok = _segment_codes(segment, index.aliases)
            codes.extend(found)
            if not ok:
                unmatched.append(normalize_key(segment))

    unique = tuple(dict.fromkeys(codes))
    mode = detect_work_mode(f"{location} {title or ''}", has_province=bool(unique))
    return LocationResult(province_codes=unique, work_mode=mode, unmatched=tuple(unmatched))


def job_location_rows(job_id: int, result: LocationResult) -> list[tuple[int, int]]:
    """Các dòng (job_id, province_code) để ghi vào core.job_locations."""
    return [(job_id, code) for code in result.province_codes]


def parsed_ratio(results: Iterable[LocationResult]) -> float:
    """Tỷ lệ tin đạt AC3, ghi vào ops.quality_reports.province_parsed_pct."""
    items = list(results)
    return sum(r.is_parsed for r in items) / len(items) if items else 0.0


_DEFAULT_INDEX: ProvinceIndex | None = None


def default_index() -> ProvinceIndex:
    global _DEFAULT_INDEX
    if _DEFAULT_INDEX is None:
        _DEFAULT_INDEX = load_index_from_seed()
    return _DEFAULT_INDEX
