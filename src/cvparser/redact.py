"""Che thông tin cá nhân (PII) trong CV (S3-D03, US-12 AC4): tên, email, SĐT, địa chỉ, ngày sinh,
số giấy tờ, link trang cá nhân, giới tính/hôn nhân.

    from cvparser.redact import redact
    red = redact(result.text, known_names=["Nguyễn Văn Hùng"])
    red.text            # → app.cvs.text_redacted; thứ DUY NHẤT được lưu hoặc gửi ra ngoài
    red.province_codes  # tỉnh/thành tách ra trước khi che địa chỉ (gợi ý việc theo địa điểm)

Khung là Presidio (AnalyzerEngine + AnonymizerEngine). Không dùng bộ nhận diện mặc định của
Presidio: DATE_TIME sẽ che mất khoảng thời gian làm việc mà S3-D04 cần. Bộ nhận diện riêng:
  - Pattern: email (cả "[at]"), SĐT Việt Nam (kiểm đầu số + độ dài), link trang cá nhân.
  - Nhãn: "Họ tên:", "Địa chỉ:", "Ngày sinh:", "CCCD:", "Giới tính:"... → che giá trị.
  - Địa chỉ không nhãn ở phần đầu CV: đoạn có ≥ 2 từ khóa (ngõ, hẻm, phường, P.5, Q.3...).
  - Tên: dòng chỉ có họ Việt + 1–3 chữ viết hoa; dòng tên ở đầu CV; spaCy PERSON (tiếng Anh)
    chỉ được nhận ở phần đầu CV / mục khác; tên tài khoản (known_names). Tên đã tìm thấy được
    che ở MỌI chỗ (cả viết hoa, không dấu, đảo thứ tự).
  - Không che: kỹ năng trong từ điển, tổ chức/trường, tên tỉnh; khoảng thời gian không bị đụng.
  - Kiểm lần cuối: quét lại email/SĐT trên văn bản đã che.
Không ghi log nội dung; `entities` chỉ giữ loại và vị trí.
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "pii.yaml"
SPACY_MODEL = "en_core_web_sm"

_EMAIL = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
_EMAIL_OBFUSCATED = (
    r"[\w.+-]+\s*[\[(]\s*(?:at|@|a còng)\s*[\])]\s*[\w-]+"
    r"(?:\s*[\[(]\s*(?:dot|\.|chấm)\s*[\])]\s*[\w-]+)+"
)
_PHONE = r"(?<![\w.,/])(?:\(?\+?84\)?[ .\-]*|0)\d(?:[ .\-]?\d){8,10}(?![\w])"
_LINE_SEPARATORS = re.compile(r"\s*[·|•▪●]\s*|\s{3,}")


class Entity(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    start: int  # vị trí trong văn bản GỐC
    end: int
    source: str  # bộ nhận diện (không có giá trị PII)


class RedactionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    text: str
    entities: list[Entity]
    counts: dict[str, int]
    province_codes: list[int] = []
    warnings: list[str] = []


# ----------------------------------------------------------------------------- tiện ích chữ


def fold_keep_length(text: str) -> str:
    """Bỏ dấu + chữ thường, GIỮ NGUYÊN độ dài (mỗi ký tự NFC → 1 ký tự) để dùng chung offset."""
    out = []
    for ch in text:
        base = "".join(
            c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c)
        ).lower()
        base = base.replace("đ", "d")
        out.append(base[:1] if base else " ")
    return "".join(out)


def _words(pattern_list: list[str]) -> re.Pattern:
    items = sorted({re.escape(w) for w in pattern_list}, key=len, reverse=True)
    return re.compile(rf"(?<![\w])(?:{'|'.join(items)})(?![\w])")


class _Config:
    def __init__(self, data: dict) -> None:
        from ingestion.location import load_index_from_seed

        self.version: str = data["version"]
        self.placeholders: dict[str, str] = data["placeholders"]
        self.surnames: set[str] = set(data["surnames"])
        self.labels = {
            kind: _words(items) for kind, items in data["labels"].items()
        }  # khớp trên văn bản đã fold
        self.address_strong = _words(data["address_strong"])
        weak = "|".join(re.escape(w) for w in sorted(data["address_weak"], key=len, reverse=True))
        self.address_weak = re.compile(rf"(?<![\w])(?:{weak})(?![\w])")
        self.not_name = _words(data["not_name_words"])
        place = [unicodedata.normalize("NFC", w).lower() for w in data.get("place_words", [])]
        self.place_accented = _words(place)  # khớp trên chữ thường CÓ dấu
        self.place_folded = {fold_keep_length(w) for w in place}
        self.title_words = _words(data["title_words"])
        domains = "|".join(re.escape(d) for d in data["profile_domains"])
        hosts = "|".join(re.escape(d) for d in data.get("profile_hosts", []))
        self.profile_url = (
            rf"(?:https?://)?(?:www\.)?(?:{domains})/[^\s,;)\]]+"
            rf"|(?:https?://)?[\w-]+\.(?:{hosts})(?:/[^\s,;)\]]*)?"
        )
        self.provinces = load_index_from_seed()


@lru_cache(maxsize=2)
def load_config(path: str | Path = DEFAULT_CONFIG) -> _Config:
    return _Config(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _lines(text: str):
    pos = 0
    for raw in text.split("\n"):
        yield pos, raw
        pos += len(raw) + 1


def _is_cap_word(w: str) -> bool:
    letters = [c for c in w if c.isalpha()]
    return bool(letters) and len(letters) == len(w) and (w[0].isupper()) and len(w) <= 8


def _not_name(phrase: str, cfg: _Config) -> bool:
    """Cụm có từ tổ chức/địa danh nên không phải tên người. Từ địa danh trùng tên khi bỏ dấu
    ("Quận"/"Quân") so có dấu; cụm không dấu thì chỉ tính khi đứng đầu."""
    folded = fold_keep_length(phrase)
    if cfg.not_name.search(folded):
        return True
    lower = unicodedata.normalize("NFC", phrase).lower()
    if cfg.place_accented.search(lower):
        return True
    if folded == lower:  # không dấu: "VO DUC QUAN" là tên, "QUAN 3" / "PHUONG 5" không phải
        first = folded.split()[0] if folded.split() else ""
        return first in cfg.place_folded
    return False


def _province_code(segment: str, cfg: _Config) -> int | None:
    from ingestion.location import normalize_key

    key = normalize_key(segment)
    for prefix in ("thanh pho ", "tp ", "tinh "):
        if key.startswith(prefix):
            key = key[len(prefix) :]
    return cfg.provinces.aliases.get(key)


def _is_place(phrase: str, cfg: _Config) -> bool:
    return _province_code(phrase, cfg) is not None


# ----------------------------------------------------------------------------- nhận diện riêng


def _label_spans(text: str, cfg: _Config) -> list[tuple[str, int, int, str]]:
    """(loại, start, end, nguồn) của giá trị sau nhãn "Họ tên:", "Địa chỉ:"..."""
    folded = fold_keep_length(text)
    out = []
    for kind, pattern in cfg.labels.items():
        for m in pattern.finditer(folded):
            # nhãn phải ở đầu đoạn (đầu dòng hoặc sau dấu phân cách) và có ":" ngay sau
            line_start = folded.rfind("\n", 0, m.start()) + 1
            prefix = folded[line_start : m.start()]
            if prefix.strip(" -*•●▪#\t") and not re.search(r"[·|•▪●,;(]\s*$", prefix):
                continue
            colon = re.match(r"\s*[:：]\s*", folded[m.end() :])
            if not colon:
                continue
            start = m.end() + colon.end()
            stop_chars = "·|•;\n" if kind == "ADDRESS" else "·|•;,\n"
            end = start
            while end < len(text) and text[end] not in stop_chars:
                end += 1
            value = text[start:end].rstrip(" .")
            if kind == "PERSON":  # "Đặng Quốc Bảo – Trưởng phòng CNTT": chỉ che phần tên
                value = re.split(r"\s[–—-]\s|\s*[(/]", value, maxsplit=1)[0].rstrip()
            if value.strip():
                out.append((kind, start, start + len(value), "label"))
    return out


def _address_spans(text: str, header_end: int, cfg: _Config) -> list[tuple[str, int, int, str]]:
    """Địa chỉ không nhãn trong phần đầu CV: đoạn có ≥ 2 từ khóa địa chỉ (P.5, Q.3 cũng tính)."""
    out = []
    for pos, raw in _lines(text):
        if pos > header_end:
            break
        for seg in _segments(raw):
            s, e = pos + seg[0], pos + seg[1]
            piece = text[s:e]
            if re.match(r"^[^:：\d]{1,30}[:：]", piece):
                continue  # "Địa chỉ: …" đã do bộ nhận nhãn xử lý (giữ chữ nhãn)
            folded = fold_keep_length(piece)
            hits = len(cfg.address_strong.findall(folded))
            for m in cfg.address_weak.finditer(folded):  # từ yếu: phải có số / tên riêng ngay sau
                after = piece[m.end() :].lstrip(" .")
                hits += bool(after) and (after[0].isdigit() or after[0].isupper())
            hits += len(re.findall(r"(?<![\w])[PpQq]\.\s*(?:\d|[A-ZĐ])", piece))
            if hits >= 2 and len(piece) <= 160 and "@" not in piece:
                out.append(("ADDRESS", s, e, "address_keywords"))
    return out


def _segments(raw: str) -> list[tuple[int, int]]:
    """Các đoạn của một dòng, cắt ở "·", "|", "•" (không cắt ở dấu phẩy)."""
    out, last = [], 0
    for m in _LINE_SEPARATORS.finditer(raw):
        out.append((last, m.start()))
        last = m.end()
    out.append((last, len(raw)))
    return [(a, b) for a, b in out if raw[a:b].strip()]


def _strip_prefix(raw: str) -> tuple[int, str]:
    m = re.match(r"^[\s\-–•●▪*#-]*", raw)
    return m.end(), raw[m.end() :].rstrip(" .,;:")


def _name_line(raw: str, cfg: _Config, *, surname_first_only: bool) -> tuple[int, int] | None:
    """Cả dòng là một tên người: 2–4 chữ viết hoa, có họ Việt (đầu, hoặc cuối nếu cho phép)."""
    from cvparser.sections import match_heading

    off, body = _strip_prefix(raw)
    words = body.split()
    if not 2 <= len(words) <= 4 or not all(_is_cap_word(w) for w in words):
        return None
    folded = fold_keep_length(body)
    if _not_name(body, cfg) or cfg.title_words.search(folded) or _is_place(body, cfg):
        return None
    if match_heading(body):
        return None
    first, last = fold_keep_length(words[0]), fold_keep_length(words[-1])
    if first in cfg.surnames or (not surname_first_only and last in cfg.surnames):
        return off, off + len(body)
    return None


def _first_line_name(text: str, cfg: _Config) -> tuple[int, int] | None:
    """Dòng tên ở đầu CV dù không có họ Việt ("Hung Nguyen", "John Smith"): 2–5 chữ viết hoa,
    không phải chức danh / tiêu đề mục, nằm trong 3 dòng đầu."""
    from cvparser.sections import match_heading

    seen = 0
    for pos, raw in _lines(text):
        if not raw.strip():
            continue
        seen += 1
        if seen > 3:
            return None
        off, body = _strip_prefix(raw)
        words = body.split()
        folded = fold_keep_length(body)
        if (
            2 <= len(words) <= 5
            and all(_is_cap_word(w) for w in words)
            and not cfg.title_words.search(folded)
            and not _not_name(body, cfg)
            and not match_heading(body)
            and not _is_place(body, cfg)
        ):
            return pos + off, pos + off + len(body)
    return None


# ----------------------------------------------------------------------------- Presidio


@lru_cache(maxsize=1)
def _engines():
    """AnalyzerEngine (pattern + spaCy PERSON) và AnonymizerEngine; nạp một lần mỗi tiến trình."""
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import SpacyRecognizer
    from presidio_anonymizer import AnonymizerEngine

    cfg = load_config()

    class VnPhoneRecognizer(PatternRecognizer):
        def validate_result(self, pattern_text: str) -> bool:
            digits = re.sub(r"\D", "", pattern_text)
            if digits.startswith("84"):
                digits = "0" + digits[2:]
            return len(digits) in (10, 11) and digits[0] == "0" and digits[1] in "235789"

    registry = RecognizerRegistry(supported_languages=["en"])
    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="EMAIL",
            patterns=[Pattern("email", _EMAIL, 1.0), Pattern("email_obf", _EMAIL_OBFUSCATED, 0.9)],
            global_regex_flags=re.IGNORECASE | re.UNICODE,
        )
    )
    registry.add_recognizer(
        VnPhoneRecognizer(supported_entity="PHONE", patterns=[Pattern("vn_phone", _PHONE, 0.9)])
    )
    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="PROFILE_URL",
            patterns=[Pattern("profile_url", cfg.profile_url, 0.95)],
            global_regex_flags=re.IGNORECASE,
        )
    )
    registry.add_recognizer(SpacyRecognizer(supported_entities=["PERSON"]))
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": SPACY_MODEL}],
        }
    )
    analyzer = AnalyzerEngine(
        registry=registry, nlp_engine=provider.create_engine(), supported_languages=["en"]
    )
    return analyzer, AnonymizerEngine()


def _skill_spans(text: str) -> list[tuple[int, int]]:
    """Vị trí kỹ năng trong từ điển: spaCy PERSON trùng chỗ này thì bỏ (che nhầm kỹ năng)."""
    from skillkit.levels.pipeline import SKILLS_YAML
    from skillkit.matcher import prepare

    matcher = _matcher(str(SKILLS_YAML))
    cased, _ = prepare(text)
    if cased != text:  # prepare gộp khoảng trắng: dò theo từng dòng để giữ offset
        out = []
        for pos, raw in _lines(text):
            if raw.strip() and prepare(raw)[0] == raw:
                out += [(pos + m.start, pos + m.end) for m in matcher.find(raw)]
        return out
    return [(m.start, m.end) for m in matcher.find(text)]


@lru_cache(maxsize=1)
def _matcher(path: str):
    from skillkit.matcher import SkillMatcher
    from skillkit.taxonomy import load_taxonomy

    return SkillMatcher(load_taxonomy(path))


def _overlaps(a: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    return any(a[0] < e and s < a[1] for s, e in spans)


def _name_variants(name: str) -> list[str]:
    words = name.split()
    out = {name}
    if len(words) >= 2:
        out.add(" ".join([*words[1:], words[0]]))  # "Hùng Nguyễn Văn", "Hung Nguyen"
        out.add(f"{words[-1]} {words[0]}")  # "Hùng Nguyễn"
    return sorted(out, key=len, reverse=True)


def _propagate_names(text: str, names: list[str]) -> list[tuple[int, int]]:
    """Mọi chỗ xuất hiện của các tên đã tìm thấy (không phân biệt hoa/thường, dấu, khoảng trắng)."""
    folded = fold_keep_length(text)
    spans = []
    for name in names:
        for variant in _name_variants(" ".join(name.split())):
            key = fold_keep_length(variant)
            pattern = r"(?<![\w])" + r"\s+".join(map(re.escape, key.split())) + r"(?![\w])"
            spans += [(m.start(), m.end()) for m in re.finditer(pattern, folded)]
        # "Tôi là Hùng", "I am Hung": tên gọi đứng riêng sau cụm giới thiệu
        given = fold_keep_length(name.split()[-1])
        intro = rf"(?:toi la|toi ten la|toi ten|minh la|i am|i'm|my name is)\s+({re.escape(given)})"
        spans += [(m.start(1), m.end(1)) for m in re.finditer(rf"(?<![\w]){intro}(?![\w])", folded)]
    return spans


# ----------------------------------------------------------------------------- API


def redact(text: str, *, known_names: tuple[str, ...] | list[str] = ()) -> RedactionResult:
    from presidio_analyzer import RecognizerResult
    from presidio_anonymizer.entities import OperatorConfig

    from cvparser.sections import split_sections

    cfg = load_config()
    analyzer, anonymizer = _engines()
    sections = split_sections(text)
    # Phần đầu CV: hết mục header đầu tiên (tên, liên hệ). Địa chỉ không nhãn chỉ tìm ở đây.
    header_end = next((s.start for s in sections.sections if s.name != "header"), len(text))
    skill_spans = _skill_spans(text)

    found: list[tuple[str, int, int, str]] = []
    for r in analyzer.analyze(text=text, language="en", score_threshold=0.5):
        source = r.recognition_metadata.get("recognizer_name", "") if r.recognition_metadata else ""
        if r.entity_type == "PERSON":
            if source != "SpacyRecognizer":
                continue
            span_text = text[r.start : r.end]
            region = sections.section_at(r.start)
            words = span_text.split()
            ok = (
                "\n" not in span_text
                and (r.start <= header_end or region in ("header", "other"))
                and 2 <= len(words) <= 4
                and all(_is_cap_word(w) for w in words)
                and not _not_name(span_text, cfg)
                and not cfg.title_words.search(fold_keep_length(span_text))
                and not _is_place(span_text, cfg)
                and not _overlaps((r.start, r.end), skill_spans)
            )
            if ok:
                found.append(("PERSON", r.start, r.end, "spacy"))
        else:
            found.append((r.entity_type, r.start, r.end, "pattern"))

    found += _label_spans(text, cfg)
    found += _address_spans(text, header_end, cfg)
    address = [(s, e) for kind, s, e, _ in found if kind == "ADDRESS"]
    found = [f for f in found if not (f[3] == "spacy" and _overlaps((f[1], f[2]), address))]
    for pos, raw in _lines(text):
        span = _name_line(raw, cfg, surname_first_only=pos > header_end)
        if span:
            found.append(("PERSON", pos + span[0], pos + span[1], "name_line"))
    first = _first_line_name(text, cfg)
    if first:
        found.append(("PERSON", first[0], first[1], "first_line"))

    # Tên tìm thấy + tên tài khoản → che mọi chỗ xuất hiện.
    names = [text[s:e] for kind, s, e, _ in found if kind == "PERSON"] + list(known_names)
    names = [n for n in dict.fromkeys(" ".join(n.split()) for n in names) if len(n.split()) >= 2]
    found += [
        ("PERSON", s, e, "propagate")
        for s, e in _propagate_names(text, names)
        if all(w[0].isupper() for w in text[s:e].split())  # "Cổng thanh toán" không phải tên
    ]

    # Link trang cá nhân tìm qua nhãn ("Portfolio: an.dev") → che mọi chỗ cùng link (CV song ngữ
    # ghi lại ở dòng không có nhãn).
    links = {text[s:e] for kind, s, e, _ in found if kind == "PROFILE_URL" and e - s >= 4}
    for link in links:
        found += [
            ("PROFILE_URL", m.start(), m.end(), "propagate")
            for m in re.finditer(rf"(?<![\w.-]){re.escape(link)}(?![\w-])", text)
        ]

    # Địa chỉ: giữ phần tỉnh/thành ở cuối (không phải PII, cần cho gợi ý theo địa điểm).
    provinces: list[int] = []
    adjusted = []
    for kind, s, e, source in found:
        if (
            kind == "PROFILE_URL"
        ):  # giữ tên miền ("github.com/" là bằng chứng công cụ), che tài khoản
            domain = re.search(r"\.[a-z]{2,3}/", text[s:e])
            s = s + domain.end() if domain else s
        if kind == "ADDRESS":
            parts = text[s:e].split(",")
            while len(parts) > 1:
                code = _province_code(parts[-1], cfg)
                if code is None:
                    break
                provinces.append(code)
                parts = parts[:-1]
            e = s + len(",".join(parts).rstrip())
            code = _province_code(text[s:e], cfg)
            if code is not None:  # cả đoạn chỉ là tên tỉnh: không che
                provinces.append(code)
                continue
        adjusted.append((kind, s, e, source))

    results = [
        RecognizerResult(entity_type=kind, start=s, end=e, score=1.0)
        for kind, s, e, _ in adjusted
        if e > s
    ]
    operators = {
        kind: OperatorConfig("replace", {"new_value": value})
        for kind, value in cfg.placeholders.items()
    }
    redacted = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators).text

    # Kiểm lần cuối: không được còn email/SĐT nào.
    warnings = []
    for kind, pattern in (("EMAIL", _EMAIL), ("PHONE", _PHONE)):
        leftovers = [
            m for m in re.finditer(pattern, redacted) if kind != "PHONE" or _valid_phone(m.group())
        ]
        if leftovers:
            warnings.append(f"leak_guard_{kind.lower()}")
            redacted = re.sub(
                pattern,
                lambda m, k=kind: (
                    cfg.placeholders[k] if k != "PHONE" or _valid_phone(m.group()) else m.group()
                ),
                redacted,
            )

    entities = sorted(
        {Entity(type=k, start=s, end=e, source=src) for k, s, e, src in adjusted if e > s},
        key=lambda x: (x.start, x.end),
    )
    counts: dict[str, int] = {}
    for ent in entities:
        counts[ent.type] = counts.get(ent.type, 0) + 1
    return RedactionResult(
        version=cfg.version,
        text=redacted,
        entities=entities,
        counts=counts,
        province_codes=list(dict.fromkeys(provinces)),
        warnings=warnings,
    )


def _valid_phone(s: str) -> bool:
    digits = re.sub(r"\D", "", s)
    if digits.startswith("84"):
        digits = "0" + digits[2:]
    return len(digits) in (10, 11) and digits[0] == "0" and digits[1] in "235789"


def warm_up() -> None:
    """Nạp Presidio + spaCy trước (gọi khi khởi động worker/API để request đầu không chậm)."""
    redact("Nguyễn Văn A\nEmail: a@example.com")
