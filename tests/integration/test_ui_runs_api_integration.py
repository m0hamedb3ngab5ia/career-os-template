"""The Runs API end to end: FastAPI TestClient over a temp repo root with the fictional UI data. RunControl is
real except for the process edges (Popen, pid and command-line lookups, signals, launchctl), which the app's
`run_control` factory swaps for fakes, so nothing is spawned or signalled and launchd is never touched."""
from __future__ import annotations

import json
import signal
from datetime import datetime, timedelta, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import build_ui_data

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.runs import locks  # noqa: E402
from careeros.runs.store import RunStore  # noqa: E402
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
        self.killed: list[tuple[int, int]] = []
        self.launchctl_calls: list[list[str]] = []
        self.cmdline = "/venv/bin/python -m careeros.cli --root /r run prepare --json"

    def popen(self, cmd, **kw):
        self.spawned.append(cmd)
        return type("P", (), {"pid": 4242})()

    def launchctl(self, args):
        self.launchctl_calls.append(args)
        return (0, "", "") if args[0] in ("bootstrap", "bootout") else (1, "", "not loaded")

    def factory(self, settings, **kw):
        base = dict(popen=self.popen, python="/venv/bin/python", env={}, pid_alive=lambda pid: True,
                    cmdline=lambda pid: self.cmdline, kill=lambda pid, sig: self.killed.append((pid, sig)),
                    now=lambda: NOW, sleep=lambda s: None, launchctl=self.launchctl)
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


def running(data, kind="prepare", trigger="manual"):
    rs = RunStore(data["settings"])
    run = rs.new_run(kind, trigger, {"preset": "small", "max_jobs": 2, "max_minutes": 30},
                     NOW - timedelta(minutes=5), counters={"attempted": 0},
                     queue=[{"job_id": data["jobs"]["queued"], "rank": 1, "score": 60, "why": "posted 4d ago (+50)"}])
    locks.acquire(rs.runner_lock_path, owner=f"run:{run['id']}", ttl_seconds=3600, pid=999, note=kind,
                  pid_alive=lambda p: True)
    return run


# --- reading ---------------------------------------------------------------------------------------------------

def test_history_newest_first_with_kind_filter_and_cursor(client, data):
    h = client.get("/api/runs").json()
    assert [r["id"] for r in h["runs"]] == [data["runs"]["prepare"], data["runs"]["score"]]
    assert h["runs"][0]["stop_reason"] == "usage_limit" and h["next_cursor"] is None
    only = client.get("/api/runs", params={"kind": "score"}).json()
    assert [r["kind"] for r in only["runs"]] == ["score"]
    page = client.get("/api/runs", params={"limit": 1}).json()
    assert len(page["runs"]) == 1 and page["next_cursor"] == data["runs"]["prepare"]
    rest = client.get("/api/runs", params={"limit": 1, "cursor": page["next_cursor"]}).json()
    assert [r["id"] for r in rest["runs"]] == [data["runs"]["score"]]
    assert client.get("/api/runs", params={"limit": 0}).status_code == 422


def test_detail_has_attempts_with_names_and_the_log(client, data):
    d = client.get(f"/api/runs/{data['runs']['prepare']}").json()
    assert d["attempts"][0]["company"] == "Initech" and d["attempts"][0]["outcome"] == "usage_limit"
    assert "log" in d
    assert client.get("/api/runs/20200101-000000-score-ffff").status_code == 404
    assert client.get("/api/runs/bad.id").status_code == 422


def test_bad_run_ids_are_refused_with_422(client):
    assert client.get("/api/runs", params={"cursor": "bad.id"}).status_code == 422
    assert client.post("/api/runs/cancel", json={"run_id": "bad.id"}, headers=W).status_code == 422
    assert client.get("/api/runs/bad.id/stream").status_code == 422


def test_current_is_null_when_idle_then_shows_the_batch(client, data):
    assert client.get("/api/runs/current").json() is None
    run = running(data)
    cur = client.get("/api/runs/current").json()
    assert cur["id"] == run["id"] and cur["state"] == "running" and cur["scheduled"] is False
    assert cur["jobs"][0]["company"] == "Initech" and cur["jobs"][0]["state"] == "queued"
    assert cur["used"]["max_jobs"] == 2


def test_queue_ranks_with_reason_chips(client, data):
    q = client.get("/api/runs/queue/score").json()
    assert [i["company"] for i in q["items"]] == ["Acme Robotics"]
    assert q["items"][0]["reasons"][0]["code"] == "fresh"
    assert client.get("/api/runs/queue/apply").status_code == 422


