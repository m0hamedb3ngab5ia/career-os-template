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


def test_resume_http_api(root: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from careeros.config import Settings
    from careeros.ui.app import create_app
    from careeros.ui.index import Index
    from careeros.ui.security import LOOPBACK

    s = Settings.load(root)
    ix = Index(s)
    ix.rebuild()
    app = create_app(s, index=ix, broker=None, allowed_hosts=LOOPBACK | {"testserver"}, static_dir=root / "no-static")
    started = []
    app.state.run_control = lambda settings: type("RC", (), {"start_step": lambda self, k: started.append(k)})()
    W = {"X-CareerOS": "1"}
    with TestClient(app) as c:
        r = c.put("/api/profile/resumes", params={"filename": "cv.pdf"}, content=PDF, headers=W)
        assert r.status_code == 201, r.text
        a = r.json()
        assert a["n"] == 1 and a["review_run"] is None
        assert c.put("/api/profile/resumes", params={"filename": "cv.exe"}, content=PDF, headers=W).status_code == 415
        big = b"%PDF" + b"x" * (5 * 1024 * 1024)
        assert c.put("/api/profile/resumes", params={"filename": "cv.pdf"}, content=big, headers=W).status_code == 413
        chunked = iter([b"%PDF", b"x" * (5 * 1024 * 1024)])  # no Content-Length: only the streamed cap applies
        assert c.put("/api/profile/resumes", params={"filename": "cv.pdf"}, content=chunked, headers=W).status_code == 413
        assert len(c.get("/api/profile/resumes", headers=W).json()["resumes"]) == 1
        b = c.put("/api/profile/resumes", params={"filename": "b.pdf"}, content=PDF, headers=W).json()["rid"]
        rows = c.get("/api/profile/resumes", headers=W).json()["resumes"]
        assert {x["rid"]: x["type"] for x in rows} == {a["rid"]: "master", b: "variant"}
        assert c.post(f"/api/profile/resumes/{b}/master", headers=W).json()["type"] == "master"
        # E2E-003-02: marking B master launches extract-master; until a proposal is approved master.yaml is stale
        assert started == ["extract_master"]
        assert c.get("/api/profile/master/proposal", headers=W).json()["state"] == "stale"
        ready = {i["id"]: i for i in c.get("/api/readiness", headers=W).json()["items"]}
        assert not ready["master_synced"]["done"]
        assert c.post(f"/api/profile/resumes/{b}/master", headers=W).status_code == 200 and len(started) == 1
        assert c.get(f"/api/profile/resumes/{a['rid']}", headers=W).json()["type"] == "variant"
        r = c.patch(f"/api/profile/resumes/{a['rid']}", json={"name": "Old", "type": "other"}, headers=W)
        assert r.status_code == 200 and r.json()["name"] == "Old"
        v = c.get(f"/api/profile/resumes/{b}/versions/1", headers=W).json()
        assert v["author"] == "user" and "no text found" in v["ats"]["warnings"]
        assert c.delete(f"/api/profile/resumes/{b}/versions/1", headers=W).status_code == 409  # latest of master
        assert c.delete(f"/api/profile/resumes/{b}", headers=W).status_code == 409  # master
        assert c.delete(f"/api/profile/resumes/{a['rid']}", headers=W).status_code == 204
        assert c.get(f"/api/profile/resumes/{a['rid']}", headers=W).status_code == 404


def test_upload_extracts_off_the_event_loop(root: Path, monkeypatch):
    pytest.importorskip("fastapi")
    import asyncio

    from fastapi.testclient import TestClient

    from careeros import resumes
    from careeros.config import Settings
    from careeros.ui.app import create_app
    from careeros.ui.index import Index
    from careeros.ui.security import LOOPBACK

    real = resumes.add

    def add(*a, **kw):
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()  # blocking PDF/DOCX parse must not run on the event loop
        return real(*a, **kw)

    monkeypatch.setattr(resumes, "add", add)
    s = Settings.load(root)
    app = create_app(s, index=Index(s), broker=None, allowed_hosts=LOOPBACK | {"testserver"}, static_dir=root / "no-static")
    with TestClient(app) as c:
        r = c.put("/api/profile/resumes", params={"filename": "cv.pdf"}, content=PDF, headers={"X-CareerOS": "1"})
        assert r.status_code == 201, r.text


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
        assert not synced()["done"]
        assert c.post("/api/profile/master/proposal/reject", headers=W).json()["state"] == "rejected"
        assert master.read_text(encoding="utf-8") == before and not synced()["done"]
        assert c.post("/api/profile/master/proposal/approve", headers=W).status_code == 404
        assert _cli(root, "resume", "propose-master", str(prop)).returncode == 0
        assert c.post("/api/profile/master/proposal/approve", headers=W).json()["state"] == "synced"
        assert master.read_text(encoding="utf-8") == prop.read_text(encoding="utf-8") and synced()["done"]


V1 = "Jane Doe\nExperience\nAcme Corp, Engineer 2021-2023\n- Supported migration of 12 services to Python\n"


def test_feedback_lifecycle_http_api(root: Path):  # TASK-008: E2E-001-01, E2E-002-01..04
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from careeros import resume_feedback
    from careeros.config import Settings
    from careeros.ui.app import create_app
    from careeros.ui.index import Index
    from careeros.ui.security import LOOPBACK

    s = Settings.load(root)
    app = create_app(s, index=Index(s), broker=None, allowed_hosts=LOOPBACK | {"testserver"}, static_dir=root / "x")
    started = []
    app.state.run_control = lambda settings: type("RC", (), {
        "start_step": lambda self, k, **kw: started.append((k, kw.get("resume"), kw.get("item")))})()
    W = {"X-CareerOS": "1"}
    with TestClient(app) as c:
        up = c.put("/api/profile/resumes", params={"filename": "cv.pdf"}, content=PDF, headers=W).json()
        rid = up["rid"]
        assert up["review_run"] == "review" and started == [("review", rid, None)]  # REQ-094: upload starts review
        assert c.put(f"/api/profile/resumes/{rid}/text", json={"text": V1}, headers=W).json()["versions"][-1] == {
            **c.get(f"/api/profile/resumes/{rid}", headers=W).json()["versions"][-1], "n": 2, "author": "user"}
        assert started[-1] == ("extract_master", None, None)  # new master version -> extract-master (REQ-099)
        resume_feedback.save_review(root, rid, [{"section": "Experience", "issue": "weak", "suggestion": "s"}] * 2)
        f = c.get(f"/api/profile/resumes/{rid}/feedback", headers=W).json()
        assert f["review"]["state"] == "done" and [i["id"] for i in f["items"]] == ["f1", "f2"]
        assert c.post(f"/api/profile/resumes/{rid}/feedback/f1/apply", headers=W).status_code == 202
        assert started[-1] == ("resume_edit", rid, "f1")
        bad = c.put(f"/api/profile/resumes/{rid}/feedback/f1/rewrite", json={"text": V1.replace("Supported", "Led")},
                    headers=W)
        assert bad.status_code == 422 and "led" in bad.json()["detail"]  # E2E-002-04
        f1 = c.get(f"/api/profile/resumes/{rid}/feedback", headers=W).json()["items"][0]
        assert f1["state"] == "open" and "led" in f1["reason"]
        ok = c.put(f"/api/profile/resumes/{rid}/feedback/f1/rewrite",
                   json={"text": V1.replace("migration of", "moving")}, headers=W).json()
        assert ok["versions"][-1]["author"] == "ai" and ok["versions"][-1]["n"] == 3  # E2E-002-01
        assert c.post(f"/api/profile/resumes/{rid}/feedback/f1/apply", headers=W).status_code == 409  # applied
        assert c.post(f"/api/profile/resumes/{rid}/feedback/f2/comment", json={"text": "keep Python"},
                      headers=W).status_code == 202
        assert started[-1] == ("resume_edit", rid, "f2")
        assert c.post(f"/api/profile/resumes/{rid}/feedback/f2/dismiss", headers=W).json()["state"] == "dismissed"
        assert c.get("/api/profile/resumes/nope-0000/feedback", headers=W).status_code == 404


def test_feedback_cli_and_edit_run_launches_extract(root: Path, tmp_path: Path):
    from careeros import resume_feedback, resumes
    from careeros.config import Settings
    from careeros.ui.services.step import run_resume_skill

    resumes.add(root, "master.pdf", PDF)  # rid is a variant here: the CLI edit spawns no extract-master run
    rid = resumes.add(root, "cv.pdf", PDF)["rid"]
    (tmp_path / "v1.txt").write_text(V1)
    assert _cli(root, "resume", "edit", rid, str(tmp_path / "v1.txt")).returncode == 0
    (tmp_path / "items.json").write_text(json.dumps([{"section": "Experience", "issue": "i", "suggestion": "s"}]))
    assert _cli(root, "resume", "review-save", rid, str(tmp_path / "items.json")).returncode == 0
    (tmp_path / "bad.txt").write_text(V1.replace("12 services", "40% of 12 services"))
    r = _cli(root, "resume", "apply-edit", rid, "f1", str(tmp_path / "bad.txt"))
    assert r.returncode == 1 and "40%" in r.stderr  # E2E-002-02: no new version
    assert resumes.get(root, rid)["versions"][-1]["n"] == 2

    resumes.update(root, rid, type="master")
    calls = []

    def fake_run_skill(settings, kind, skill):  # the skill applies a clean rewrite
        calls.append(kind)
        if kind == "resume_edit":
            resume_feedback.apply(root, rid, "f1", V1.replace("migration of", "moving"))
        return {"id": kind, "stop_reason": "completed"}

    run_resume_skill(Settings.load(root), "resume_edit", rid, "f1", run_skill=fake_run_skill)
    assert calls == ["resume_edit", "extract_master"]  # new master version -> extract-master (REQ-099)
    run_resume_skill(Settings.load(root), "review", rid, None, run_skill=lambda *a: {"id": "r", "stop_reason": "timeout"})
    assert resume_feedback.load(root, rid)["review"]["state"] == "failed"  # REQ-094: failed + Retry
