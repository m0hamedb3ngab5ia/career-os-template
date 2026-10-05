"""`careeros apply plan <job_id>` as a subprocess on a temp repo root, schema from the recorded fixture."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import FILLED_IDENTITY, FIXTURES, PY, ready_env, subprocess_env

pytestmark = pytest.mark.integration


def test_apply_plan_writes_fill_plan(temp_root: Path, tmp_path: Path):
    job_id = "ledgerline-8128744"
    jd = temp_root / "data" / "jobs" / job_id
    jd.mkdir(parents=True)
    (jd / "posting.json").write_text(json.dumps({
        "job_id": job_id, "company": "Ledgerline", "title": "Software Engineer, New Grad", "ats": "greenhouse",
        "source_slug": "ledgerline", "ats_job_id": "8128744", "url": "https://example.com/j"}))
    (jd / "resume.pdf").write_bytes(b"%PDF-1.4")
    home = tmp_path / "home"
    home.mkdir()
    env = ready_env(temp_root, home)
    # work-auth/sponsorship set (the apply gate) but matching no form label -> those fields pause, Action Item
    sa = temp_root / "profile" / "standard_answers.yaml"
    d = yaml.safe_load(sa.read_text())
    for x in d["answers"]:
        if x["key"] in ("work_authorization", "sponsorship"):
            x["match"] = []
    sa.write_text(yaml.safe_dump(d))
    r = subprocess.run([PY, "-m", "careeros.cli", "--root", str(temp_root), "apply", "plan", job_id,
                        "--schema-json", str(FIXTURES / "greenhouse" / "job_questions.json")],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "needs_review" in r.stdout
    plan = json.loads((jd / "fill_plan.json").read_text())
    assert plan["job_id"] == job_id and plan["ats"] == "greenhouse"
    assert plan["board"] == "ledgerline" and plan["ats_job_id"] == "8128744"
    assert plan["files"]["resume"] == str(jd / "resume.pdf") and plan["files"]["cover_letter"] is None
    by = {f["field_id"]: f for f in plan["fields"]}
    assert by["email"]["value"] == FILLED_IDENTITY["email"]
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


def _gh_job(root: Path, job_id: str = "x-1") -> Path:
    jd = root / "data" / "jobs" / job_id
    jd.mkdir(parents=True)
    (jd / "posting.json").write_text(json.dumps({
        "job_id": job_id, "company": "X", "title": "T", "ats": "greenhouse", "source_slug": "x",
        "ats_job_id": "1", "url": "https://example.com/j"}))
    return jd


def test_apply_plan_sensitive_field_blocks(temp_root: Path, tmp_path: Path):
    import careeros.cli as cli_mod

    jd = _gh_job(temp_root)
    schema = tmp_path / "q.json"
    schema.write_text(json.dumps({"questions": [{"label": "Social Security Number", "required": True,
                                                 "fields": [{"name": "question_1", "type": "input_text"}]}]}))
    assert cli_mod.main(["--root", str(temp_root), "apply", "plan", "x-1", "--schema-json", str(schema)]) == 3
    plan = json.loads((jd / "fill_plan.json").read_text())
    assert plan["blocked"] == ["Social Security Number"]


def test_apply_plan_refuses_locked_job(temp_root: Path, monkeypatch):
    import careeros.cli as cli_mod
    from careeros.config import get_settings
    from careeros.runs import locks
    from careeros.runs.store import RunStore

    monkeypatch.delenv("CAREEROS_LOCK_TOKEN", raising=False)
    jd = _gh_job(temp_root)
    locks.acquire(RunStore(get_settings(temp_root)).job_lock_path("x-1"), owner="run:other", ttl_seconds=600)
    assert cli_mod.main(["--root", str(temp_root), "apply", "plan", "x-1", "--schema-json",
                         str(FIXTURES / "greenhouse" / "job_questions.json")]) == 6
    assert not (jd / "fill_plan.json").exists()


def test_apply_plan_asks_required_unknown_once_and_keeps_edits(temp_root: Path, tmp_path: Path):
    """REQ-106: a required unknown raises one `fill plan: <id>` question Action Item (deduped on re-run); a rebuild
    keeps this job's edits and skips by field_id."""
    import careeros.cli as cli_mod

    jd = _gh_job(temp_root)
    schema = tmp_path / "q.json"
    schema.write_text(json.dumps({"questions": [
        {"label": "What is your favourite tea?", "required": True,
         "fields": [{"name": "question_1", "type": "input_text"}]},
        {"label": "Favourite biscuit", "required": False, "fields": [{"name": "question_2", "type": "input_text"}]}]}))
    args = ["--root", str(temp_root), "apply", "plan", "x-1", "--schema-json", str(schema)]
    assert cli_mod.main(args) == 0
    plan = json.loads((jd / "fill_plan.json").read_text())
    for f in plan["fields"]:
        if f["field_id"] == "question_1":
            f.update(value="Green", source="user", needs_review=False)
        if f["field_id"] == "question_2":
            f.update(skipped=True, needs_review=False)
    (jd / "fill_plan.json").write_text(json.dumps(plan))
    assert cli_mod.main(args) == 0
    by = {f["field_id"]: f for f in json.loads((jd / "fill_plan.json").read_text())["fields"]}
    assert by["question_1"]["value"] == "Green" and by["question_1"]["source"] == "user"
    assert by["question_2"]["skipped"] is True
    asks = [a for a in _actions(temp_root) if a["What to do"] == "fill plan: x-1"]
    assert len(asks) == 1 and asks[0]["Type"] == "question"
