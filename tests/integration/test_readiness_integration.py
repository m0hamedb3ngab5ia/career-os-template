"""ACCEPT-103 / E2E-006-01/02: readiness gate end to end (CLI subprocess exit 7, API 409, GET /api/readiness)."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.config import Settings  # noqa: E402
from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

from test_runs_integration import add_jobs, cli, env_for, fake_bin, home, root  # noqa: E402,F401

pytestmark = [pytest.mark.integration, pytest.mark.readiness]


def test_run_apply_and_apply_plan_exit_7_while_master_resume_missing(root, home, fake_bin, tmp_path):
    ids = add_jobs(root, 1)
    shutil.rmtree(root / "profile" / "resumes")
    env = env_for(root, home, fake_bin, FAKE_CLAUDE_ARGV=str(tmp_path / "argv.jsonl"))
    for args in (("run", "apply", "--job", ids[0]), ("apply", "plan", ids[0]), ("apply", "fill", ids[0])):
        r = cli(root, env, *args)
        assert r.returncode == 7, (args, r.stderr)
        assert "not ready: master_resume" in r.stderr
    assert not (tmp_path / "argv.jsonl").exists()  # nothing ran
    assert not (root / "data" / "jobs" / ids[0] / "fill_plan.json").exists()
    r = cli(root, env, "run", "score", "--job", ids[0])  # score/prepare are never blocked
    assert r.returncode == 0, r.stderr
    r = cli(root, env, "doctor")
    assert "readiness" in r.stdout and "Master résumé set: apply blocked" in r.stdout


@pytest.fixture
def client(root, tmp_path):
    now = datetime(2026, 10, 4, tzinfo=timezone.utc)
    ix = Index(Settings.load(root))
    ix.rebuild()
    app = create_app(Settings.load(root), index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: now)
    with TestClient(app) as c:
        yield c
    ix.close()


def test_api_readiness_and_409_on_apply(root, client, monkeypatch):
    monkeypatch.setattr("careeros.readiness.shutil.which", lambda n: f"/fake/{n}")
    monkeypatch.delenv("CLAUDECODE", raising=False)
    body = client.get("/api/readiness").json()
    assert body["ready"] is True and {"id", "label", "must", "done", "fix_link"} == set(body["items"][0])
    jid = add_jobs(root, 1)[0]
    shutil.rmtree(root / "profile" / "resumes")
    body = client.get("/api/readiness").json()
    assert body["ready"] is False
    assert [i["id"] for i in body["items"] if i["must"] and not i["done"]] == ["master_resume"]
    r = client.post(f"/api/jobs/{jid}/application/open", json={}, headers={"x-careeros": "1"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_ready"
    assert r.json()["detail"]["items"][0]["id"] == "master_resume"
