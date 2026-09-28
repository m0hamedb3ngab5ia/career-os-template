"""The typed Operations API surface (runs, schedule, storage, advise, settings, actions, inbox, contacts): each GET
returns exactly the JSON the service functions build, pinned by a snapshot on the fictional UI data, so a TypedDict
response shape that drops a key fails here (docs/UI.md "API types (generated)")."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import make_temp_root
from fixtures.ui_data import add_outreach_data, add_scam_case, build_ui_data

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.runs import locks  # noqa: E402
from careeros.runs.store import RunStore  # noqa: E402
from careeros.runs.tick import _save_catch_up  # noqa: E402
from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
SNAPSHOTS = REPO / "tests" / "fixtures" / "ui_snapshots"
NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
# values that change per build (generated ids, wall-clock stamps, temp paths): blanked, their keys kept
VOLATILE = {"id", "run_id", "created", "indexed_at", "pid", "log", "path", "root", "dir", "next", "version", "done_date"}
SIZES = {"storage"}  # byte counts and free disk space vary per machine


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    import time
    time.tzset()
    data = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    add_outreach_data(data)
    add_scam_case(data)
    rs = RunStore(data["settings"])                                  # the schedule's optional blocks, filled in
    rs.set_pause(None, "travelling", NOW)                            # no end: stays active whatever the wall clock
    _save_catch_up(rs, {"created_at": "2026-09-24T08:00:00+00:00", "updated_at": "2026-09-24T08:00:00+00:00",
                        "kinds": {"score": {"first_missed": "2026-09-23T09:00:00+00:00", "slots": 2,
                                            "last_missed": "2026-09-24T09:00:00+00:00"}}})
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c, data, str(tmp_path)
    ix.close()
    monkeypatch.delenv("TZ")
    time.tzset()


def _stable(body, tmp: str, ids: dict[str, str], sizes: bool = False):
    if sizes and isinstance(body, (int, float)) and not isinstance(body, bool):
        return "<n>"
    if isinstance(body, dict):
        return {k: (f"<{k}>" if k in VOLATILE and v is not None else _stable(v, tmp, ids, sizes)) for k, v in body.items()}
    if isinstance(body, list):
        return [_stable(v, tmp, ids, sizes) for v in body]
    if isinstance(body, str):
        body = body.replace(tmp, "<tmp>")
        for name, v in ids.items():
            body = body.replace(v, f"<{name}>")
        return re.sub(r"\b\d{8}T\d{6}-[0-9a-f]+\b", "<gen_id>", body)
    return body


PATHS = {
    "runs": "/api/runs", "runs_current": "/api/runs/current", "runs_detail": "/api/runs/{run}",
    "schedule": "/api/schedule", "storage": "/api/storage", "advise": "/api/advise",
    "settings": "/api/settings", "settings_runs": "/api/settings/runs",
    "actions": "/api/actions", "actions_done": "/api/actions?tab=done",
    "inbox": "/api/inbox", "inbox_detail": "/api/inbox/{job}", "contacts": "/api/contacts",
}


@pytest.mark.parametrize("name", sorted(PATHS))
def test_response_matches_snapshot(api, name):
    c, data, tmp = api
    ids = {f"job_{k}": v for k, v in data["jobs"].items()} | {f"run_{k}": v for k, v in data["runs"].items()}
    ids |= {f"action_{k}": v for k, v in data["actions"].items()}
    url = PATHS[name].format(run=data["runs"]["score"], job=data["jobs"]["interview"])
    r = c.get(url)
    assert r.status_code == 200, r.text
    _check(name, r.json(), tmp, ids)


def _check(name, body, tmp, ids):
    got = _stable(body, tmp, dict(sorted(ids.items(), key=lambda kv: -len(kv[1]))), name in SIZES)
    snap = SNAPSHOTS / f"ops_{name}.json"
    if os.environ.get("CAREEROS_UPDATE_SNAPSHOTS"):
        snap.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n")
    assert got == json.loads(snap.read_text())


def test_current_run_while_a_batch_runs_matches_snapshot(api):
    """/api/runs/current is null in the shared fixture; hold the runner lock and a job lock to pin CurrentRun."""
    c, data, tmp = api
    rs = RunStore(data["settings"])
    run = rs.new_run("prepare", "manual", {"preset": "small", "max_jobs": 2, "max_minutes": 30},
                     NOW - timedelta(minutes=5), counters={"attempted": 0},
                     queue=[{"job_id": data["jobs"]["queued"], "rank": 1, "score": 60, "why": "posted 4d ago (+50)"}])
    locks.acquire(rs.runner_lock_path, owner=f"run:{run['id']}", ttl_seconds=3600, pid=os.getpid(), note="prepare",
                  pid_alive=lambda p: True)
    (rs.dir / "locks").mkdir(parents=True, exist_ok=True)
    locks.acquire(rs.dir / "locks" / f"{data['jobs']['queued']}.lock", owner=f"run:{run['id']}", ttl_seconds=3600,
                  pid=os.getpid(), note="prepare", pid_alive=lambda p: True)
    r = c.get("/api/runs/current")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == run["id"] and body["current_job"] == data["jobs"]["queued"]
    # the lock's wall-clock stamps, host and token, today's cap date and the elapsed minutes vary per run
    body["holder"].update({k: f"<{k}>" for k in ("acquired_at", "expires_at", "host", "token")})
    body["cap"]["date"], body["used"]["minutes"] = "<date>", "<minutes>"
    ids = {f"job_{k}": v for k, v in data["jobs"].items()} | {"run_current": run["id"]}
    _check("runs_current_running", body, tmp, ids)
