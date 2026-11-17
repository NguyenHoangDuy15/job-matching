"""Workflow lưới an toàn post-ingest: gắn kỹ năng + vector hóa tin còn thiếu, mọi nguồn."""

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "post-ingest.yml"


def _wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_runs_on_schedule_by_hand_and_after_dictionary_changes():
    wf = _wf()
    on = wf.get("on") or wf[True]
    assert on["schedule"] and "workflow_dispatch" in on
    assert "config/skills.yaml" in on["push"]["paths"]
    assert on["push"]["branches"] == ["main"]


def test_runs_shared_post_steps_with_secrets_only_from_env():
    steps = _wf()["jobs"]["post-ingest"]["steps"]
    run = steps[-1]["run"]
    assert "python scripts/postprocess.py" in run
    assert steps[-1]["env"]["DATABASE_URL"] == "${{ secrets.DATABASE_URL }}"
    for step in steps:
        assert not re.search(r"\$\{\{", step.get("run", "")), step.get("name")
