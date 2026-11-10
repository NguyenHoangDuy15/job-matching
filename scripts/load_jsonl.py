"""Nạp file JSONL tin tuyển dụng vào Supabase: uv run python scripts/load_jsonl.py --help."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.jsonl_import import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
