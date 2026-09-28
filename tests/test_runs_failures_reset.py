"""`careeros run reset-failures`: clear a job's failure count and resolve the out-of-retries Action Item."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from careeros.runs.failures import Failures
from careeros.runs.store import RunStore

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def test_status_reports_count_last_outcome_and_exclusion(settings):
    f = Failures(RunStore(settings))
    assert f.status("apply", "j1", 2) is None
    f.record("apply", "j1", "timeout", "slow", "r1", NOW)
    s = f.status("apply", "j1", 2)
    assert s == {"kind": "apply", "count": 1, "max_attempts": 2, "last_outcome": "timeout", "last_detail": "slow",
                 "last_run": "r1", "excluded": False}
    f.record("apply", "j1", "invalid_result", "bad", "r2", NOW)
    assert f.status("apply", "j1", 2)["excluded"] is True


def test_reset_clears_the_count_and_resolves_only_the_matching_action_item(settings):
    from careeros.runs.service import reset_failures
    from careeros.tracker import Tracker, add_action

    f = Failures(RunStore(settings))
    f.record("apply", "j1", "invalid_result", "bad", "r1", NOW)
    f.record("apply", "j1", "invalid_result", "bad", "r2", NOW)
    f.record("prepare", "j1", "timeout", "slow", "r3", NOW)
    add_action(settings, "careeros run: /apply-job failed 2 times on job j1 (invalid_result: bad). Run it by hand",
               "other", job_id="j1")
    add_action(settings, "careeros run: /apply-job failed 2 times on job j2 (x). Run it by hand", "other", job_id="j2")
    add_action(settings, "Follow up with the recruiter", "other", job_id="j1")
    out = reset_failures(settings, "apply", "j1")
    assert out["cleared"] is True and len(out["resolved"]) == 1
    assert f.get("apply", "j1") is None and f.get("prepare", "j1") is not None
    left = {(i["JobID"], i["What to do"][:20]) for i in Tracker(settings=settings).list_action_items(open_only=True)}
    assert left == {("j2", "careeros run: /apply"), ("j1", "Follow up with the r")}
    assert reset_failures(settings, "apply", "j1") == {"kind": "apply", "job_id": "j1", "cleared": False,
                                                       "resolved": []}


def test_reset_rejects_an_unknown_kind(settings):
    from careeros.runs.service import reset_failures

    with pytest.raises(ValueError):
        reset_failures(settings, "nope", "j1")
