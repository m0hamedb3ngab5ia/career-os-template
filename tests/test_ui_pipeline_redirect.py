"""E2E-016-01: /pipeline is gone; it redirects to the Jobs Applied board (REQ-129, DEC-022)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import make_temp_root
from fastapi.testclient import TestClient
from fixtures.ui_data import build_ui_data

from careeros.ui.app import create_app
from careeros.ui.index import Index
from careeros.ui.security import LOOPBACK

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
TARGET = "/jobs?tab=applied&view=board"


@pytest.fixture
def client(tmp_path):
    d = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    ix = Index(d["settings"])
    ix.rebuild()
    app = create_app(d["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c
    ix.close()


def test_E2E_016_01_pipeline_redirects_to_applied_board(client):
    r = client.get("/pipeline", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == TARGET


def test_E2E_016_01_api_pipeline_is_gone(client):
    assert client.get("/api/pipeline").status_code == 404
