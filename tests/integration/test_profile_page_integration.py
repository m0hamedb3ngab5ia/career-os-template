"""Profile page HTTP API (REQ-107, REQ-101, E2E-005-01) on a temp repo root built from examples/."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from conftest import make_temp_root

pytestmark = pytest.mark.integration
W = {"X-CareerOS": "1"}


@pytest.fixture
def client(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from careeros.config import Settings
    from careeros.ui.app import create_app
    from careeros.ui.index import Index
    from careeros.ui.security import LOOPBACK

    root = make_temp_root(tmp_path / "repo")
    s = Settings.load(root)
    ix = Index(s)
    ix.rebuild()
    app = create_app(s, index=ix, broker=None, allowed_hosts=LOOPBACK | {"testserver"}, static_dir=root / "no-static")
    started: list[str] = []
    app.state.run_control = lambda settings: type("RC", (), {
        "start_step": lambda self, k: started.append(k) or {"run_id": f"r{len(started)}"}})()
    with TestClient(app) as c:
        yield c, root, started


def test_saved_answers_edit_and_delete(client):
    c, root, _ = client
    rows = c.get("/api/profile/answers", headers=W).json()["answers"]
    assert any(r["key"] == "work_authorization" for r in rows) and any(r["scope"] == "eeo" for r in rows)
    r = c.put("/api/profile/answers/relocate", json={"answer": "No"}, headers=W)
    assert r.status_code == 200 and r.json()["answer"] == "No"
    assert c.delete("/api/profile/answers/relocate", headers=W).status_code == 204
    data = yaml.safe_load((root / "profile" / "standard_answers.yaml").read_text())
    assert "relocate" not in [e["key"] for e in data["answers"]]
    assert c.delete("/api/profile/answers/relocate", headers=W).status_code == 404
    assert c.put("/api/profile/answers/gender", json={"answer": "Decline", "eeo": True}, headers=W).status_code == 200


def test_lesson_delete(client):
    c, _, _ = client
    lid = c.post("/api/learning/lessons", json={"text": "Lever asks twice"}, headers=W).json()["id"]
    assert c.delete(f"/api/learning/lessons/{lid}", headers=W).status_code == 204
    assert c.get("/api/learning/lessons", headers=W).json()["lessons"] == []
    assert c.delete(f"/api/learning/lessons/{lid}", headers=W).status_code == 404


def test_writing_samples_upload_runs_learn_voice(client):
    c, root, started = client
    for name in ("a.md", "b.txt"):
        r = c.put("/api/profile/samples", params={"filename": name}, content=b"I wrote this.", headers=W)
        assert r.status_code == 201, r.text
    assert started == ["learn_voice", "learn_voice"]
    got = c.get("/api/profile/samples", headers=W).json()
    assert [x["name"] for x in got["samples"]] == ["a.md", "b.txt"]
    assert c.put("/api/profile/samples", params={"filename": "x.exe"}, content=b"x", headers=W).status_code == 415
    big = b"x" * (5 * 1024 * 1024 + 1)
    assert c.put("/api/profile/samples", params={"filename": "c.md"}, content=big, headers=W).status_code == 413
    assert c.post("/api/profile/samples/learn", headers=W).json()["learn_run"] == "r3"
    c.delete("/api/profile/samples/a.md", headers=W)
    r = c.delete("/api/profile/samples/b.txt", headers=W).json()
    assert r["samples"] == [] and r["learn_run"] is None and started == ["learn_voice"] * 4
    assert c.get("/api/profile/samples", headers=W).json()["learned"] == ""
    assert c.delete("/api/profile/samples/b.txt", headers=W).status_code == 404
