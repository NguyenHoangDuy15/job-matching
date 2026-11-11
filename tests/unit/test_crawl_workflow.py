"""S2-T05: workflow GitHub Actions chạy pipeline crawl 02:00 giờ Việt Nam mỗi ngày."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "crawl-daily.yml"


@pytest.fixture(scope="module")
def wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    # PyYAML đọc khóa `on:` thành True (YAML 1.1).
    return wf.get("on") or wf[True]


def _steps(wf: dict) -> list[dict]:
    return wf["jobs"]["crawl"]["steps"]


def test_schedule_is_0200_vietnam_time(wf):
    crons = [entry["cron"] for entry in _triggers(wf)["schedule"]]
    assert crons == ["0 19 * * *"]
    minute, hour, *rest = crons[0].split()
    assert (minute, rest) == ("0", ["*", "*", "*"])
    assert (int(hour) + 7) % 24 == 2  # cron GitHub tính theo UTC, Việt Nam là UTC+7


def test_can_be_run_by_hand_for_acceptance(wf):
    inputs = _triggers(wf)["workflow_dispatch"]["inputs"]
    assert inputs["sources"]["default"] == "itviec"
    assert inputs["max_jobs"]["default"] == "150"


def test_runs_the_same_crawl_command_as_locally(wf):
    run = _steps(wf)[-1]["run"]
    assert "python scripts/crawl.py run" in run
    assert '--run-type="$RUN_TYPE"' in run
    env = wf["jobs"]["crawl"]["env"]
    # Lượt theo lịch ghi ops.crawl_runs.run_type = 'daily', chạy tay ghi 'manual'.
    assert "'daily'" in env["RUN_TYPE"] and "'manual'" in env["RUN_TYPE"]


def test_database_url_only_comes_from_secret(wf):
    for step in _steps(wf):
        if "DATABASE_URL" in step.get("run", ""):
            assert step["env"]["DATABASE_URL"] == "${{ secrets.DATABASE_URL }}"
    assert "secrets." not in "".join(step.get("run", "") for step in _steps(wf))


def test_no_expression_inside_run_scripts(wf):
    """Giá trị người dùng nhập (inputs) chỉ đi qua biến môi trường, không chèn thẳng vào shell."""
    for step in _steps(wf):
        assert not re.search(r"\$\{\{", step.get("run", "")), step.get("name")


def test_safe_defaults(wf):
    job = wf["jobs"]["crawl"]
    assert wf["permissions"] == {"contents": "read"}
    assert wf["concurrency"]["cancel-in-progress"] is False
    assert 0 < job["timeout-minutes"] <= 120
    assert job["if"] == "github.repository == 'NguyenHoangDuy15/job-matching'"
