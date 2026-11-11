"""S2-T05: scripts/deploy_crawl_job.sh ở chế độ DRY_RUN (chỉ in lệnh, không gọi gcloud)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy_crawl_job.sh"
POOLER_URL = "postgresql://postgres.ref:MAT_KHAU_THU@aws-0-x.pooler.supabase.com:5432/postgres"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="cần bash (Linux/macOS, CI)"
)


def _deploy(**env):
    base = {"PATH": os.environ["PATH"], "DRY_RUN": "1", "PROJECT_ID": "demo", "ALLOW_NO_MODEL": "1"}
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env={**base, **env},
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )


def _command(out: str, fragment: str) -> str:
    lines = [line for line in out.splitlines() if line.startswith("+ ") and fragment in line]
    assert len(lines) == 1, f"cần đúng 1 lệnh chứa {fragment!r}, thấy {len(lines)}"
    return lines[0]


def test_job_runs_daily_crawl_with_secret_from_secret_manager():
    result = _deploy(DATABASE_URL=POOLER_URL, CRAWL_SOURCES="itviec vietnamworks")
    assert result.returncode == 0, result.stderr
    deploy = _command(result.stdout, "run jobs deploy")
    assert (
        "--command python --args=scripts/crawl.py,run,--source=itviec,--source=vietnamworks,"
        "--run-type=daily,--max-jobs=150"
    ) in deploy
    assert "--set-secrets DATABASE_URL=job-matching-database-url:latest" in deploy
    assert "--service-account crawl-job@demo.iam.gserviceaccount.com" in deploy
    # Chuỗi kết nối chỉ đi qua stdin vào Secret Manager, không được hiện trong lệnh hay log.
    assert "MAT_KHAU_THU" not in result.stdout + result.stderr


def test_scheduler_fires_at_0200_vietnam_time():
    result = _deploy(DATABASE_URL=POOLER_URL)
    scheduler = _command(result.stdout, "scheduler jobs create http")
    assert "--schedule 0 2 * * * --time-zone Asia/Ho_Chi_Minh" in scheduler
    assert (
        "--uri https://run.googleapis.com/v2/projects/demo/locations/asia-southeast1"
        "/jobs/crawl-daily:run"
    ) in scheduler
    assert "--oauth-service-account-email crawl-scheduler@demo.iam.gserviceaccount.com" in scheduler
    # Service account của Scheduler chỉ được chạy đúng job này.
    invoker = _command(result.stdout, "run jobs add-iam-policy-binding")
    assert "crawl-scheduler@demo.iam.gserviceaccount.com --role roles/run.invoker" in invoker


def test_refuses_supabase_direct_connection():
    result = _deploy(DATABASE_URL="postgresql://postgres:x@db.abcdefgh.supabase.co:5432/postgres")
    assert result.returncode == 1
    assert "Session pooler" in result.stderr
    assert "+ gcloud" not in result.stdout


def test_refuses_to_create_secret_without_database_url():
    result = _deploy()
    assert result.returncode == 1
    assert "DATABASE_URL" in result.stderr
    assert "builds submit" not in result.stdout


def test_refuses_to_deploy_without_tier2_model():
    if (ROOT / "models" / "jev_local_v1.joblib").exists():
        pytest.skip("máy này có model")
    result = _deploy(DATABASE_URL=POOLER_URL, ALLOW_NO_MODEL="0")
    assert result.returncode == 1
    assert "jev_local_v1.joblib" in result.stderr
