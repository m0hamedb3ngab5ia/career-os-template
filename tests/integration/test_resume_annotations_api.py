"""/api/profile/resumes/{rid}/annotations (TASK-030 part A, DEC-016): list, create, reply, accept (409/422), reject."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_temp_root

from careeros import annotations as ann
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
        # AI annotations come only through the Python API (part B CLI); HTTP is the user's UI
        good = ann.create(root, rid, kind="suggestion", target_id=tid, proposed="Built a thing", author="ai")["id"]
        bad = ann.create(root, rid, kind="suggestion", target_id=tid, proposed="Led the thing for 9 years",
                         author="ai")["id"]
        r = c.post(url, json={"kind": "suggestion", "target_id": tid, "proposed": "Built thing"}, headers=W)
        assert r.status_code == 201 and r.json()["base"] == "Built the thing"
        late = r.json()["id"]
        r = c.post(url, json={"kind": "comment", "target_id": tid, "text": "why?", "author": "ai"}, headers=W)
        assert r.json()["author"] == "user"  # author is not client-settable
        com = r.json()["id"]
        assert c.post(url, json={"kind": "suggestion", "target_id": tid}, headers=W).status_code == 422
        assert c.post(url, json={"kind": "comment", "target_id": "nope", "text": "x"}, headers=W).status_code == 404

        r = c.post(f"{url}/{com}/replies", json={"text": "because", "author": "ai"}, headers=W)
        assert r.status_code == 200 and r.json()["replies"][0]["author"] == "user"
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
        fbp = root / "profile/resumes" / rid / "feedback.json"
        fbp.write_text(json.dumps({"review": None, "items": [{"id": "f1", "section": "S", "issue": "i",
                       "suggestion": "s", "quote": None, "state": "open", "comments": [], "reason": None,
                       "v": 1}]}), encoding="utf-8")
        r = c.post(f"{url}/f1/reject", headers=W)  # a migrated review item, rejected over the API
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        assert {i["id"]: i["status"] for i in c.get(url).json()}["f1"] == "rejected"
        assert c.get("/api/profile/resumes/nope/annotations").status_code == 404


def _app(tmp_path: Path):
    from careeros.config import Settings
    from careeros.ui.app import create_app
    from careeros.ui.index import Index
    from careeros.ui.security import LOOPBACK

    root = make_temp_root(tmp_path / "repo")
    src = tmp_path / "resume.json"
    src.write_text(json.dumps(DOC), encoding="utf-8")
    rid = resumes.add_tailored(root, "text", category="x", source="job-1", files={"resume.json": src})["rid"]
    s = Settings.load(root)
    return root, rid, create_app(s, index=Index(s), broker=None, allowed_hosts=LOOPBACK | {"testserver"},
                                 static_dir=root / "no-static")


def test_reply_with_apply_queues_an_ai_redraft_run(tmp_path: Path):  # "Apply comment" (DEC-016)
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    root, rid, app = _app(tmp_path)
    started: list = []

    class RC:
        def __init__(self, settings):
            pass

        def start_step(self, kind, **kw):
            started.append((kind, kw))
            return {"run_id": "run-1"}

    app.state.run_control = RC
    W = {"X-CareerOS": "1"}
    url = f"/api/profile/resumes/{rid}/annotations"
    with TestClient(app) as c:
        aid = c.post(url, json={"kind": "comment", "target_id": "experience-1.b1", "text": "vague"}, headers=W).json()["id"]
        r = c.post(f"{url}/{aid}/replies", json={"text": "keep it short"}, headers=W)
        assert r.status_code == 200 and r.json()["run_id"] is None and started == []
        r = c.post(f"{url}/{aid}/replies", json={"text": "apply it", "apply": True}, headers=W)
        assert r.status_code == 200 and r.json()["run_id"] == "run-1"
        assert [x["author"] for x in r.json()["replies"]] == ["user", "user"]
        assert started == [("resume_edit", {"resume": rid, "item": aid})]
        assert c.post(f"{url}/zz/replies", json={"text": "x", "apply": True}, headers=W).status_code == 404
        assert len(started) == 1

        def busy(self, kind, **kw):
            raise RuntimeError("runner busy")
        RC.start_step = busy
        r = c.post(f"{url}/{aid}/replies", json={"text": "try again", "apply": True}, headers=W)
        assert r.status_code == 409 and "reply saved" in r.json()["detail"]
        assert ann.list_items(root, rid)[0]["replies"][-1]["text"] == "try again"  # the reply is kept

        def bad(self, kind, **kw):
            raise ValueError("bad item")
        RC.start_step = bad
        assert c.post(f"{url}/{aid}/replies", json={"text": "again", "apply": True}, headers=W).status_code == 422
        assert ann.list_items(root, rid)[0]["replies"][-1]["text"] == "again"


def test_cli_writes_annotations_as_ai(tmp_path: Path, capsys):  # review-resume / edit-resume path
    from careeros import cli

    root = make_temp_root(tmp_path / "repo")
    src = tmp_path / "resume.json"
    src.write_text(json.dumps(DOC), encoding="utf-8")
    rid = resumes.add_tailored(root, "text", category="x", source="job-1", files={"resume.json": src})["rid"]
    r = ["--root", str(root), "resume"]
    assert cli.main([*r, "annotate", rid, "suggestion", "--target", "experience-1.b1", "--proposed", "Built it",
                     "--text", "shorter"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert (s["author"], s["kind"], s["proposed"], s["base"]) == ("ai", "suggestion", "Built it", "Built the thing")
    assert cli.main([*r, "annotate-reply", rid, s["id"], "kept the verb"]) == 0
    assert json.loads(capsys.readouterr().out)["replies"][0]["author"] == "ai"
    assert cli.main([*r, "annotations", rid]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [i["id"] for i in out["items"]] == [s["id"]] and out["resume"]["experience"][0]["id"] == "experience-1"
    assert cli.main([*r, "annotate", rid, "suggestion", "--target", "experience-1.b1"]) == 1  # no proposed text
    assert cli.main([*r, "annotate", rid, "comment", "--target", "nope", "--text", "x"]) == 1
    assert cli.main([*r, "annotate", rid, "comment", "--target", "experience-1.b1", "--text", "x",
                     "--proposed", "y"]) == 1  # a comment proposes nothing
    assert "error:" in capsys.readouterr().err


def test_e2e_002_05_accepts_and_edit_stay_one_draft(tmp_path: Path):
    """E2E-002-05 (backend part): 2 accepts + 1 edit are draft changes, no new version; reverting 1 accept puts
    its target back and leaves the other changes. `Done` -> exactly one version needs TASK-031 publish."""
    root = make_temp_root(tmp_path / "repo")
    src = tmp_path / "resume.json"
    doc = {"schema_version": 1, "summary": "Engineer", "experience": [{"id": "experience-1", "bullets": [
        {"id": "b1", "source": "s1", "text": "Built the thing"},
        {"id": "b2", "source": "s2", "text": "Ran the other thing"}]}]}
    src.write_text(json.dumps(doc), encoding="utf-8")
    rid = resumes.add_tailored(root, "text", category="x", source="job-1", files={"resume.json": src})["rid"]
    a1 = ann.create(root, rid, kind="suggestion", target_id="b1", proposed="Built thing", author="ai")["id"]
    a2 = ann.create(root, rid, kind="suggestion", target_id="b2", proposed="Ran thing", author="ai")["id"]
    ann.accept(root, rid, a1)
    d = ann.accept(root, rid, a2)
    d["resume"]["summary"] = "Backend engineer"
    resumes.put_draft(root, rid, d["resume"], rev=d["rev"], author="user")
    log = resumes.changes(root, rid)
    assert [c["author"] for c in log] == ["ai", "ai", "user"]
    assert len(resumes.get(root, rid)["versions"]) == 1
    out = resumes.revert_change(root, rid, log[0]["id"])
    bullets = out["resume"]["experience"][0]["bullets"]
    assert [b["text"] for b in bullets] == ["Built the thing", "Ran thing"]
    assert out["resume"]["summary"] == "Backend engineer"
    assert len(resumes.get(root, rid)["versions"]) == 1
