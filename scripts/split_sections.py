"""Tách 4 section cho tin đã có trong core.jobs: uv run python scripts/split_sections.py --help."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingestion.split_jobs import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
