"""GET/POST /api/jobs/{id}/pipeline over the fictional UI data: the next action per job state, approve_continue
flips needs_review -> queued and starts the apply run, 409 while a run is active or for Tier A / done jobs. The
`run_control` factory swaps the process edges for fakes (a fake popen records the argv, nothing runs)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import build_ui_data

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.runs import locks  # noqa: E402
from careeros.runs.store import RunStore  # noqa: E402
from careeros.store import Store  # noqa: E402
from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402
from careeros.ui.services.runs import RunControl  # noqa: E402

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
W = {"X-CareerOS": "1"}


class Fakes:
    def __init__(self):
        self.spawned: list[list[str]] = []

    def popen(self, cmd, **kw):
        self.spawned.append(cmd)
        return type("P", (), {"pid": 4242})()

    def factory(self, settings, **kw):
        base = dict(popen=self.popen, python="/venv/bin/python", env={}, pid_alive=lambda pid: True,
                    cmdline=lambda pid: "/venv/bin/python -m careeros.cli run apply --json", kill=lambda p, s: None,
                    now=lambda: NOW, sleep=lambda s: None)
        return RunControl(settings, **{**base, **kw})


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return build_ui_data(make_temp_root(tmp_path / "repo"), NOW)


@pytest.fixture
def fakes():
    return Fakes()


@pytest.fixture
def client(data, fakes, tmp_path):
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    app.state.run_control = fakes.factory
    with TestClient(app) as c:
        yield c
    ix.close()


def prepared(data, key: str, tier: str = "B") -> str:
    """Give the fixture job a prepare.json with qa_pass and a scored decision (the fixture writes neither)."""
    jid = data["jobs"][key]
    store = Store(data["settings"])
    score = json.loads((store.job_dir(jid) / "score.json").read_text())
    store._write(jid, "score.json", {**score, "tier": tier, "decision": "prepare"})  # Score has no decision field
    store._write(jid, "prepare.json", {"job_id": jid, "qa_pass": True, "action_items": ["cover_letter_facts: add 2 facts"]})
    return jid


def test_get_pipeline_per_job_state(client, data):
    found = client.get(f"/api/jobs/{data['jobs']['found']}/pipeline").json()
    assert (found["stage"], found["next_action"], found["next_kind"]) == ("score", "start", "score")
    review = prepared(data, "review", tier="A")
    got = client.get(f"/api/jobs/{review}/pipeline").json()
    assert got["stage"] == "review" and got["next_action"] == "approve_continue" and got["next_kind"] == "apply"
    assert got["blocked_reason"] is None and got["next_label"] == "Prepare & stage for review"
    assert got["note"] == "Tier A: the run fills and stages the form; you review and submit."
    assert got["auto_submit"] is False  # examples/config: runs.auto_submit off -> the UI may chain prepare into apply
    assert got["review_reasons"] == ["cover_letter_facts: add 2 facts", "Apply session needs_review: Tier A: you submit",
                                     "Open action item: Review and submit"]
    # Tier B with the form staged in the browser (auto_submit off): nothing runnable, the human submits.
    Store(data["settings"])._write(review, "score.json", {**json.loads((Store(data["settings"]).job_dir(review) / "score.json").read_text()), "tier": "B"})
    Store(data["settings"])._write(review, "apply_session.json", {"outcome": "staged", "status": "needs_review",
                                                                  "reason": "assisted: review & submit"})
    staged = client.get(f"/api/jobs/{review}/pipeline").json()
    assert staged["stage"] == "review" and staged["next_action"] is None
    assert staged["blocked_reason"].startswith("Application staged in the browser")
    assert "Apply session staged: assisted: review & submit" in staged["review_reasons"]
    r = client.post(f"/api/jobs/{review}/pipeline", json={"action": "approve_continue"}, headers=W)
    assert r.status_code == 409 and "staged in the browser" in r.json()["detail"]
    applied = client.get(f"/api/jobs/{data['jobs']['applied']}/pipeline").json()
    assert applied["next_action"] is None and applied["blocked_reason"] is None and applied["active_run_id"] is None
    assert client.get("/api/jobs/nope/pipeline").status_code == 404


def test_auto_submit_on_in_config_is_reported_and_drops_the_stage_label(client, data):
    jid = prepared(data, "queued", tier="B")
    off = client.get(f"/api/jobs/{jid}/pipeline").json()
    assert off["auto_submit"] is False and off["next_label"] == "Prepare & stage for review"
    s = data["settings"]
    s.pipeline = {**s.pipeline, "runs": {**(s.pipeline.get("runs") or {}),
                                         "auto_submit": {"enabled": True, "allow": ["tier_b"], "manual": ["tier_a"]}}}
    on = client.get(f"/api/jobs/{jid}/pipeline").json()
    assert on["auto_submit"] is True and on["next_label"] == "Continue pipeline" and on["note"] is None


def test_approve_continue_flips_status_logs_and_starts_the_apply_run(client, data, fakes):
    jid = prepared(data, "review", tier="B")
    assert client.get(f"/api/jobs/{jid}/pipeline").json()["next_action"] == "approve_continue"
    r = client.post(f"/api/jobs/{jid}/pipeline", json={"action": "approve_continue"}, headers=W)
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "apply" and r.json()["run_id"].endswith
    cmd = fakes.spawned[0]
    assert cmd[3:5] == ["run", "apply"] and cmd[cmd.index("--job") + 1] == jid
    assert cmd[cmd.index("--run-id") + 1] == r.json()["run_id"]
    store = Store(data["settings"])
    assert store.get_status(jid) == "queued"
    assert "Approved for apply from the UI" in store.read_log(jid)
    # the status change is in the job's history and Job detail sees it
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "queued"


def test_start_and_continue_run_the_next_stage(client, data, fakes):
    r = client.post(f"/api/jobs/{data['jobs']['found']}/pipeline", json={"action": "start"}, headers=W)
    assert r.status_code == 200 and r.json()["kind"] == "score"
    jid = prepared(data, "queued")
    r = client.post(f"/api/jobs/{jid}/pipeline", json={"action": "continue"}, headers=W)
    assert r.status_code == 200 and r.json()["kind"] == "apply"
    assert [c[4] for c in fakes.spawned] == ["score", "apply"]


def test_tier_a_apply_is_started_assisted_and_other_misfits_are_409(client, data, fakes):
    """Tier A is no longer refused: continue starts `run apply --job` (the runner passes CAREEROS_AUTO_SUBMIT=0
    and the skill stages the form); a status that does not fit the action is still 409."""
    jid = prepared(data, "queued", tier="A")
    got = client.get(f"/api/jobs/{jid}/pipeline").json()
    assert got["next_action"] == "continue" and got["next_label"] == "Prepare & stage for review"
    r = client.post(f"/api/jobs/{jid}/pipeline", json={"action": "continue"}, headers=W)
    assert r.status_code == 200 and r.json()["kind"] == "apply"
    assert len(fakes.spawned) == 1 and fakes.spawned[0][4] == "apply"
    r = client.post(f"/api/jobs/{data['jobs']['applied']}/pipeline", json={"action": "start"}, headers=W)
    assert r.status_code == 409 and "status applied" in r.json()["detail"]
    r = client.post(f"/api/jobs/{data['jobs']['found']}/pipeline", json={"action": "approve_continue"}, headers=W)
    assert r.status_code == 409 and Store(data["settings"]).get_status(data["jobs"]["found"]) == "found"
    assert len(fakes.spawned) == 1


def test_409_while_a_run_is_active_and_the_active_run_is_reported(client, data, fakes):
    jid = prepared(data, "queued")
    rs = RunStore(data["settings"])
    run = rs.new_run("apply", "manual", {"max_jobs": 1, "max_minutes": 30}, NOW - timedelta(minutes=1),
                     counters={"attempted": 0}, queue=[{"job_id": jid, "rank": 1, "score": 1, "why": ""}])
    locks.acquire(rs.runner_lock_path, owner=f"run:{run['id']}", ttl_seconds=3600, pid=999, note="apply",
                  pid_alive=lambda p: True)
    got = client.get(f"/api/jobs/{jid}/pipeline").json()  # picked by the batch, not in flight: queued, no Cancel
    assert got["active_run_id"] is None and got["queued_in_run"] == run["id"] and got["next_action"] is None
    assert got["blocked_reason"] == f"Queued in batch run {run['id']}"
    locks.acquire(rs.job_lock_path(jid), owner=f"run:{run['id']}", ttl_seconds=600, pid=999, note=f"apply {jid}",
                  pid_alive=lambda p: True)
    got = client.get(f"/api/jobs/{jid}/pipeline").json()
    assert got["active_run_id"] == run["id"] and got["queued_in_run"] is None and got["next_action"] is None
    other = client.get(f"/api/jobs/{data['jobs']['found']}/pipeline").json()
    assert other["active_run_id"] is None and other["queued_in_run"] is None
    r = client.post(f"/api/jobs/{jid}/pipeline", json={"action": "continue"}, headers=W)
    assert r.status_code == 409 and "already running" in r.json()["detail"] and fakes.spawned == []