def test_schedule_status(client, fakes):
    s = client.get("/api/schedule").json()
    assert s["installed"] is False and s["loaded"] is False
    assert [j["kind"] for j in s["jobs"]] == ["scout", "inbox_sync", "score", "prepare", "prune"]
    assert s["inbox_ready"] is False


# --- starting --------------------------------------------------------------------------------------------------

def test_start_a_batch_spawns_the_cli(client, fakes):
    r = client.post("/api/runs", json={"kind": "score", "preset": "small"}, headers=W)
    assert r.status_code == 200 and r.json()["pid"] == 4242
    assert fakes.spawned[0][-5:] == ["run", "score", "--preset", "small", "--json"]


def test_custom_budget_and_dry_run(client, fakes):
    dry = client.post("/api/runs", json={"kind": "score", "max_jobs": 3, "max_minutes": 20, "dry_run": True},
                      headers=W).json()
    assert dry["dry_run"] is True and fakes.spawned == []
    assert dry["budget"]["max_jobs"] == 3 and dry["selected"][0]["reasons"]
    client.post("/api/runs", json={"kind": "prepare", "preset": "custom", "max_jobs": 3, "max_minutes": 20},
                headers=W)
    cmd = fakes.spawned[0]
    assert cmd[cmd.index("--max-jobs") + 1] == "3" and cmd[cmd.index("--max-minutes") + 1] == "20"


def test_start_errors_map_to_plain_statuses(client, data):
    assert client.post("/api/runs", json={"kind": "apply"}, headers=W).status_code == 422
    assert client.post("/api/runs", json={"kind": "score", "preset": "huge"}, headers=W).status_code == 422
    assert client.post("/api/runs", json={"kind": "score"}).status_code == 403  # no X-CareerOS header
    running(data)
    busy = client.post("/api/runs", json={"kind": "score"}, headers=W)
    assert busy.status_code == 409 and "already running" in busy.json()["detail"]


def test_paused_refuses_starts_until_resumed(client, fakes):
    p = client.post("/api/runs/pause", json={"until": "+1h"}, headers=W)
    assert p.status_code == 200 and p.json()["until"]
    r = client.post("/api/runs", json={"kind": "score"}, headers=W)
    assert r.status_code == 409 and "paused" in r.json()["detail"].lower()
    assert client.get("/api/schedule").json()["paused"]["until"]
    assert client.post("/api/runs/resume", headers=W).json() == {"resumed": True}
    assert client.post("/api/runs", json={"kind": "score"}, headers=W).status_code == 200
    assert client.post("/api/runs/pause", json={"until": "yesterday"}, headers=W).status_code == 422
    assert client.post("/api/runs/pause", json={}, headers=W).json()["until"] is None


def test_steps_and_inbox_not_set_up(client, fakes):
    r = client.post("/api/runs/steps/scout", headers=W)
    assert r.status_code == 200 and "careeros.ui.services.step" in fakes.spawned[0]
    inbox = client.post("/api/runs/steps/inbox_sync", headers=W)
    assert inbox.status_code == 409 and "not set up" in inbox.json()["detail"]
    assert client.post("/api/runs/steps/apply", headers=W).status_code == 422


# --- cancel, catch-up, schedule --------------------------------------------------------------------------------

def test_cancel_signals_a_manual_batch_but_not_a_scheduled_one(client, data, fakes):
    assert client.post("/api/runs/cancel", json={}, headers=W).json()["status"] == "idle"
    run = running(data)
    r = client.post("/api/runs/cancel", json={"run_id": run["id"]}, headers=W).json()
    assert r["status"] == "cancelling" and fakes.killed == [(999, signal.SIGTERM)]
    assert client.post("/api/runs/cancel", json={}, headers=W).json()["status"] == "already_stopping"


def test_cancel_refuses_a_tick(client, data, fakes):
    running(data, trigger="schedule")
    fakes.cmdline = "/venv/bin/python -m careeros.cli --root /r tick"
    r = client.post("/api/runs/cancel", json={}, headers=W).json()
    assert r["status"] == "refused" and "Pause all" in r["detail"] and fakes.killed == []


