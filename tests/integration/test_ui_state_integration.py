"""GET/PUT /api/ui-state (REQ-121): tour_done lives in data/ui_state.json (per install), written atomically."""
from __future__ import annotations

import json
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
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    data = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c, data["settings"].root / "data" / "ui_state.json"
    ix.close()


def test_fresh_install_tour_not_done(setup):
    client, path = setup
    assert not path.exists()
    r = client.get("/api/ui-state")
    assert r.status_code == 200, r.text
    assert r.json() == {"tour_done": False}


def test_put_persists_tour_done_across_reload(setup):
    client, path = setup
    r = client.put("/api/ui-state", json={"tour_done": True}, headers=W)
    assert r.status_code == 200, r.text
    assert r.json() == {"tour_done": True}
    assert json.loads(path.read_text()) == {"tour_done": True}
    assert client.get("/api/ui-state").json() == {"tour_done": True}


def test_put_needs_write_header_and_bool(setup):
    client, path = setup
    assert client.put("/api/ui-state", json={"tour_done": True}).status_code == 403
    assert client.put("/api/ui-state", json={"tour_done": "yes"}, headers=W).status_code == 422
    assert not path.exists()


def test_broken_file_reads_as_not_done(setup):
    client, path = setup
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert client.get("/api/ui-state").json() == {"tour_done": False}
