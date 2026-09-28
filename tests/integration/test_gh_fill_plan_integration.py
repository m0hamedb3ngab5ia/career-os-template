"""`careeros apply plan <job_id>` as a subprocess on a temp repo root, schema from the recorded fixture."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import FIXTURES, PY, subprocess_env

pytestmark = pytest.mark.integration


def test_apply_plan_writes_fill_plan(temp_root: Path, tmp_path: Path):
    job_id = "ledgerline-8128744"
    jd = temp_root / "data" / "jobs" / job_id
    jd.mkdir(parents=True)
    (jd / "posting.json").write_text(json.dumps({
        "job_id": job_id, "company": "Ledgerline", "title": "Software Engineer, New Grad", "ats": "greenhouse",
        "source_slug": "ledgerline", "ats_job_id": "8128744", "url": "https://example.com/j"}))
    (jd / "resume.pdf").write_bytes(b"%PDF-1.4")
    # no work-auth/sponsorship answers stored -> those fields pause and raise an Action Item
    (temp_root / "profile" / "standard_answers.yaml").write_text(
        "answers:\n  - key: current_employer\n    match: ['current or previous employer']\n    answer: Foo\n")
    home = tmp_path / "home"
    home.mkdir()
    r = subprocess.run([PY, "-m", "careeros.cli", "--root", str(temp_root), "apply", "plan", job_id,
                        "--schema-json", str(FIXTURES / "greenhouse" / "job_questions.json")],
                       capture_output=True, text=True, env=subprocess_env(temp_root, home), timeout=120)
    assert r.returncode == 0, r.stderr
    assert "needs_review" in r.stdout
    plan = json.loads((jd / "fill_plan.json").read_text())
    assert plan["job_id"] == job_id and plan["ats"] == "greenhouse"
    assert plan["board"] == "ledgerline" and plan["ats_job_id"] == "8128744"
    assert plan["files"]["resume"] == str(jd / "resume.pdf") and plan["files"]["cover_letter"] is None
    by = {f["field_id"]: f for f in plan["fields"]}
    assert by["email"]["value"] == "alex@example.com"
    assert by["resume"]["value"] == str(jd / "resume.pdf")
    assert any(str(a["JobID"]) == job_id and a["Type"] == "question" and a["What to do"] == f"fill plan: {job_id}"
               for a in _actions(temp_root))


def _actions(root: Path):
    from careeros.config import get_settings
    from careeros.tracker import Tracker

    return Tracker(settings=get_settings(root)).list_action_items()


def test_apply_plan_fetch_failure_exits_1(temp_root: Path, tmp_path: Path, monkeypatch, capsys):
    import careeros.apply.gh_schema as gs
    import careeros.cli as cli_mod
    from careeros.scout.base import BoardNotFound

    job_id = "x-1"
    jd = temp_root / "data" / "jobs" / job_id
    jd.mkdir(parents=True)
    (jd / "posting.json").write_text(json.dumps({
        "job_id": job_id, "company": "X", "title": "T", "ats": "greenhouse", "source_slug": "x",
        "ats_job_id": "1", "url": "https://example.com/j"}))

    def boom(*a, **k):
        raise BoardNotFound("u")

    monkeypatch.setattr(gs, "fetch_questions", boom)
    assert cli_mod.main(["--root", str(temp_root), "apply", "plan", job_id]) == 1
    assert "u" in capsys.readouterr().err
