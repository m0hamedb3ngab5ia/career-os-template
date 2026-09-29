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
