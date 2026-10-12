"""/api/profile/resumes/{rid}/annotations (TASK-030 part A, DEC-016): list, create, reply, accept (409/422), reject."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_temp_root

from careeros import resumes

pytestmark = pytest.mark.integration

DOC = {"schema_version": 1, "experience": [{"id": "experience-1", "bullets": [
    {"id": "experience-1.b1", "source": "b-a", "text": "Built the thing"}]}]}


def test_annotations_api(tmp_path: Path):
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
    W = {"X-CareerOS": "1"}
    url = f"/api/profile/resumes/{rid}/annotations"
    tid = "experience-1.b1"
    with TestClient(app) as c:
        assert c.get(url).json() == []
        r = c.post(url, json={"kind": "suggestion", "target_id": tid, "proposed": "Built a thing", "author": "ai"},
                   headers=W)
        assert r.status_code == 201 and r.json()["base"] == "Built the thing"
        good = r.json()["id"]
        bad = c.post(url, json={"kind": "suggestion", "target_id": tid, "proposed": "Led the thing for 9 years"},
                     headers=W).json()["id"]
        late = c.post(url, json={"kind": "suggestion", "target_id": tid, "proposed": "Built thing"}, headers=W).json()["id"]
        com = c.post(url, json={"kind": "comment", "target_id": tid, "text": "why?"}, headers=W).json()["id"]
        assert c.post(url, json={"kind": "suggestion", "target_id": tid}, headers=W).status_code == 422
        assert c.post(url, json={"kind": "comment", "target_id": "nope", "text": "x"}, headers=W).status_code == 404

        r = c.post(f"{url}/{com}/replies", json={"text": "because", "author": "ai"}, headers=W)
        assert r.status_code == 200 and r.json()["replies"][0]["author"] == "ai"
        r = c.post(f"{url}/{bad}/accept", headers=W)
        assert r.status_code == 422 and "9" in r.json()["detail"]
        r = c.post(f"{url}/{good}/accept", headers=W)
        assert r.status_code == 200 and r.json()["resume"]["experience"][0]["bullets"][0]["text"] == "Built a thing"
        assert c.get(f"/api/profile/resumes/{rid}/draft/changes").json()[-1]["author"] == "ai"
        r = c.post(f"{url}/{late}/accept", headers=W)
        assert r.status_code == 409 and r.json()["detail"]["expected"] == "Built the thing"
        assert r.json()["detail"]["current"] == "Built a thing"
        r = c.post(f"{url}/{bad}/reject", headers=W)
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        assert c.post(f"{url}/{bad}/reject", headers=W).status_code == 409
        st = {i["id"]: i["status"] for i in c.get(url).json()}
        assert st == {good: "accepted", bad: "rejected", late: "outdated", com: "outdated"}
        assert c.post(f"{url}/zz/accept", headers=W).status_code == 404
        assert c.get("/api/profile/resumes/nope/annotations").status_code == 404
