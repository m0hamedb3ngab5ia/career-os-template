"""GET /api/next-step (REQ-122, E2E-014-02): readiness done and 0 ticked jobs -> "Pick jobs" to the Jobs list."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import build_ui_data

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
W = {"X-CareerOS": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr("careeros.readiness.items", lambda root: [{"id": "a", "label": "A", "must": True,
                                                                   "done": True, "fix_link": "/profile"}])
    data = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c, ix
    ix.close()


def test_e2e_014_02_ready_no_ticked_jobs_says_pick_jobs(client):
    client, ix = client
    ids = [r["job_id"] for r in ix.query("SELECT job_id FROM jobs", ())]
    assert ids
    assert client.post("/api/jobs/select", json={"ids": ids, "selected": False}, headers=W).status_code == 200
    r = client.get("/api/next-step")
    assert r.status_code == 200
    assert r.json() == {"key": "pick_jobs", "label": "Pick jobs", "href": "/jobs"}


def test_ticked_jobs_no_batch_says_start_pipeline(client):
    client, _ = client
    assert client.get("/api/next-step").json()["key"] == "start_pipeline"
