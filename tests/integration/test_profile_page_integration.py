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
    busy: list[dict] = []  # a holder here makes the next start raise Busy

    def start_step(self, k):
        from careeros.ui.services.runs import Busy

        if busy:
            raise Busy(busy[0])
        started.append(k)
        return {"run_id": f"r{len(started)}"}
    app.state.run_control = lambda settings: type("RC", (), {"start_step": start_step})()
    app.state.busy = busy
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
    p = root / "profile" / "standard_answers.yaml"
    p.write_text(p.read_text() + '\ncompany_answers:\n  Acme:\n    - key: why_us\n      answer: "Rockets"\n')
    r = c.put("/api/profile/answers/why_us", json={"answer": "Space", "company": " acme "}, headers=W)
    assert r.status_code == 200 and r.json()["answer"] == "Space"  # NIT7: stray whitespace is not a 500


def test_lesson_delete(client):
    c, _, _ = client
    lid = c.post("/api/learning/lessons", json={"text": "Lever asks twice"}, headers=W).json()["id"]
    assert c.delete(f"/api/learning/lessons/{lid}", headers=W).status_code == 204
    assert c.get("/api/learning/lessons", headers=W).json()["lessons"] == []
    assert c.delete(f"/api/learning/lessons/{lid}", headers=W).status_code == 404


def test_writing_samples_upload_runs_learn_voice(client):
    c, root, started = client
    for name in ("a.md", "b.txt"):  # E2E-005-01: one upload action of 2 files -> learn-voice once
        r = c.put("/api/profile/samples", params={"filename": name, "learn": False}, content=b"I wrote this.",
                  headers=W)
        assert r.status_code == 201 and r.json()["learn_run"] is None, r.text
    assert started == []
    assert c.post("/api/profile/samples/learn", headers=W).json()["learn_run"] == "r1"
    assert started == ["learn_voice"]
    assert c.put("/api/profile/samples", params={"filename": "a.md"}, content=b"x", headers=W).json()["learn_run"] == "r2"
    started.pop()
    c.delete("/api/profile/samples/a-2.md", headers=W)
    started.pop()
    got = c.get("/api/profile/samples", headers=W).json()
    assert [x["name"] for x in got["samples"]] == ["a.md", "b.txt"]
    assert c.put("/api/profile/samples", params={"filename": "x.doc"}, content=b"x", headers=W).status_code == 415
    big = b"x" * (5 * 1024 * 1024 + 1)
    assert c.put("/api/profile/samples", params={"filename": "c.md"}, content=big, headers=W).status_code == 413
    c.app.state.busy.append({"owner": "run:x", "note": "learn_voice (manual)"})  # MUST1: already learning = info
    r = c.post("/api/profile/samples/learn", headers=W).json()
    assert r["learn_error"] is None and "already running" in r["learn_info"]
    c.app.state.busy[0] = {"owner": "run:y", "note": "prepare (manual)"}
    assert "not started" in c.post("/api/profile/samples/learn", headers=W).json()["learn_error"]
    c.app.state.busy.clear()
    c.delete("/api/profile/samples/a.md", headers=W)
    r = c.delete("/api/profile/samples/b.txt", headers=W).json()
    assert r["samples"] == [] and r["learn_run"] is None and started == ["learn_voice"] * 2
    assert c.get("/api/profile/samples", headers=W).json()["learned"] == ""
    assert c.delete("/api/profile/samples/b.txt", headers=W).status_code == 404


def test_writing_samples_upload_docx_as_text_and_pdf(client):
    """TASK-021 (REQ-101): a .docx upload is stored as its plain text, a .pdf as-is; both trigger learn-voice."""
    c, root, started = client
    docx = (Path(__file__).resolve().parents[1] / "fixtures" / "voice_sample.docx").read_bytes()
    r = c.put("/api/profile/samples", params={"filename": "letter.docx", "learn": False}, content=docx, headers=W)
    assert r.status_code == 201, r.text
    r = c.put("/api/profile/samples", params={"filename": "essay.pdf"}, content=b"%PDF-1.4 x", headers=W)
    assert r.status_code == 201 and started == ["learn_voice"], r.text
    assert [x["name"] for x in r.json()["samples"]] == ["essay.pdf", "letter.txt"]
    assert "small tools" in (root / "profile" / "voice" / "samples" / "letter.txt").read_text(encoding="utf-8")
    assert c.put("/api/profile/samples", params={"filename": "bad.docx"}, content=b"x", headers=W).status_code == 422
