"""Contacts and Inbox & follow-ups over HTTP: FastAPI TestClient on a temp root with the fictional UI data plus
contacts, drafts and an inbox-sync log line; the mark write goes through `careeros outreach mark`'s code and the
index picks it up."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import make_temp_root
from fixtures.ui_data import add_outreach_data, build_ui_data

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
W = {"X-CareerOS": "1"}


@pytest.fixture
def data(tmp_path):
    return add_outreach_data(build_ui_data(make_temp_root(tmp_path / "repo"), NOW))


@pytest.fixture
def client(data, tmp_path):
    ix = Index(data["settings"])
    ix.rebuild()
    app = create_app(data["settings"], index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        c.ix = ix  # type: ignore[attr-defined]
        yield c
    ix.close()


def test_contacts_list(client):
    got = client.get("/api/contacts").json()
    by = {c["name"]: c for c in got["items"]}
    assert by["Pat Rivers"]["mode"] == "manual" and by["Sam Lee"]["mode"] == "linkedin_draft"
    assert got["linkedin_drafts"] == 1


def test_mark_contact_round_trip(client, data):
    jid = data["jobs"]["interview"]
    r = client.post(f"/api/contacts/{jid}/Sam%20Lee/mark", json={"mutuals": 3}, headers=W)
    assert r.status_code == 200 and r.json()["mutuals"] == 3
    saved = json.loads((Path(data["settings"].paths["jobs_dir"]) / jid / "contacts.json").read_text())
    assert saved["contacts"][1]["mutuals"] == 3
    client.ix.update_jobs([jid])            # what the watcher does after the write
    sam = next(c for c in client.get("/api/contacts").json()["items"] if c["name"] == "Sam Lee")
    assert sam["mode"] == "manual" and sam["manual_detail"] == "3 mutual connections"


def test_mark_errors(client, data):
    jid = data["jobs"]["interview"]
    assert client.post(f"/api/contacts/{jid}/Sam%20Lee/mark", json={"mutuals": 3}).status_code == 403  # no header
    assert client.post(f"/api/contacts/{jid}/Sam%20Lee/mark", json={}, headers=W).status_code == 400
    assert client.post(f"/api/contacts/{jid}/Sam%20Lee/mark", json={"degree": 9}, headers=W).status_code == 422
    assert client.post(f"/api/contacts/{jid}/Nobody/mark", json={"degree": 1}, headers=W).status_code == 404
    assert client.post("/api/contacts/nope00000000/Sam/mark", json={"degree": 1}, headers=W).status_code == 404


def test_inbox_list_and_detail(client, data):
    got = client.get("/api/inbox").json()
    assert [r["company"] for r in got["items"]] == ["Hooli", "Stark Industries"]
    assert got["sync"]["available"] is False and got["sending"]["reason"] == "Follow-up sending isn't built yet"
    d = client.get(f"/api/inbox/{data['jobs']['applied']}").json()
    assert d["drafts"][d["primary"]]["placeholders"] == ["[SPECIFIC CONNECTION]", "[MOST RELEVANT EXPERIENCE]"]
    assert any(e["type"] == "pending_update" for e in d["thread"])
    assert client.get("/api/inbox/nope00000000").status_code == 404
