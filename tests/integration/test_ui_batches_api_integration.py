"""Batches API + CLI end to end over a temp repo root with the fictional UI data: preview (dry run), create,
read back, refusals. Nothing runs: slice 7 only plans the batch."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import pytest
from conftest import PY, make_temp_root, subprocess_env
from fixtures.ui_data import build_ui_data

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.runs import batches  # noqa: E402
from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
W = {"X-CareerOS": "1"}


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return build_ui_data(make_temp_root(tmp_path / "repo"), NOW)


@pytest.fixture
def client(data, tmp_path):
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c
    ix.close()


def test_dry_run_previews_without_saving(client, data):
    ids = data["jobs"]
    r = client.post("/api/batches", json={"job_ids": [ids["found"], ids["applied"]], "stop_at": "prepare",
                                          "dry_run": True}, headers=W)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True and body["id"] is None
    assert [s["job_id"] for s in body["selected"]] == [ids["found"]]
    assert body["selected"][0]["stages"] == ["score", "prepare"]
    assert body["excluded"] == [{"job_id": ids["applied"], "reason": "status applied"}]
    assert batches.list_ids(data["settings"]) == []


def test_create_then_get(client, data):
    r = client.post("/api/batches", json={"job_ids": [data["jobs"]["found"]], "stop_at": "score", "name": "Mine"},
                    headers=W)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "queued" and b["name"] == "Mine"
    g = client.get(f"/api/batches/{b['id']}")
    assert g.status_code == 200 and g.json()["selected"][0]["state"] == "pending"


def test_refusals(client, data):
    assert client.get("/api/batches/missing").status_code == 404
    assert client.post("/api/batches", json={"job_ids": [data["jobs"]["found"]], "stop_at": "mass"},
                       headers=W).status_code == 422
    assert client.post("/api/batches", json={"job_ids": [data["jobs"]["applied"]], "stop_at": "score"},
                       headers=W).status_code == 422
    assert client.post("/api/batches", json={"job_ids": [data["jobs"]["found"]], "stop_at": "score"}
                       ).status_code in (400, 403)


def test_cli_create_and_show(data, tmp_path):
    root = data["settings"].root
    env = subprocess_env(root, tmp_path / "home")

    def cli(*args):
        return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), "batch", *args], capture_output=True,
                              text=True, env=env, timeout=60, cwd=root)

    dry = cli("create", "--stop-at", "score", "--dry-run", "--json", data["jobs"]["found"])
    assert dry.returncode == 0, dry.stderr
    assert json.loads(dry.stdout)["selected"][0]["job_id"] == data["jobs"]["found"]
    bad = cli("create", "--stop-at", "score", data["jobs"]["applied"])
    assert bad.returncode == 2 and "status applied" in bad.stderr
    made = cli("create", "--stop-at", "score", "--json", data["jobs"]["found"])
    bid = json.loads(made.stdout)["id"]
    shown = cli("show", bid)
    assert shown.returncode == 0 and data["jobs"]["found"] in shown.stdout
    assert cli("show", "missing").returncode == 1


def test_drive_end_to_end_then_controls(client, data, monkeypatch):
    """Slice 8: the driver works a saved batch with a fake headless invoke; the API reads the progress back and
    pause / cancel / retry / start answer by the batch lock (single writer)."""
    import sys
    from pathlib import Path

    from careeros.runs import locks

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from test_runs_runner import FakeInvoke

    s = data["settings"]
    s.pipeline = {**s.pipeline, "runs": {**(s.pipeline.get("runs") or {}), "preflight_doctor": False}}
    b = client.post("/api/batches", json={"job_ids": [data["jobs"]["found"]], "stop_at": "score"}, headers=W).json()
    inv = FakeInvoke(s)
    batches.drive(s, b["id"], invoke=inv, now=lambda: NOW)
    g = client.get(f"/api/batches/{b['id']}").json()
    assert g["status"] == "done" and g["selected"][0]["state"] == "done" and g["selected"][0]["result"] == "scored"
    assert len(inv.calls) == 1 and inv.calls[0]["job_id"] == data["jobs"]["found"]
    assert client.post(f"/api/batches/{b['id']}/start", headers=W).status_code == 422  # done
    r = client.post(f"/api/batches/{b['id']}/retry", json={}, headers=W).json()
    assert r["status"] == "done" and r["retried"] == 0  # nothing failed: the UI must not call /start

    b2 = client.post("/api/batches", json={"job_ids": [data["jobs"]["found"]], "stop_at": "prepare"},
                     headers=W).json()
    lk = locks.acquire(batches._lock_path(s, b2["id"]), owner="driver", ttl_seconds=60, pid=None)
    r = client.post(f"/api/batches/{b2['id']}/pause", headers=W).json()
    assert r["requested"] == "pause" and r["status"] == "queued"  # a request: the driver writes the status
    assert client.post(f"/api/batches/{b2['id']}/retry", json={}, headers=W).status_code == 409
    assert client.post(f"/api/batches/{b2['id']}/start", headers=W).status_code == 409
    locks.release(lk.path, lk.token)
    assert client.post(f"/api/batches/{b2['id']}/cancel", headers=W).json()["status"] == "cancelled"
    assert client.post("/api/batches/missing/pause", headers=W).status_code == 404


def test_batch_skips_prepare_for_a_job_unticked_after_scoring(client, data):
    """REQ-104: each batch stage re-checks `selected`; untick between score and prepare -> prepare never runs."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from test_runs_runner import FakeInvoke

    from careeros.store import Store

    s = data["settings"]
    s.pipeline = {**s.pipeline, "runs": {**(s.pipeline.get("runs") or {}), "preflight_doctor": False}}
    jid = data["jobs"]["found"]
    Store(s).set_selected([jid], True)
    b = client.post("/api/batches", json={"job_ids": [jid], "stop_at": "prepare"}, headers=W).json()

    class Untick(FakeInvoke):
        def __call__(self, *a, **kw):
            Store(self.s).set_selected([jid], False)
            return super().__call__(*a, **kw)

    inv = Untick(s)
    batches.drive(s, b["id"], invoke=inv, now=lambda: NOW)
    g = client.get(f"/api/batches/{b['id']}").json()
    assert len(inv.calls) == 1  # score only
    assert "not selected" in json.dumps(g["selected"][0]), g["selected"][0]


