"""careeros.ui.services.pipeline (the board) and job_actions (set status), over the fictional UI data."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import add_scam_case, build_ui_data

from careeros.config import Settings
from careeros.store import Store
from careeros.tracker import Tracker
from careeros.ui.index import Index
from careeros.ui.services import job_actions
from careeros.ui.services import pipeline as svc

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def data(tmp_path):
    d = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    add_scam_case(d)
    return d


@pytest.fixture
def idx(data):
    ix = Index(data["settings"])
    ix.rebuild()
    yield ix
    ix.close()


def col(board: dict, name: str) -> dict:
    return next(c for c in board["columns"] if c["name"] == name)


def test_board_columns_counts_and_closed(idx, data):
    b = svc.board(data["settings"], idx)
    assert [c["name"] for c in b["columns"]] == ["Found", "Queued", "Needs review", "Applied",
                                                "Screening · Interview", "Offer"]
    assert col(b, "Found")["count"] == 2 and col(b, "Needs review")["count"] == 2
    assert col(b, "Offer")["count"] == 0 and col(b, "Offer")["cards"] == []
    assert b["closed"] == {"count": 2, "by_status": {"skipped": 1, "rejected": 1}}
    assert b["card_limit"] == 10


def test_card_fields(idx, data):
    b = svc.board(data["settings"], idx)
    cards = {c["job_id"]: c for c in col(b, "Needs review")["cards"]}
    review = cards[data["jobs"]["review"]]
    assert review["company"] == "Umbrella Labs" and review["title"] == "Infrastructure Engineer"
    assert (review["fit"], review["tier"], review["safety"], review["status"]) == (91, "A", "review", "needs_review")
    assert review["qa_passed"] is True and review["override"] is None
    # an open action item is the hint (highest priority, soonest due)
    assert review["hint"]["kind"] == "action" and review["hint"]["type"] == "review" and review["hint"]["due"]
    scam = cards[data["jobs"]["scam"]]
    assert scam["hint"]["kind"] == "action" and scam["hint"]["type"] == "scam_suspected"
    found = {c["job_id"]: c for c in col(b, "Found")["cards"]}
    assert found[data["jobs"]["found"]]["hint"] == {"kind": "not_scored"}
    assert found[data["jobs"]["found"]]["qa_passed"] is None


def test_safety_flag_hint_when_no_open_item(idx, data):
    s = data["settings"]
    Tracker(settings=s).mark_action_done(data["actions"]["scam"])
    idx.update_tracker()
    b = svc.board(s, idx)
    scam = next(c for c in col(b, "Needs review")["cards"] if c["job_id"] == data["jobs"]["scam"])
    assert scam["hint"] == {"kind": "safety", "text": "asks for payment"}


def test_override_from_tracker(idx, data):
    s = data["settings"]
    tr = Tracker(settings=s)
    tr.upsert_job({"job_id": data["jobs"]["queued"], "company": "Initech", "override": "manual"})
    b = svc.board(s, idx)
    card = col(b, "Queued")["cards"][0]
    assert card["job_id"] == data["jobs"]["queued"] and card["override"] == "manual"


def test_filters(idx, data):
    s = data["settings"]
    b = svc.board(s, idx, tier=["A"])
    assert sum(c["count"] for c in b["columns"]) == 2
    b = svc.board(s, idx, safety=["block"])
    assert [c["job_id"] for c in col(b, "Needs review")["cards"]] == [data["jobs"]["scam"]]
    b = svc.board(s, idx, location=["Remote"])
    assert sum(c["count"] for c in b["columns"]) == 1 and b["closed"]["count"] == 0
    b = svc.board(s, idx, category=["nope"])
    assert sum(c["count"] for c in b["columns"]) == 0
    opts = svc.board(s, idx)["options"]
    assert opts["categories"] == ["swe_backend"]
    assert [o["value"] for o in opts["locations"]] == ["New York, NY", "Remote"]


def test_card_limit_and_expand(idx, data, monkeypatch):
    s = data["settings"]
    s.pipeline.setdefault("ui", {})["pipeline"] = {"card_limit": 1}
    b = svc.board(s, idx)
    assert b["card_limit"] == 1
    assert len(col(b, "Found")["cards"]) == 1 and col(b, "Found")["count"] == 2
    b = svc.board(s, idx, expand=["Found"])
    assert len(col(b, "Found")["cards"]) == 2 and len(col(b, "Needs review")["cards"]) == 1


def test_cards_sorted_by_fit_then_newest(idx, data):
    b = svc.board(data["settings"], idx)
    fits = [c["fit"] for c in col(b, "Needs review")["cards"]]
    assert fits == [91, 74]


def test_empty_board_is_zeros(tmp_path):
    s = Settings.load(make_temp_root(tmp_path / "empty"))
    ix = Index(s)
    ix.rebuild()
    b = svc.board(s, ix)
    assert all(c["count"] == 0 and c["cards"] == [] for c in b["columns"])
    assert b["closed"] == {"count": 0, "by_status": {}}
    ix.close()


def test_set_status_writes_both_and_returns_previous(idx, data):
    s = data["settings"]
    jid = data["jobs"]["queued"]
    got = job_actions.set_status(s, jid, "needs_review", note="moved on the board")
    assert got == {"job_id": jid, "status": "needs_review", "previous": "queued"}
    assert Store(s).get_status(jid) == "needs_review"
    assert Tracker(settings=s).get_job(jid)["Status"] == "needs_review"


def test_set_status_rejects_unknown_status_and_job(idx, data):
    s = data["settings"]
    with pytest.raises(ValueError):
        job_actions.set_status(s, data["jobs"]["queued"], "launched")
    with pytest.raises(LookupError):
        job_actions.set_status(s, "nope00000000", "queued")
    assert Store(s).get_status(data["jobs"]["queued"]) == "queued"
