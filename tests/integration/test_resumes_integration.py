"""`careeros resume list|add` via subprocess and the /api/profile/resumes HTTP API on a temp root (TASK-007)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import PY, make_temp_root, subprocess_env

pytestmark = pytest.mark.integration

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
    W = {"X-CareerOS": "1"}
    with TestClient(app) as c:
        r = c.put("/api/profile/resumes", params={"filename": "cv.pdf"}, content=PDF, headers=W)
        assert r.status_code == 201, r.text
        a = r.json()
        assert a["n"] == 1 and a["review_run"] is None
        assert c.put("/api/profile/resumes", params={"filename": "cv.exe"}, content=PDF, headers=W).status_code == 415
        big = b"%PDF" + b"x" * (5 * 1024 * 1024)
        assert c.put("/api/profile/resumes", params={"filename": "cv.pdf"}, content=big, headers=W).status_code == 413
        b = c.put("/api/profile/resumes", params={"filename": "b.pdf"}, content=PDF, headers=W).json()["rid"]
        rows = c.get("/api/profile/resumes", headers=W).json()["resumes"]
        assert {x["rid"]: x["type"] for x in rows} == {a["rid"]: "master", b: "variant"}
        assert c.post(f"/api/profile/resumes/{b}/master", headers=W).json()["type"] == "master"
        assert c.get(f"/api/profile/resumes/{a['rid']}", headers=W).json()["type"] == "variant"
        r = c.patch(f"/api/profile/resumes/{a['rid']}", json={"name": "Old", "type": "other"}, headers=W)
        assert r.status_code == 200 and r.json()["name"] == "Old"
        v = c.get(f"/api/profile/resumes/{b}/versions/1", headers=W).json()
        assert v["author"] == "user" and "no text found" in v["ats"]["warnings"]
        assert c.delete(f"/api/profile/resumes/{b}/versions/1", headers=W).status_code == 409  # latest of master
        assert c.delete(f"/api/profile/resumes/{b}", headers=W).status_code == 409  # master
        assert c.delete(f"/api/profile/resumes/{a['rid']}", headers=W).status_code == 204
        assert c.get(f"/api/profile/resumes/{a['rid']}", headers=W).status_code == 404
