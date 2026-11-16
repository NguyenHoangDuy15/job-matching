"""S3-D01 "10/10 CV ra văn bản đọc được": kiểm tự động trên bộ CV mẫu giả.

Một CV đạt khi: không failed, quality.readable, ≥ 95% cụm mốc có nguyên vẹn, heading đúng thứ
tự, các nhóm dòng (cột trái của CV 2 cột, gạch đầu dòng của một việc) liền nhau, không có chuỗi
rác, đủ số bảng. File làm tay (cv06, cv07, cv10) chưa có thì bỏ qua (skip), không đỏ CI.
"""

import re
from pathlib import Path

import pytest
import yaml

from cvparser.extract import extract_document

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "cv"
EXPECTED = sorted((FIX / "expected").glob("cv*.yaml"))
FORBIDDEN = ("(cid:", "�")
MIN_COVERAGE = 0.95


def _flat(s: str) -> str:
    return " ".join(s.split()).lower()


def check(result, exp: dict) -> list[str]:
    """Danh sách lý do không đạt (rỗng = đạt). Dùng chung cho test và báo cáo."""
    if result.status == "failed":
        return [f"failed: {result.error.code}"]
    problems = []
    if not result.quality.readable:
        problems.append(f"không readable: {result.quality.reasons}")
    text = _flat(result.text)
    missing = [m for m in exp["landmarks"] if _flat(m) not in text]
    coverage = 1 - len(missing) / len(exp["landmarks"])
    if coverage < MIN_COVERAGE:
        problems.append(f"độ phủ mốc {coverage:.2f}, thiếu {missing[:5]}")
    for seq in exp["order"]:
        pos = [text.find(_flat(h)) for h in seq]
        if any(p < 0 for p in pos) or pos != sorted(pos):
            problems.append(f"sai thứ tự heading {seq}")
    lines = [_flat(x) for x in result.text.split("\n") if x.strip()]
    for group in exp["contiguous"]:
        want = [_flat(x) for x in group]
        hits = [i for i, x in enumerate(lines) if any(x.endswith(w) for w in want[:1])]
        ok = any([re.sub(r"^- ", "", x) for x in lines[i : i + len(want)]] == want for i in hits)
        if not ok:
            problems.append(f"nhóm dòng không liền nhau: {group[:2]}…")
    if any(f in result.text for f in FORBIDDEN):
        problems.append("có chuỗi rác")
    if len(result.tables) < exp["min_tables"]:
        problems.append(f"thiếu bảng: {len(result.tables)}/{exp['min_tables']}")
    return problems


@pytest.mark.parametrize("path", EXPECTED, ids=[p.stem for p in EXPECTED])
def test_sample_cv_is_readable(path):
    exp = yaml.safe_load(path.read_text(encoding="utf-8"))
    sample = FIX / "samples" / exp["file"]
    if not sample.exists():
        pytest.skip(f"{exp['file']} chưa làm (file làm tay, xem tests/fixtures/cv/README.md)")
    result = extract_document(sample.read_bytes(), filename=sample.name)
    assert check(result, exp) == []


def test_ten_expected_files():
    assert len(EXPECTED) == 10
