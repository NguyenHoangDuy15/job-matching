"""Gắn kỹ năng + vector hóa mọi tin đang mở còn thiếu, không phụ thuộc tin vào từ nguồn nào.

uv run python scripts/postprocess.py                 # ③ gắn kỹ năng + ④ vector hóa
uv run python scripts/postprocess.py --skip-embed    # chỉ ③
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.postprocess import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
