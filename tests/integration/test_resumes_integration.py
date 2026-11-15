"""`careeros resume list|add` via subprocess and the /api/profile/resumes HTTP API on a temp root (TASK-007)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import PY, make_temp_root, subprocess_env

pytestmark = [pytest.mark.integration, pytest.mark.readiness]

PDF = b"%PDF-1.4\nnot really a pdf\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "home").mkdir()
    return make_temp_root(tmp_path / "repo")


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=subprocess_env(root, root.parent / "home"), timeout=120)


def test_resume_cli(root: Path, tmp_path: Path):
    f = tmp_path / "cv.pdf"
    f.write_bytes(PDF)
    r = _cli(root, "resume", "add", str(f), "--name", "Main", "--json")
    assert r.returncode == 0, r.stderr
    rid = json.loads(r.stdout)["rid"]
    assert (root / "profile" / "resumes" / rid / "v1" / "original.pdf").read_bytes() == PDF
    r = _cli(root, "resume", "list", "--json")
    assert r.returncode == 0, r.stderr
    assert [(x["rid"], x["type"], x["latest"]) for x in json.loads(r.stdout)] == [(rid, "master", 1)]
    assert "Main" in _cli(root, "resume", "list").stdout
    (tmp_path / "cv.txt").write_text("x")
    r = _cli(root, "resume", "add", str(tmp_path / "cv.txt"))
    assert r.returncode == 1 and "PDF or DOCX" in r.stderr


def test_master_diff_cli_and_api(root: Path, tmp_path: Path):
    """REQ-099 / E2E-003-02: a proposal is pending until approve; reject keeps master.yaml and readiness open."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from careeros.config import Settings
    from careeros.ui.app import create_app
    from careeros.ui.index import Index
    from careeros.ui.security import LOOPBACK

    f = tmp_path / "cv.pdf"
    f.write_bytes(PDF)
    assert _cli(root, "resume", "add", str(f)).returncode == 0
    master = root / "profile" / "master.yaml"
    before = master.read_text(encoding="utf-8")
    prop = tmp_path / "proposed.yaml"
    prop.write_text(before + "\n# re-extracted\n", encoding="utf-8")
    bad = tmp_path / "bad.yaml"
    bad.write_text("experience: []\n", encoding="utf-8")
    r = _cli(root, "resume", "propose-master", str(bad))
    assert r.returncode == 1 and "identity" in r.stderr
    bad.write_text("identity: x\n", encoding="utf-8")  # wrongly-typed section: a validation problem, not a crash
    r = _cli(root, "resume", "propose-master", str(bad))
    assert r.returncode == 1 and "Traceback" not in r.stderr, r.stderr
    r = _cli(root, "resume", "propose-master", str(prop))
    assert r.returncode == 0, r.stderr
    s = Settings.load(root)
    app = create_app(s, index=Index(s), broker=None, allowed_hosts=LOOPBACK | {"testserver"}, static_dir=root / "no-static")
    W = {"X-CareerOS": "1"}
    with TestClient(app) as c:
        st = c.get("/api/profile/master/proposal", headers=W).json()
        assert st["state"] == "pending" and "re-extracted" in st["diff"]
        assert master.read_text(encoding="utf-8") == before
        synced = lambda: next(i for i in c.get("/api/readiness", headers=W).json()["items"] if i["id"] == "master_synced")
        assert not synced()["done"] and synced()["fix_link"] == "/profile#master"  # TASK-022: links to the diff panel
        assert c.post("/api/profile/master/proposal/reject", headers=W).json()["state"] == "rejected"
        assert master.read_text(encoding="utf-8") == before and not synced()["done"]
        assert c.post("/api/profile/master/proposal/approve", headers=W).status_code == 404
        assert _cli(root, "resume", "propose-master", str(prop)).returncode == 0
        assert c.post("/api/profile/master/proposal/approve", headers=W).json()["state"] == "synced"
        assert master.read_text(encoding="utf-8") == prop.read_text(encoding="utf-8") and synced()["done"]


