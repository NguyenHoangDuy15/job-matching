"""S3-T05: lấy mẫu cặp tin từ Postgres thật, chỉ đọc (cần migration 0011).

Bỏ qua nếu không đặt TEST_DATABASE_URL. Chỉ chạy với DB thử, KHÔNG dùng Supabase production.
"""

import csv
import importlib.util
import os
import uuid
from pathlib import Path

import pytest

from ingestion.store import PgStore
from tests.integration.test_near_dedup_pg import BASE, EXTRA, _run, _save

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="cần TEST_DATABASE_URL trỏ tới DB thử")
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_dedup.py"


@pytest.fixture
def store():
    s = PgStore(DSN)
    if not s.can_dedup:
        s.close()
        pytest.skip("DB thử chưa chạy db/migrations/0011_exact_dedup.sql")
    yield s
    s.close()


def _script():
    spec = importlib.util.spec_from_file_location("eval_dedup", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _snapshot(store) -> tuple:
    row = store.conn.execute(
        """select (select count(*) from core.jobs where duplicate_of is not null),
                  (select count(*) from core.dedup_candidates)"""
    ).fetchone()
    store.conn.commit()
    return row


def test_sample_reads_merged_and_queued_pairs_without_writing(store, tmp_path, monkeypatch):
    tag = uuid.uuid4().hex[:8]
    a = _save(store, "itviec", tag, BASE)
    b = _save(store, "vietnamworks", tag, BASE.replace("quận 1", "Quận 1, TP.HCM"))
    c = _save(store, "careerviet", tag, BASE + EXTRA, title="Data Engineer (ETL)")
    _run(store)  # b gộp vào a, (a, c) vào hàng chờ
    before = _snapshot(store)

    monkeypatch.setenv("DATABASE_URL", DSN)
    out = tmp_path / "pairs.csv"
    assert _script().main(["sample", "--out", str(out), "--n", "100000"]) == 0
    assert _snapshot(store) == before  # không gộp, không xếp hàng chờ thêm

    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = {(int(r["job_a"]), int(r["job_b"])): r for r in csv.DictReader(f)}
    ab = rows[(a, b)]
    assert ab["da_gop"] == "1" and ab["tang"] == "gop" and ab["nhan"] == ""
    assert ab["nguon_a"] == ab["nguon_b"]  # nguồn của b đã chuyển sang tin giữ lại a
    ac = rows[(a, c)]
    assert ac["da_gop"] == "0" and ac["quyet_dinh_hien_tai"] == "review"
    assert ac["cong_ty"].startswith("Công ty T04")
    page = out.with_suffix(".html").read_text(encoding="utf-8")
    assert f"#{a}" in page and "<ins>" in page
