"""`careeros learn ...` and `careeros action done --answer` via subprocess on a temp root; the learning HTTP API."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import PY, make_temp_root, subprocess_env

pytestmark = pytest.mark.integration


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=subprocess_env(root, root.parent / "home"), timeout=120)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = make_temp_root(tmp_path / "repo")
    (tmp_path / "home").mkdir()
    d = r / "data" / "jobs" / "acme-1"
    d.mkdir(parents=True)
    (d / "posting.json").write_text(json.dumps({"id": "acme-1", "company": "Acme", "title": "Engineer",
                                                "url": "https://example.com/j", "source": "greenhouse", "ats": "greenhouse"}))
    return r


def test_learn_cli_roundtrip(root: Path):
    r = _cli(root, "learn", "answer", "Willing to travel 25%?", "Yes", "--job", "acme-1", "--match", "travel.*25")
    assert r.returncode == 0, r.stderr
    doc = yaml.safe_load((root / "profile" / "standard_answers.yaml").read_text())
    assert doc["answers"][-1]["match"] == ["travel.*25"] and doc["answers"][-1]["answer"] == "Yes"
    r = _cli(root, "learn", "answer", "Worked at Acme before?", "No", "--company", "Acme")
    assert r.returncode == 0, r.stderr
    assert yaml.safe_load((root / "profile" / "standard_answers.yaml").read_text())["company_answers"]["Acme"]
    r = _cli(root, "learn", "lesson", "Greenhouse hides the EEO section behind a toggle", "--ats", "greenhouse", "--job", "acme-1", "--tag", "eeo")
    assert r.returncode == 0, r.stderr
    r = _cli(root, "learn", "list", "--ats", "greenhouse", "--json")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert any("toggle" in x["text"] for x in got) and all(x["ats"] in (None, "greenhouse") for x in got)
    assert _cli(root, "learn", "answer", "Q", "   ").returncode == 1
    assert "PASS  apply_lessons" in _cli(root, "doctor").stdout


def test_action_done_with_answer_learns_and_closes(root: Path):
    r = _cli(root, "action", "add", "legal question not in standard answers: Are you bound by a non-compete?",
             "--type", "question", "--job", "acme-1")
    assert r.returncode == 0, r.stderr
    aid = r.stdout.split()[2]
    r = _cli(root, "action", "done", aid, "--answer", "No")
    assert r.returncode == 0, r.stderr
    doc = yaml.safe_load((root / "profile" / "standard_answers.yaml").read_text())
    last = doc["answers"][-1]
    assert last["answer"] == "No" and "acme-1" in last["note"]
    assert re.search(last["match"][0], "Are you bound by a non-compete?", re.I)
    assert "no open action items" in _cli(root, "action", "list").stdout
    rec = json.loads((root / "data" / "jobs" / "acme-1" / "answers.json").read_text())
    assert rec[0]["question"] == "Are you bound by a non-compete?" and rec[0]["source"] == "learned"
    r = _cli(root, "action", "add", "Review", "--type", "review")
    assert _cli(root, "action", "done", r.stdout.split()[2], "--answer", "x").returncode == 1


def test_learning_http_api(root: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from careeros.config import Settings
    from careeros.tracker import Tracker
    from careeros.ui.app import create_app
    from careeros.ui.index import Index
    from careeros.ui.security import LOOPBACK

    s = Settings.load(root)
    aid = Tracker(settings=s).add_action_item("essay: Why Acme? (limit 300)", type="question", job_id="acme-1", company="Acme")
    ix = Index(s)
    ix.rebuild()
    app = create_app(s, index=ix, broker=None, allowed_hosts=LOOPBACK | {"testserver"}, static_dir=root / "no-static")
    W = {"X-CareerOS": "1"}
    with TestClient(app) as c:
        r = c.post(f"/api/actions/{aid}/answer", json={"answer": "Because of the platform team", "scope": "company"}, headers=W)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] == [aid] and r.json()["learned"]["scope"] == "company"
        assert c.get("/api/actions", params={"tab": "open"}, headers=W).json()["counts"]["open"] == 0
        assert c.post(f"/api/actions/{aid}/answer", json={"answer": ""}, headers=W).status_code == 400
        assert c.post("/api/actions/nope/answer", json={"answer": "x"}, headers=W).status_code == 404
        r = c.post("/api/learning/lessons", json={"text": "Greenhouse EEO is a toggle", "ats": "greenhouse", "job_id": "acme-1"}, headers=W)
        assert r.status_code == 200 and r.json()["ats"] == "greenhouse"
        assert c.post("/api/learning/lessons", json={"text": " "}, headers=W).status_code == 400
        got = c.get("/api/learning/lessons", params={"ats": "greenhouse", "company": "Acme"}).json()["lessons"]
        assert any(x["text"] == "Greenhouse EEO is a toggle" for x in got)
        assert not any(x["ats"] == "greenhouse" for x in c.get("/api/learning/lessons", params={"ats": "lever"}).json()["lessons"])
    ix.close()
    assert yaml.safe_load((root / "profile" / "standard_answers.yaml").read_text())["company_answers"]["Acme"][0]["answer"] == "Because of the platform team"
