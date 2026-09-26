"""Action Items and Pipeline through the HTTP API: FastAPI TestClient over a temp repo root with the fictional UI
data. Every write lands in the real files (tracker, status.json, companies.yaml, flagged registry), the index
answers the next GET, and one `changed` event goes to open tabs."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import yaml
from conftest import make_temp_root
from fixtures.ui_data import add_scam_case, build_ui_data

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from careeros.safety import registry  # noqa: E402
from careeros.store import Store  # noqa: E402
from careeros.tracker import Tracker  # noqa: E402
from careeros.ui.app import create_app  # noqa: E402
from careeros.ui.events import Broker  # noqa: E402
from careeros.ui.index import Index  # noqa: E402
from careeros.ui.security import LOOPBACK  # noqa: E402

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)
W = {"X-CareerOS": "1"}


class Spy(Broker):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[tuple[str, dict]] = []

    def publish(self, event, data):  # noqa: ANN001, ANN201
        self.sent.append((event, data))
        return super().publish(event, data)


@pytest.fixture
def data(tmp_path):
    d = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    d["scam"] = add_scam_case(d)
    return d


@pytest.fixture
def env(data, tmp_path):
    ix = Index(data["settings"])
    ix.rebuild()
    spy = Spy()
    app = create_app(data["settings"], index=ix, broker=spy, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=tmp_path / "no-static", now=lambda: NOW)
    with TestClient(app) as c:
        yield c, spy
    ix.close()


def _items(view: dict) -> dict[str, dict]:
    return {i["id"]: i for g in view["groups"] for i in g["items"]}


# --- Action Items -------------------------------------------------------------------------------------------------

def test_list_open_groups_and_counts(env, data):
    c, _ = env
    v = c.get("/api/actions", params={"tz": "America/New_York"}).json()
    assert v["counts"] == {"open": 4, "today": 1, "done": 1}
    assert [g["key"] for g in v["groups"]] == ["tomorrow", "nodate"]
    high = _items(v)[data["actions"]["high"]]
    assert high["due_reason"] == "posting closes" and high["level"] == "soon" and high["bucket"] == "tomorrow"
    assert _items(v)[data["actions"]["scam"]]["scam_actions"] is True
    done = c.get("/api/actions", params={"tab": "done"}).json()
    assert list(_items(done)) == [data["actions"]["done"]]
    assert c.get("/api/actions", params={"tab": "nope"}).status_code == 400
    assert c.get("/api/actions", params={"tz": "Mars/Olympus"}).status_code == 400


def test_done_reopen_bulk_and_events(env, data):
    c, spy = env
    a = data["actions"]
    assert c.post(f"/api/actions/{a['medium']}/done").status_code == 403       # no X-CareerOS header
    r = c.post(f"/api/actions/{a['medium']}/done", headers=W)
    assert r.status_code == 200 and r.json()["ok"] == [a["medium"]]
    assert spy.sent[-1][0] == "changed" and spy.sent[-1][1]["actions"] is True
    assert c.get("/api/actions").json()["counts"]["open"] == 3
    assert c.post(f"/api/actions/{a['medium']}/reopen", headers=W).status_code == 200
    assert c.get("/api/actions").json()["counts"]["open"] == 4
    r = c.post("/api/actions/bulk-done", json={"ids": [a["low"], a["high"]]}, headers=W)
    assert sorted(r.json()["ok"]) == sorted([a["low"], a["high"]])
    assert {it["ID"] for it in Tracker(settings=data["settings"]).list_action_items()} == {a["medium"], a["scam"]}
    r = c.post("/api/actions/bulk-reopen", json={"ids": [a["low"], a["high"]]}, headers=W)
    assert c.get("/api/actions").json()["counts"]["open"] == 4
    assert c.post("/api/actions/nope/done", headers=W).status_code == 404
    assert c.post("/api/actions/bulk-done", json={"ids": []}, headers=W).status_code == 422


def test_add_item_and_due_date(env, data):
    c, _ = env
    r = c.post("/api/actions", headers=W, json={"what": "Call the recruiter back", "type": "other", "needs": "phone",
                                                "priority": "H", "job_id": data["jobs"]["applied"],
                                                "link": "https://mail.example.com/thread/1"})
    assert r.status_code == 200
    aid = r.json()["id"]
    it = _items(c.get("/api/actions").json())[aid]
    assert it["company"] == "Hooli" and it["role"] == "New Grad Engineer" and it["bucket"] == "nodate"
    r = c.post(f"/api/actions/{aid}/due", headers=W, json={"due": "2026-09-25T09:00:00-04:00",
                                                           "due_reason": "reply within 48 hours"})
    assert r.status_code == 200
    it = _items(c.get("/api/actions", params={"tz": "America/New_York"}).json())[aid]
    assert it["bucket"] == "tomorrow" and it["due_reason"] == "reply within 48 hours"
    assert c.post(f"/api/actions/{aid}/due", headers=W, json={"due": "soonish"}).status_code == 400
    assert c.post("/api/actions", headers=W, json={"what": "x", "link": "javascript:alert(1)"}).status_code == 400
    assert c.post("/api/actions", headers=W, json={"what": "x", "job_id": "nope00000000"}).status_code == 404


def test_block_company_and_undo(env, data):
    c, spy = env
    s, scam = data["settings"], data["scam"]
    companies = s.root / "config" / "companies.yaml"
    before = companies.read_text()
    r = c.post(f"/api/actions/{scam['action_id']}/block-company", headers=W)
    assert r.status_code == 200 and r.json() == {"company": scam["company"], "added": True, "queued": False,
                                                 "job_id": scam["job_id"]}
    bl = yaml.safe_load(companies.read_text())["blocklist"]["companies"]
    assert bl[-1] == scam["company"] and "Globex Bank" in bl
    assert spy.sent[-1][1]["config"] is True
    assert scam["action_id"] not in _items(c.get("/api/actions").json())
    r = c.post(f"/api/actions/{scam['action_id']}/unblock-company", headers=W, json={"company": scam["company"]})
    assert r.status_code == 200 and r.json()["removed"] is True
    assert yaml.safe_load(companies.read_text()) == yaml.safe_load(before)
    assert scam["action_id"] in _items(c.get("/api/actions").json())
    # only a scam item can block
    assert c.post(f"/api/actions/{data['actions']['medium']}/block-company", headers=W).status_code == 400


def test_mark_safe_and_undo(env, data):
    c, _ = env
    s, scam = data["settings"], data["scam"]
    reg = registry.default_path(s)
    r = c.post(f"/api/actions/{scam['action_id']}/mark-safe", headers=W)
    assert r.status_code == 200
    out = r.json()
    assert out["previous_status"] == "needs_review" and out["registry_before"]["state"] == "active"
    assert Store(s).get_status(scam["job_id"]) == "queued"
    assert Tracker(settings=s).get_job(scam["job_id"])["Status"] == "queued"
    assert registry.is_flagged(registry.load(reg), scam["company"]) is None
    board = c.get("/api/pipeline").json()
    queued = next(col for col in board["columns"] if col["name"] == "Queued")
    assert scam["job_id"] in [card["job_id"] for card in queued["cards"]]
    r = c.post(f"/api/actions/{scam['action_id']}/mark-safe/undo", headers=W,
               json={"previous_status": out["previous_status"], "registry_before": out["registry_before"]})
    assert r.status_code == 200
    assert Store(s).get_status(scam["job_id"]) == "needs_review"
    assert registry.is_flagged(registry.load(reg), scam["company"]) is not None
    assert scam["action_id"] in _items(c.get("/api/actions").json())
    bad = dict(out["registry_before"], company="Someone Else")
    assert c.post(f"/api/actions/{scam['action_id']}/mark-safe/undo", headers=W,
                  json={"registry_before": bad}).status_code == 400


# --- Pipeline -----------------------------------------------------------------------------------------------------

def test_pipeline_board(env, data):
    c, _ = env
    b = c.get("/api/pipeline").json()
    assert [col["count"] for col in b["columns"]] == [2, 1, 2, 1, 1, 0]
    assert b["closed"] == {"count": 2, "by_status": {"skipped": 1, "rejected": 1}}
    assert b["options"]["categories"] == ["swe_backend"]
    only_a = c.get("/api/pipeline", params=[("tier", "A")]).json()
    assert sum(col["count"] for col in only_a["columns"]) == 2
    m = c.get("/api/meta").json()
    assert m["pipeline"]["card_limit"] == 10 and m["ui"]["due_soon_hours"] == 48


def test_set_status_moves_the_card(env, data):
    c, spy = env
    jid = data["jobs"]["queued"]
    assert c.post(f"/api/jobs/{jid}/status", json={"status": "needs_review"}).status_code == 403
    r = c.post(f"/api/jobs/{jid}/status", headers=W, json={"status": "needs_review", "note": "moved on the board"})
    assert r.status_code == 200 and r.json() == {"job_id": jid, "status": "needs_review", "previous": "queued"}
    assert spy.sent[-1][1]["jobs"] == [jid]
    b = c.get("/api/pipeline").json()
    review = next(col for col in b["columns"] if col["name"] == "Needs review")
    assert jid in [card["job_id"] for card in review["cards"]]
    # undo = set it back
    assert c.post(f"/api/jobs/{jid}/status", headers=W, json={"status": "queued"}).json()["previous"] == "needs_review"
    assert c.post(f"/api/jobs/{jid}/status", headers=W, json={"status": "launched"}).status_code == 400
    assert c.post("/api/jobs/nope00000000/status", headers=W, json={"status": "queued"}).status_code == 404
