"""job_actions.set_status over the fictional UI data."""
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
