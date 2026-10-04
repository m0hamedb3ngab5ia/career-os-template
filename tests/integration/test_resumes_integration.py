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
