"""GET/PUT /api/profile/resumes/{rid}/draft on a temp root (TASK-028, DEC-014): autosave, stale rev -> 409."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from conftest import make_temp_root

from careeros import resumes

pytestmark = pytest.mark.integration

DOC = {"schema_version": 1, "experience": [{"id": "experience-1", "bullets": [
    {"id": "experience-1.b1", "source": "b-a", "text": "Built the thing"}]}]}


def test_draft_api(tmp_path: Path):
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
    leftover = root / "profile/resumes" / rid / ".draft.json.1.dead.tmp"
    leftover.write_text("{")
    os.utime(leftover, (0, 0))
    s = Settings.load(root)
    app = create_app(s, index=Index(s), broker=None, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=root / "no-static")
    assert not leftover.exists()  # startup cleanup
    W = {"X-CareerOS": "1"}
    url = f"/api/profile/resumes/{rid}/draft"
    with TestClient(app) as c:
        r = c.get(url)
        assert r.status_code == 200 and (r.json()["rev"], r.json()["draft"]) == (0, False)
        edited = json.loads(json.dumps(DOC))
        edited["experience"][0]["bullets"].append({"id": "x", "text": "Mine", "origin": "user"})
        r = c.put(url, json={"rev": 0, "resume": edited, "author": "user"}, headers=W)
        assert r.status_code == 200 and (r.json()["rev"], r.json()["draft"]) == (1, True)
        r = c.put(url, json={"rev": 0, "resume": DOC, "author": "user"}, headers=W)
        assert r.status_code == 409 and "reload" in r.json()["detail"]
        edited["experience"][0]["bullets"][1]["text"] = "AI version"
        r = c.put(url, json={"rev": 1, "resume": edited, "author": "ai"}, headers=W)
        assert r.status_code == 422 and "origin" in r.json()["detail"]
        assert c.get(url).json()["rev"] == 1
        assert c.get("/api/profile/resumes/nope/draft").status_code == 404