def test_cli_batch_cancel_and_run(data, tmp_path):
    b = batches.create(data["settings"], [data["jobs"]["found"]], "score", now=NOW)
    root, env = str(data["settings"].root), subprocess_env(data["settings"].root, tmp_path / "home")
    out = subprocess.run([PY, "-m", "careeros.cli", "--root", root, "batch", "cancel", b["id"], "--json"],
                         capture_output=True, text=True, env=env, timeout=60, cwd=root)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["status"] == "cancelled"
    out = subprocess.run([PY, "-m", "careeros.cli", "--root", root, "batch", "run", b["id"], "--json"],
                         capture_output=True, text=True, env=env, timeout=60, cwd=root)
    assert out.returncode == 0 and json.loads(out.stdout)["status"] == "cancelled"  # nothing left to run


def test_e2e_013_02_api_stops_are_capped_server_side(client, data):
    """E2E-013-02: POST /api/batches with stops {tierA: submit} -> Tier A never submitted, reason in batch file."""
    ids = data["jobs"]
    body = {"job_ids": [ids["found"], ids["review"]], "stop_at": "score",
            "stops": {ids["review"]: "submit", ids["found"]: "prepare"}}
    r = client.post("/api/batches", json=body, headers=W)
    assert r.status_code == 200, r.text
    saved = batches.load(data["settings"], r.json()["id"])
    assert saved["stops"] == body["stops"]
    rows = {x["job_id"]: x for x in saved["selected"]}
    assert rows[ids["found"]]["stop_at"] == "prepare"
    tier_a = rows.get(ids["review"]) or {x["job_id"]: x for x in saved["excluded"]}[ids["review"]]
    assert "tier_a" in (tier_a.get("cap") or tier_a.get("reason"))
    assert not tier_a.get("auto_submit")
    assert client.post("/api/batches", json={**body, "stops": {ids["found"]: "mass"}}, headers=W).status_code == 422


def test_cli_job_stop(data, tmp_path):
    root, jid = data["settings"].root, data["jobs"]["found"]
    env = subprocess_env(root, tmp_path / "home")

    def cli(*args):
        return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), "batch", "create", "--stop-at",
                               "score", "--dry-run", *args, jid], capture_output=True, text=True, env=env,
                              timeout=60, cwd=root)

    ok = cli("--json", "--job-stop", f"{jid}=prepare")
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["selected"][0]["stages"] == ["score", "prepare"]
    bad = cli("--job-stop", "nope")
    assert bad.returncode == 2 and "JOB_ID=STAGE" in bad.stderr
    dup = cli("--job-stop", f"{jid}=prepare", "--job-stop", f"{jid}=fill")
    assert dup.returncode == 2 and "more than once" in dup.stderr
