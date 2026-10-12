"""TASK-033b API: Résumés row status, annotations by run (Apply-comment polling), CLI stamps CAREEROS_RUN_ID."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_temp_root

from careeros import annotations as ann
from careeros import resume_feedback as fb
from careeros import resume_import as imp
from careeros import resumes

pytestmark = pytest.mark.integration

DOC = {"schema_version": 1, "summary": "Eng", "experience": [{"id": "experience-1", "bullets": [
    {"id": "experience-1.b1", "source": "b-a", "text": "Built the thing"}]}]}


def _setup(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from careeros.config import Settings
    from careeros.ui.app import create_app
    from careeros.ui.index import Index
    from careeros.ui.security import LOOPBACK

    root = make_temp_root(tmp_path / "repo")
    src = tmp_path / "resume.json"
    src.write_text(json.dumps(DOC), encoding="utf-8")
    rid = resumes.add_tailored(root, "text", category="x", source="job-1", files={"resume.json": src})["rid"]
    s = Settings.load(root)
    app = create_app(s, index=Index(s), broker=None, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=root / "no-static")
    return root, rid, TestClient(app)


def test_row_status(tmp_path: Path):
    root, rid, client = _setup(tmp_path)
    with client as c:
        def status() -> str:
            return {r["rid"]: r["status"] for r in c.get("/api/profile/resumes").json()["resumes"]}[rid]

        def step():
            return {r["rid"]: r["failed_step"] for r in c.get("/api/profile/resumes").json()["resumes"]}[rid]

        assert status() == "ready"
        d = resumes.get_draft(root, rid)
        d["resume"]["summary"] = "Engineer"
        resumes.put_draft(root, rid, d["resume"], rev=d["rev"], author="user")
        assert status() == "draft"
        fb.set_review(root, rid, "running", run="r1")
        assert status() == "reviewing"
        imp.set_state(root, rid, "failed", reason="guard")
        assert status() == "failed" and step() == "import"
        imp.set_state(root, rid, "done")
        fb.set_review(root, rid, "failed", run="r1")
        assert status() == "failed" and step() == "review"
        fb.set_review(root, rid, "running", run="r2")
        assert step() is None


def test_annotations_by_run_and_cli_stamp(tmp_path: Path, capsys, monkeypatch):
    from careeros import cli

    root, rid, client = _setup(tmp_path)
    u = ann.create(root, rid, kind="comment", target_id="summary", text="shorter")
    monkeypatch.setenv("CAREEROS_RUN_ID", "run-1")
    r = ["--root", str(root), "resume"]
    assert cli.main([*r, "annotate", rid, "suggestion", "--target", "summary", "--proposed", "Engineer"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["run"] == "run-1"
    monkeypatch.setenv("CAREEROS_RUN_ID", "run-2")
    assert cli.main([*r, "annotate-reply", rid, u["id"], "kept"]) == 0
    assert json.loads(capsys.readouterr().out)["replies"][-1]["run"] == "run-2"
    url = f"/api/profile/resumes/{rid}/annotations"
    with client as c:
        assert [i["id"] for i in c.get(url).json()] == [u["id"], s["id"]]
        got = c.get(url, params={"run": "run-1"}).json()
        assert [(i["id"], i["run"]) for i in got] == [(s["id"], "run-1")]
        assert [i["id"] for i in c.get(url, params={"run": "run-2"}).json()] == [u["id"]]
        assert c.get(url, params={"run": "nope"}).json() == []
