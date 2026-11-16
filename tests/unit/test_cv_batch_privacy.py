"""S3-D01: chạy lô không dừng vì file lỗi; bộ mẫu không chứa PII thật."""

import re
from pathlib import Path

import pypdfium2 as pdfium
import yaml
from docx import Document

from cvparser.extract import extract_document
from cvparser.extract.batch import extract_many

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "cv"
FILES = sorted(p for p in FIX.glob("*/*") if p.suffix in (".pdf", ".docx"))


def test_batch_good_and_bad_files_inline():
    items = [
        ("tot", FIX / "samples" / "cv01.pdf"),
        ("hong", b"%PDF-1.4 hong"),
        ("rong", b""),
        ("docx", (FIX / "samples" / "cv08.docx").read_bytes()),
    ]
    got = dict(extract_many(items, workers=1))
    assert got["tot"].status == "ok" and got["docx"].status == "ok"
    assert got["hong"].error.code == "corrupt_file" and got["rong"].error.code == "empty_file"


def test_batch_processes_match_inline():
    items = [(p.name, p) for p in FILES]
    inline = {k: r.text for k, r in extract_many(items, workers=1)}
    parallel = {k: r.text for k, r in extract_many(items, workers=2)}
    assert parallel == inline  # kết quả không phụ thuộc chạy song song (idempotent)


# ----------------------------------------------------------------------------- riêng tư

FAKE = yaml.safe_load((FIX / "fake_pii.yaml").read_text(encoding="utf-8"))
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?:\+84|0)[\s.]?\d{2,3}[\s.]?\d{3}[\s.]?\d{3,4}")


def _digits(s: str) -> str:
    d = re.sub(r"\D", "", s)
    return "0" + d[2:] if d.startswith("84") else d


def test_fixture_pii_is_fake():
    allowed_phones = {_digits(p) for p in FAKE["phones"]}
    for path in FILES:
        r = extract_document(path.read_bytes())
        text = r.text
        if r.status == "failed" and path.name == "scan_image_only.pdf":
            continue
        for email in EMAIL.findall(text):
            assert email.split("@")[1] in FAKE["email_domains"], f"{path.name}: email lạ"
        for phone in PHONE.findall(text):
            assert _digits(phone) in allowed_phones, (
                f"{path.name}: SĐT không có trong danh sách giả"
            )


def test_fixture_metadata_has_no_author():
    for path in FILES:
        if path.suffix == ".pdf":
            try:
                pdf = pdfium.PdfDocument(path.read_bytes())
            except pdfium.PdfiumError:
                continue  # file có mật khẩu
            meta = pdf.get_metadata_dict()
            pdf.close()
            assert not meta.get("Author"), f"{path.name}: còn tên tác giả"
        else:
            props = Document(str(path)).core_properties
            assert not props.author and not props.last_modified_by, f"{path.name}: còn tên"
