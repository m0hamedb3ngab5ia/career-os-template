"""The typed API surface: GET /api/meta and /api/status return exactly the JSON the service functions build
(no key dropped by FastAPI's response filtering once the routes carry TypedDict response shapes), pinned by a
snapshot on the fictional UI data; and the committed ui/openapi.json matches a fresh dump of the app's schema."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import make_temp_root
from fixtures.ui_data import build_ui_data

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.runs.store import RunStore  # noqa: E402
from careeros.runs.tick import _save_catch_up  # noqa: E402
from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
SNAPSHOTS = REPO / "tests" / "fixtures" / "ui_snapshots"
NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")        # week_start and naive timestamps use local time: pin it
    import time
    time.tzset()
    data = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    rs = RunStore(data["settings"])                                  # the optional blocks, filled in
    rs.set_pause(NOW + timedelta(hours=3), "travelling", NOW)
    _save_catch_up(rs, {"created_at": "2026-09-24T08:00:00+00:00", "updated_at": "2026-09-24T08:00:00+00:00",
                        "kinds": {"score": {"first_missed": "2026-09-23T09:00:00+00:00", "slots": 2,
                                            "last_missed": "2026-09-24T09:00:00+00:00"}}})
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c
    ix.close()
    monkeypatch.delenv("TZ")
    time.tzset()


def _stable(body: dict) -> dict:
    """Blank the values that change per build (generated ids, index time) but keep every key."""
    body = json.loads(json.dumps(body))
    if "index" in body:
        body["index"]["indexed_at"] = "<indexed_at>"
    for r in body.get("recent_runs", []):
        r["id"] = "<run_id>"
    for r in body.get("tiles", {}).get("needs_you", {}).get("rows", []):
        r["id"], r["created"] = "<action_id>", "<created>"        # the tracker stamps wall-clock time
    for rows in [t.get("rows", []) for t in body.get("tiles", {}).values()]:
        for r in rows:
            r["job_id"] = "<job_id>" if r.get("job_id") else r.get("job_id")
    return body


@pytest.mark.parametrize("name", ["meta", "status"])
def test_response_matches_snapshot(client, name):
    got = _stable(client.get(f"/api/{name}").json())
    snap = SNAPSHOTS / f"{name}.json"
    if os.environ.get("CAREEROS_UPDATE_SNAPSHOTS"):
        snap.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n")
    assert got == json.loads(snap.read_text())


def test_committed_openapi_schema_is_current():
    from careeros.ui.openapi import dump

    committed = (REPO / "ui" / "openapi.json").read_text()
    assert committed == dump(), (
        "ui/openapi.json is stale (a response shape changed, or FastAPI/pydantic was bumped, which also requires "
        "regenerating): run `python -m careeros.ui.openapi > ui/openapi.json && (cd ui && npm run gen:api)`"
    )
