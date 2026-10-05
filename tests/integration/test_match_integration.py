"""ACCEPT-111 / REQ-115: `careeros resume match <job>` (subprocess) and GET /api/jobs/{id}/matches on a temp root."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import PY, make_temp_root, subprocess_env

from careeros import resumes

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.4\nnot really a pdf\n"
JOB = "acme-backend-1"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "home").mkdir()
    r = make_temp_root(tmp_path / "repo")
    jd = r / "data" / "jobs" / JOB
    jd.mkdir(parents=True)
    (jd / "posting.json").write_text(json.dumps({"job_id": JOB, "company": "Acme", "title": "Backend Engineer"}))
    (jd / "score.json").write_text(json.dumps({"required_skills": ["Python", "Kubernetes"],
                                               "nice_to_have_skills": ["Rust"]}))
    for name, text in (("Main", "Python backend engineer"), ("Infra", "Python k8s Rust backend engineer"),
                       ("Old", "Java")):
        rid = resumes.add(r, "cv.pdf", PDF, name=name)["rid"]
        resumes.add_text(r, rid, text, author="user", source="edit")
    with (r / "config" / "pipeline.yaml").open("a") as f:
        f.write("\nmatch:\n  synonyms:\n    kubernetes: [k8s]\n")
    return r


def test_resume_match_cli(root: Path):
    env = subprocess_env(root, root.parent / "home")
    run = lambda *a: subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), "resume", "match", *a],
                                    capture_output=True, text=True, env=env, timeout=120)
    r = run(JOB, "--json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert [x["name"] for x in out["resumes"]] == ["Infra", "Main", "Old"]
    assert out["resumes"][0]["score"] == 100 and out["best"] == out["resumes"][0]["rid"]
    assert out["resumes"][1]["missing"] == ["Kubernetes", "Rust"]
    assert out["threshold"] == 70
    assert json.loads(run(JOB, "--json", "--threshold", "90").stdout)["threshold"] == 90
    assert "Infra" in run(JOB).stdout
    assert run("nope").returncode == 1
    for bad in ("101", "-1"):  # same 0-100 range as the API
        assert run(JOB, "--threshold", bad).returncode == 2


def test_unscored_job_hint(root: Path):  # PR #130 MUST: no skills in score.json -> no score, a hint
    (root / "data" / "jobs" / JOB / "score.json").unlink()
    env = subprocess_env(root, root.parent / "home")
    r = subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), "resume", "match", JOB],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    assert f"careeros run score --job {JOB}" in r.stdout and "Infra" not in r.stdout


def test_matches_api(root: Path):
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
    with TestClient(app) as c:
        r = c.get(f"/api/jobs/{JOB}/matches")
        assert r.status_code == 200, r.text
        body = r.json()
        assert [x["score"] for x in body["resumes"]] == sorted((x["score"] for x in body["resumes"]), reverse=True)
        assert body["best"] == body["resumes"][0]["rid"] and body["threshold"] == 70
        assert c.get(f"/api/jobs/{JOB}/matches", params={"threshold": 50}).json()["threshold"] == 50
        assert c.get("/api/jobs/nope/matches").status_code == 404
        assert body["scored"] is True and body["hint"] is None
        (root / "data" / "jobs" / JOB / "score.json").write_text("{}")
        u = c.get(f"/api/jobs/{JOB}/matches").json()
        assert u["scored"] is False and u["best"] is None and f"run score --job {JOB}" in u["hint"]
