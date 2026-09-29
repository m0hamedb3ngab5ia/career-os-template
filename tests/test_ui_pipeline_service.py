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


def apps(board: dict) -> dict[str, dict]:
    return {c["job_id"]: c for c in board["applications"]}


def to(data, idx, key: str, status: str) -> str:
    jid = data["jobs"][key]
    job_actions.set_status(data["settings"], jid, status)
    idx.rebuild()
    return jid


def test_funnel_counts_submitted_this_week_and_closed(idx, data):
    b = svc.board(data["settings"], idx, now=NOW)
    assert b["funnel"] == [{"status": "found", "count": 1}, {"status": "scored", "count": 1},
                           {"status": "queued", "count": 1}, {"status": "prepared", "count": 0},
                           {"status": "needs_review", "count": 2}]
    # Hooli applied 2 days ago; Stark (interview) applied 12 days ago
    assert b["submitted"] == {"count": 1, "since": "2026-09-17"}
    assert b["closed"] == {"count": 2, "by_status": {"skipped": 1, "rejected": 1}}
    assert "columns" not in b and "card_limit" not in b


def test_funnel_counts_pure():
    assert svc.funnel_counts({"found": 3, "needs_review": 1, "applied": 9}) == [
        {"status": "found", "count": 3}, {"status": "scored", "count": 0}, {"status": "queued", "count": 0},
        {"status": "prepared", "count": 0}, {"status": "needs_review", "count": 1}]


def test_applications_are_applied_to_offer_only(idx, data):
    b = svc.board(data["settings"], idx, now=NOW)
    assert [c["job_id"] for c in b["applications"]] == [data["jobs"]["interview"], data["jobs"]["applied"]]
    hooli = apps(b)[data["jobs"]["applied"]]
    assert (hooli["company"], hooli["status"], hooli["fit"], hooli["tier"]) == ("Hooli", "applied", 84, "B")
    assert hooli["override"] is None


def test_card_fields_and_action_hint(idx, data):
    jid = to(data, idx, "review", "screening")
    review = apps(svc.board(data["settings"], idx))[jid]
    assert review["company"] == "Umbrella Labs" and review["title"] == "Infrastructure Engineer"
    assert (review["fit"], review["tier"], review["safety"], review["status"]) == (91, "A", "review", "screening")
    assert review["qa_passed"] is True
    # an open action item is the hint (highest priority, soonest due)
    assert review["hint"]["kind"] == "action" and review["hint"]["type"] == "review" and review["hint"]["due"]


def test_safety_flag_hint_when_no_open_item(idx, data):
    s = data["settings"]
    Tracker(settings=s).mark_action_done(data["actions"]["scam"])
    jid = to(data, idx, "scam", "screening")
    assert apps(svc.board(s, idx))[jid]["hint"] == {"kind": "safety", "text": "asks for payment"}


def test_override_from_tracker(idx, data):
    s = data["settings"]
    Tracker(settings=s).upsert_job({"job_id": data["jobs"]["applied"], "company": "Hooli", "override": "manual"})
    assert apps(svc.board(s, idx))[data["jobs"]["applied"]]["override"] == "manual"


def test_filters_narrow_applications_not_the_funnel(idx, data):
    s = data["settings"]
    b = svc.board(s, idx, tier=["A"])
    assert [c["job_id"] for c in b["applications"]] == [data["jobs"]["interview"]]
    assert sum(f["count"] for f in b["funnel"]) == 5
    assert svc.board(s, idx, category=["nope"])["applications"] == []
    opts = svc.board(s, idx)["options"]
    assert opts["categories"] == ["swe_backend"]
    assert [o["value"] for o in opts["locations"]] == ["New York, NY", "Remote"]


def test_empty_board_is_zeros(tmp_path):
    s = Settings.load(make_temp_root(tmp_path / "empty"))
    ix = Index(s)
    ix.rebuild()
    b = svc.board(s, ix)
    assert all(f["count"] == 0 for f in b["funnel"]) and b["submitted"]["count"] == 0
    assert b["applications"] == [] and b["closed"] == {"count": 0, "by_status": {}}
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
