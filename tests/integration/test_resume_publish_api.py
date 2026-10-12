"""POST /api/profile/resumes/{rid}/publish (TASK-031, DEC-017). E2E-002-07: Given 4 items, 2 handled, When
"Next: Saved answers", Then one version, résumé master, 2 items still open."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_temp_root

from careeros import annotations as ann
from careeros import resumes

pytestmark = pytest.mark.integration

DOC = {"schema_version": 1, "identity": {"name": "Pat Doe"}, "experience": [{"id": "e1", "bullets": [
    {"id": f"b{i}", "source": f"m{i}", "text": f"Did thing {i}"} for i in range(1, 5)]}]}


def test_e2e_002_07_next_publishes_one_version_and_sets_master(tmp_path: Path):
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
    items = [ann.create(root, rid, kind="suggestion", target_id=f"b{i}", proposed=f"Did thing {i} well")
             for i in range(1, 5)]
    s = Settings.load(root)
    app = create_app(s, index=Index(s), broker=None, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=root / "no-static")
    W = {"X-CareerOS": "1"}
    base = f"/api/profile/resumes/{rid}"
    with TestClient(app) as c:
        assert c.post(f"{base}/annotations/{items[0]['id']}/accept", headers=W).status_code == 200
        assert c.post(f"{base}/annotations/{items[1]['id']}/reject", headers=W).status_code == 200
        r = c.post(f"{base}/publish", json={"key": "next-1", "master": True}, headers=W)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["published"] is True and body["n"] == 2 and body["type"] == "master"
        again = c.post(f"{base}/publish", json={"key": "next-1", "master": True}, headers=W).json()
        assert again["published"] is False and again["n"] == 2  # double click publishes once
        assert [v["n"] for v in c.get(base).json()["versions"]] == [1, 2]
        st = [a["status"] for a in c.get(f"{base}/annotations").json()]
        assert st == ["accepted", "rejected", "open", "open"]
        assert "Did thing 1 well" in c.get(f"{base}/versions/2").json()["text"]
        assert c.post(f"{base}/publish", json={"key": ""}, headers=W).status_code == 422
