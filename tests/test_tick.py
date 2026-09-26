"""`careeros tick` executor and catch-up, with fake actions (no scout HTTP, no claude)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from careeros.runs import locks
from careeros.runs.runner import RunBusy
from careeros.runs.store import RunStore
from careeros.runs.tick import load_catch_up, load_state, run_catch_up, tick

pytestmark = pytest.mark.unit

UTC = timezone.utc
EVENING = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)


@pytest.fixture
def s(settings):
    settings.pipeline = {**settings.pipeline, "schedule": {
        "timezone": "UTC", "quiet_hours": {"start": "09:00", "end": "18:00"}, "missed_after_minutes": 60,
        "jobs": {"scout": {"every_hours": 3}, "score": {"every_hours": 6}, "prepare": {"every_hours": 12},
                 "prune": {"every_days": 7}}}}
    return settings


class Actions(dict):
    def __init__(self, busy=()):
        super().__init__()
        self.calls = []
        for k in ("scout", "inbox_sync", "score", "prepare", "prune"):
            self[k] = self._make(k, k in busy)

    def _make(self, kind, busy):
        def act(trigger):
            self.calls.append((kind, trigger))
            if busy:
                raise RunBusy({"owner": "run:x"})
            return "ok", f"{kind} done"
        return act


def test_tick_runs_due_jobs_in_order_and_records_state(s):
    a = Actions()
    out = tick(s, now=EVENING, actions=a)
    assert [c[0] for c in a.calls] == ["scout", "score", "prepare", "prune"]
    assert all(t == "schedule" for _, t in a.calls)
    st = load_state(RunStore(s))
    assert st["last_tick"] == EVENING.isoformat()
    assert st["jobs"]["score"]["last_run"] == EVENING.isoformat() and st["jobs"]["score"]["last_status"] == "ok"
    assert {d["kind"]: d["action"] for d in out["decisions"]}["scout"] == "run"


def test_second_tick_is_idempotent(s):
    tick(s, now=EVENING, actions=Actions())
    a = Actions()
    tick(s, now=EVENING + timedelta(minutes=15), actions=a)
    assert a.calls == []


def test_busy_runner_leaves_the_job_due(s):
    tick(s, now=EVENING, actions=Actions(busy=("score",)))
    st = load_state(RunStore(s))
    assert "last_run" not in st["jobs"].get("score", {}) or st["jobs"]["score"].get("last_status") == "busy"
    a = Actions()
    tick(s, now=EVENING + timedelta(minutes=15), actions=a)
    assert ("score", "schedule") in a.calls


def test_quiet_hours_hold_claude_runs(s):
    a = Actions()
    tick(s, now=datetime(2026, 9, 26, 11, tzinfo=UTC), actions=a)
    assert [c[0] for c in a.calls] == ["scout", "prune"]


def test_dry_run_changes_nothing(s):
    a = Actions()
    out = tick(s, now=EVENING, actions=a, dry_run=True)
    assert a.calls == [] and out["dry_run"] and load_state(RunStore(s))["last_tick"] is None


def test_tick_lock_makes_a_concurrent_tick_a_no_op(s):
    locks.acquire(RunStore(s).dir / "tick.lock", owner="tick", ttl_seconds=600, pid=None, now=EVENING)
    a = Actions()
    out = tick(s, now=EVENING, actions=a)
    assert out["status"] == "busy" and a.calls == []


def test_paused_tick_skips_and_advances(s):
    RunStore(s).set_pause(until=None, reason="vacation", now=EVENING)
    a = Actions()
    tick(s, now=EVENING, actions=a)
    assert a.calls == []
    assert load_state(RunStore(s))["jobs"]["scout"]["last_status"] == "paused"


def test_missed_slots_become_one_catch_up_then_run_on_request(s):
    tick(s, now=EVENING, actions=Actions())
    a = Actions()
    later = EVENING + timedelta(days=1, hours=2)  # asleep for a day
    tick(s, now=later, actions=a)
    assert a.calls == []  # nothing auto-runs
    rec = load_catch_up(RunStore(s))
    assert set(rec["kinds"]) == {"scout", "score", "prepare"}
    tick(s, now=later + timedelta(minutes=15), actions=a)
    assert a.calls == [] and load_catch_up(RunStore(s))["created_at"] == rec["created_at"]

    b = Actions()
    res = run_catch_up(s, actions=b, now=later + timedelta(minutes=20))
    assert [c for c in b.calls] == [("scout", "catch_up"), ("score", "catch_up"), ("prepare", "catch_up")]
    assert res["ran"] == ["scout", "score", "prepare"] and load_catch_up(RunStore(s)) is None


def test_catch_up_keeps_kinds_that_were_busy(s):
    tick(s, now=EVENING, actions=Actions())
    tick(s, now=EVENING + timedelta(days=1, hours=2), actions=Actions())
    res = run_catch_up(s, actions=Actions(busy=("score",)), now=EVENING + timedelta(days=1, hours=3))
    assert "score" in res["left"] and set(load_catch_up(RunStore(s))["kinds"]) == {"score"}


def test_catch_up_refuses_while_paused_and_dismiss_clears(s):
    tick(s, now=EVENING, actions=Actions())
    tick(s, now=EVENING + timedelta(days=1, hours=2), actions=Actions())
    RunStore(s).set_pause(until=None, reason="x", now=EVENING)
    with pytest.raises(RuntimeError, match="paused"):
        run_catch_up(s, actions=Actions(), now=EVENING + timedelta(days=1, hours=3))
    assert run_catch_up(s, actions=Actions(), now=EVENING, dismiss=True)["dismissed"]
    assert load_catch_up(RunStore(s)) is None


def test_enabled_inbox_sync_runs_in_order_at_its_slot(s):
    s.pipeline["schedule"]["jobs"]["inbox_sync"] = {"enabled": True}  # default times 08:00 and 18:00
    tick(s, now=datetime(2026, 9, 26, 7, 50, tzinfo=UTC), actions=Actions())
    a = Actions()
    tick(s, now=datetime(2026, 9, 26, 8, 5, tzinfo=UTC), actions=a)
    assert ("inbox_sync", "schedule") in a.calls
