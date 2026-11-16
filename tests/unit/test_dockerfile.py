"""Image Docker phải có mọi file code đọc lúc chạy (lỗi thật: thiếu db/seed, API không nạp được)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIRS = ["src", "config", "db/seed"]  # cvparser/ingestion đọc config/*.yaml và db/seed/*.sql


def test_dockerfile_copies_runtime_data():
    copied = re.findall(r"^COPY\s+(\S+)\s+", (ROOT / "Dockerfile").read_text(), re.M)
    for d in RUNTIME_DIRS:
        assert d in copied, f"Dockerfile thiếu COPY {d}"


def test_api_command_reads_port():
    text = (ROOT / "Dockerfile").read_text()
    assert "uvicorn api.main:app" in text and "${PORT" in text