V1 = "Jane Doe\nExperience\nAcme Corp, Engineer 2021-2023\n- Supported migration of 12 services to Python\n"


def test_feedback_cli_and_edit_run_launches_extract(root: Path, tmp_path: Path):
    from careeros import resume_feedback, resumes
    from careeros.config import Settings
    from careeros.ui.services.step import run_resume_skill

    resumes.add(root, "master.pdf", PDF)  # rid is a variant here: the CLI edit spawns no extract-master run
    rid = resumes.add(root, "cv.pdf", PDF)["rid"]
    (tmp_path / "v1.txt").write_text(V1)
    assert _cli(root, "resume", "edit", rid, str(tmp_path / "v1.txt")).returncode == 2  # PR #127: no CLI hand edit
    resumes.add_text(root, rid, V1, author="user", source="edit")
    (tmp_path / "items.json").write_text(json.dumps([{"section": "Experience", "issue": "i",
                                                      "suggestion": "say what moved"}]))
    assert _cli(root, "resume", "review-save", rid, str(tmp_path / "items.json")).returncode == 0
    (tmp_path / "bad.txt").write_text(V1.replace("12 services", "40% of 12 services"))
    r = _cli(root, "resume", "apply-edit", rid, "f1", "2", str(tmp_path / "bad.txt"))
    assert r.returncode == 1 and "40%" in r.stderr  # E2E-002-02: no new version
    assert resumes.get(root, rid)["versions"][-1]["n"] == 2

    resumes.update(root, rid, type="master")
    calls = []

    def fake_run_skill(settings, kind, skill, **kw):  # the skill applies a clean rewrite
        calls.append(kind)
        if kind == "resume_edit":
            resume_feedback.apply(root, rid, "f1", V1.replace("migration of", "moving"), base=2)
        return {"id": kind, "stop_reason": "completed"}

    run_resume_skill(Settings.load(root), "resume_edit", rid, "f1", run_skill=fake_run_skill)
    assert calls == ["resume_edit", "extract_master"]  # new master version -> extract-master (REQ-099)
    run_resume_skill(Settings.load(root), "review", rid, None, run_skill=lambda *a, **kw: {"id": "r", "stop_reason": "timeout"})
    assert resume_feedback.load(root, rid)["review"]["state"] == "failed"  # REQ-094: failed + Retry


def test_import_save_cli(root: Path, tmp_path: Path):  # TASK-032: the extract-master run hands its resume.json here
    from careeros import resume_import, resumes

    rid = resumes.add_tailored(root, "Acme Dev\n• Built the thing\n", category="x", source="up")["rid"]
    resume_import.set_state(root, rid, "running", run="r1")
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"schema_version": 1, "experience": [{"company": "Acme", "title": "Dev", "bullets": [
        {"text": "Built the thing"}]}]}), encoding="utf-8")
    r = _cli(root, "resume", "import-save", rid, str(f))  # review MUST: an AI résumé is never marked user text
    assert r.returncode == 1 and "upload" in r.stderr and len(resumes.get(root, rid)["versions"]) == 1
    rid = resumes.add(root, "cv.pdf", PDF)["rid"]
    (resumes._dir(root, rid) / "v1" / "text.txt").write_text("Acme Dev\n• Built the thing\n", encoding="utf-8")
    resume_import.set_state(root, rid, "running", run="r2")
    f.write_text(json.dumps({"schema_version": 1, "experience": [{"company": "Acme", "bullets": [
        {"text": "Built 40 things"}]}]}), encoding="utf-8")
    r = _cli(root, "resume", "import-save", rid, str(f))
    assert r.returncode == 1 and "not in the uploaded text" in r.stderr
    f.write_text(json.dumps({"schema_version": 1, "experience": [{"company": "Acme", "title": "Dev", "bullets": [
        {"text": "Built the thing"}]}]}), encoding="utf-8")
    resume_import.set_state(root, rid, "running", run="r3")  # Retry
    r = _cli(root, "resume", "import-save", rid, str(f))
    assert r.returncode == 0, r.stderr
    assert resume_import.load(root, rid)["state"] == "done" and "v2" in r.stdout
