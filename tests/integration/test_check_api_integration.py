"""REQ-114/116, UC-010 (E2E-010-01/02) through the API: POST /api/jobs/check, GET .../check, tailor, decision.
A fake RunControl records the score/prepare runs; the fake tailor writes the job's résumé like prepare would."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_temp_root

from careeros import resumes
from careeros.runs.store import RunStore

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.4\nnot really a pdf\n"
JD = "Backend Engineer\nWe need Python, Kubernetes, Rust, Go and SQL."


class FakeRC:
    calls: list[tuple[str, str]] = []
    on_prepare = None

    def __init__(self, settings):
        self.settings = settings

    def start(self, kind, *, job_id=None, force=False, **_):
        FakeRC.calls.append((kind, job_id))
        if kind == "prepare" and FakeRC.on_prepare:
            FakeRC.on_prepare(self.settings.paths["jobs_dir"] / job_id)
        return {"run_id": f"{kind}-1"}


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
    app.state.run_control = FakeRC
    FakeRC.calls, FakeRC.on_prepare = [], None
    with TestClient(app, headers={"X-CareerOS": "1"}) as c:
        yield c, s


def _resume(s, name: str, text: str) -> None:
    rid = resumes.add(s.root, "cv.pdf", PDF, name=name)["rid"]
    resumes.add_text(s.root, rid, text, author="user", source="edit")


def _check(c, s) -> str:
    r = c.post("/api/jobs/check", content=JD.encode(), headers={"content-type": "text/plain"},
               params={"company": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["score_run"] == "score-1" and body["flagged"] is False
    jid = body["job_id"]
    assert FakeRC.calls == [("score", jid)]
    assert c.get(f"/api/jobs/{jid}/check").json()["stage"] == "scoring"
    (s.paths["jobs_dir"] / jid / "score.json").write_text(
        json.dumps({"decision": "prepare", "required_skills": ["Python", "Kubernetes", "Rust", "Go", "SQL"]}))
    return jid


def test_e2e_010_01_best_marked_prepare_once(client):
    c, s = client
    _resume(s, "Infra", "Backend engineer: Python Kubernetes Rust Go SQL")
    _resume(s, "Old", "Python")
    jid = _check(c, s)
    st = c.get(f"/api/jobs/{jid}/check").json()
    assert st["stage"] == "ready" and st["resumes"][0]["name"] == "Infra" and st["best"] == st["resumes"][0]["rid"]
    m = c.get(f"/api/jobs/{jid}/matches").json()["resumes"]  # "Why this score" data
    assert m[0]["groups"]["required"] == {"hit": ["Python", "Kubernetes", "Rust", "Go", "SQL"], "missing": []}
    assert m[1]["groups"]["required"]["hit"] == ["Python"] and "Go" in m[1]["groups"]["required"]["missing"]
    assert c.post(f"/api/jobs/{jid}/check/tailor").json() == {"run_id": "prepare-1", "kind": "prepare"}
    assert c.post(f"/api/jobs/{jid}/check/tailor").status_code == 409  # one prepare run per check
    assert [k for k, _ in FakeRC.calls] == ["score", "prepare"]


def test_e2e_010_02_below_threshold_keep(client):
    c, s = client
    _resume(s, "A", "Backend engineer Python")

    def tailor(jd: Path) -> None:
        (jd / "resume.txt").write_text("Backend engineer Python Kubernetes Rust")
        (jd / "resume_choice.json").write_text(json.dumps({"action": "tailor"}))
        (jd / "qa.json").write_text(json.dumps({"pass": True}))
        RunStore(s).save_run({"id": "prepare-1", "kind": "prepare", "status": "done"})

    FakeRC.on_prepare = tailor
    jid = _check(c, s)
    assert c.get(f"/api/jobs/{jid}/check").json()["stage"] == "offer_tailor"
    assert c.post(f"/api/jobs/{jid}/check/tailor").json() == {"run_id": "prepare-1", "kind": "prepare"}
    st = c.get(f"/api/jobs/{jid}/check").json()
    a = st["attempt"]["score"]
    assert st["stage"] == "confirm" and a < 70 and f"{a}/70" in st["notice"]
    assert c.post(f"/api/jobs/{jid}/check/tailor").status_code == 409  # one tailor run per check
    st = c.post(f"/api/jobs/{jid}/check/decision", json={"keep": True}).json()
    assert st["stage"] == "below_threshold" and st["decision"] == "keep"
    assert [r["type"] for r in resumes.list_resumes(s.root)].count("tailored") == 1  # saved once, on keep
    assert c.post(f"/api/jobs/{jid}/check/decision", json={"keep": False}).status_code == 409


def test_bad_input(client):
    c, _ = client
    assert c.post("/api/jobs/check", content=b"MZ", params={"filename": "jd.exe"}).status_code == 415
    assert c.post("/api/jobs/check", content=b"nope", params={"filename": "jd.pdf"}).status_code == 415
    assert c.post("/api/jobs/check", content=b"   ").status_code == 422
    assert c.post("/api/jobs/check", content=b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert c.post("/api/jobs/check", content=JD.encode(), params={"url": "javascript:x"}).status_code == 422
    assert c.get("/api/jobs/nope/check").status_code == 404
    assert c.get("/api/jobs/..%2Fx/check").status_code == 404
    r = c.post("/api/jobs/check", content=b"Data role\nPython and SQL.", params={"filename": "../../jd.txt"})
    assert r.status_code == 201, r.text