def test_catch_up_start_and_dismiss(client, data, fakes):
    assert client.post("/api/runs/catch-up", json={}, headers=W).json()["pending"] is False
    rs = RunStore(data["settings"])
    (rs.dir / "catch_up.json").write_text(json.dumps({"created_at": NOW.isoformat(), "kinds": {
        "score": {"first_missed": NOW.isoformat(), "slots": 2}}}))
    assert client.get("/api/schedule").json()["catch_up"]["kinds"]["score"]["slots"] == 2
    started = client.post("/api/runs/catch-up", json={}, headers=W).json()
    assert started["pending"] is True and "catch-up" in fakes.spawned[0]
    gone = client.post("/api/runs/catch-up", json={"dismiss": True}, headers=W).json()
    assert gone["dismissed"] is True and client.get("/api/schedule").json()["catch_up"] is None


def test_catch_up_while_the_scheduler_ticks_is_a_plain_409(client, data):
    import os

    rs = RunStore(data["settings"])
    (rs.dir / "catch_up.json").write_text(json.dumps({"created_at": NOW.isoformat(), "kinds": {
        "score": {"first_missed": NOW.isoformat(), "slots": 1}}}))
    locks.acquire(rs.dir / "tick.lock", owner="tick", ttl_seconds=600, pid=os.getpid())
    r = client.post("/api/runs/catch-up", json={"dismiss": True}, headers=W)
    assert r.status_code == 409 and "scheduler is ticking" in r.json()["detail"]


def test_validation_errors_are_one_plain_sentence(client):
    r = client.post("/api/runs", json={"kind": "score", "preset": "custom", "max_jobs": 2.5}, headers=W)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str) and "max_jobs" in detail and "whole number" in detail
    assert client.get("/api/runs", params={"limit": 0}).json()["detail"].startswith("limit")


def test_schedule_install_and_uninstall_use_launchctl(client, fakes):
    r = client.post("/api/schedule/install", headers=W)
    assert r.status_code == 200 and r.json()["loaded"] is True
    assert any(a[0] == "bootstrap" for a in fakes.launchctl_calls)
    u = client.post("/api/schedule/uninstall", headers=W)
    assert u.status_code == 200 and u.json()["removed"] is True


def test_install_failure_is_a_plain_409(client, fakes):
    fakes.launchctl = lambda args: (5, "", "Bootstrap failed: 5: Input/output error")
    r = client.post("/api/schedule/install", headers=W)
    assert r.status_code == 409 and "launchctl" in r.json()["detail"]


# --- stream ----------------------------------------------------------------------------------------------------

def test_stream_replays_the_log_and_ends(client, data):
    rid = data["runs"]["score"]
    rs = RunStore(data["settings"])
    rs.log(rid, "start score")
    (rs.run_dir(rid) / "attempts" / "001.stream.jsonl").write_text(json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Scoring Initech"}]}}) + "\n")
    with client.stream("GET", f"/api/runs/{rid}/stream") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert "Scoring Initech" in body and "start score" in body
    assert "event: end" in body and '"state": "done"' in body
    assert client.get("/api/runs/20200101-000000-score-ffff/stream").status_code == 404


def test_stream_disconnect_during_a_quiet_run_stops_the_tail_promptly(data, fakes):
    """A client that goes away while the run is silent must not leave the tail thread polling until the run
    ends: cancelling the stream wakes the worker within about a second."""
    import asyncio
    import threading
    import time

    from careeros.ui.routers import runs as runs_router

    done = threading.Event()

    class Probe(RunControl):
        def tail(self, run_id, **kw):
            try:
                yield from super().tail(run_id, **kw)
            finally:
                done.set()

    def factory(settings, **kw):
        base = dict(popen=fakes.popen, pid_alive=lambda pid: True, now=lambda: NOW, launchctl=fakes.launchctl)
        return Probe(settings, **{**base, **kw})

    run = running(data)

    class Req:
        app = type("A", (), {"state": type("S", (), {"run_control": staticmethod(factory)})()})()

        async def is_disconnected(self):
            return False

    ctx = type("C", (), {"settings": data["settings"]})()

    result: dict[str, float] = {}

    async def scenario() -> None:
        import anyio

        resp = await runs_router.stream(run["id"], Req(), ctx)
        it = resp.body_iterator
        await it.__anext__()  # the retry frame
        with anyio.move_on_after(0.3):  # the way Starlette cancels a stream whose client went away
            await it.__anext__()  # blocks: the run is quiet
        result["cancelled_after"] = time.monotonic()
        await it.aclose()

    def go() -> None:
        import anyio

        anyio.run(scenario)

    t = threading.Thread(target=go, daemon=True)
    t0 = time.monotonic()
    t.start()
    assert done.wait(3), "the tail thread kept polling after the client went away"
    t.join(3)
    assert "cancelled_after" in result and result["cancelled_after"] - t0 < 1.5
