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


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_last_tick_is_stamped_at_the_end_so_a_long_run_is_not_sleep(s):
    t0 = EVENING
    st = {"last_tick": (t0 - timedelta(minutes=15)).isoformat(),
          "jobs": {"prepare": {"last_run": (t0 - timedelta(hours=11)).isoformat()},
                   "scout": {"last_run": t0.isoformat()}, "prune": {"last_run": t0.isoformat()}}}
    from careeros.runs.tick import _write
    _write(RunStore(s).dir / "schedule.json", st)
    clock = Clock(t0)
    a = Actions()
    real_score = a["score"]

    def slow_score(trigger):
        clock.t += timedelta(hours=3)
        return real_score(trigger)

    a["score"] = slow_score
    tick(s, clock=clock, actions=a)
    assert load_state(RunStore(s))["last_tick"] == (t0 + timedelta(hours=3)).isoformat()
    b = Actions()
    out = tick(s, now=t0 + timedelta(hours=3, minutes=5), actions=b)
    assert {d["kind"]: d["action"] for d in out["decisions"]}["prepare"] == "run"
    assert ("prepare", "schedule") in b.calls


def _at_noon(s):
    s.pipeline["schedule"]["jobs"]["score"] = {"at": ["12:00"]}


def test_first_time_of_day_slot_held_by_quiet_hours_runs_when_they_end(s):
    _at_noon(s)
    day = datetime(2026, 9, 26, tzinfo=UTC)
    tick(s, now=day.replace(hour=11), actions=Actions())
    a = Actions()
    tick(s, now=day.replace(hour=12, minute=5), actions=a)
    assert ("score", "schedule") not in a.calls  # quiet hours
    for h in (13, 15, 17):
        tick(s, now=day.replace(hour=h, minute=30), actions=Actions())
    b = Actions()
    tick(s, now=day.replace(hour=18, minute=5), actions=b)
    assert ("score", "schedule") in b.calls


def test_first_time_of_day_slot_that_found_the_runner_busy_runs_next_tick(s):
    s.pipeline["schedule"]["quiet_hours"] = None
    _at_noon(s)
    day = datetime(2026, 9, 26, tzinfo=UTC)
    tick(s, now=day.replace(hour=11), actions=Actions())
    tick(s, now=day.replace(hour=12, minute=5), actions=Actions(busy=("score",)))
    a = Actions()
    tick(s, now=day.replace(hour=12, minute=20), actions=a)
    assert ("score", "schedule") in a.calls


def test_catch_up_is_busy_while_a_tick_holds_the_lock(s):
    tick(s, now=EVENING, actions=Actions())
    tick(s, now=EVENING + timedelta(days=1, hours=2), actions=Actions())
    locks.acquire(RunStore(s).dir / "tick.lock", owner="tick", ttl_seconds=600, now=EVENING + timedelta(days=1, hours=3))
    a = Actions()
    res = run_catch_up(s, actions=a, now=EVENING + timedelta(days=1, hours=3))
    assert res["status"] == "busy" and a.calls == []
    assert load_catch_up(RunStore(s)) is not None


def test_a_kind_missed_during_catch_up_survives(s):
    tick(s, now=EVENING, actions=Actions())
    tick(s, now=EVENING + timedelta(days=1, hours=2), actions=Actions())
    rs = RunStore(s)
    a = Actions()
    real = a["scout"]

    def scout_and_new_miss(trigger):
        rec = load_catch_up(rs)
        rec["kinds"]["prune"] = {"first_missed": "x", "slots": 1}
        from careeros.runs.tick import _save_catch_up
        _save_catch_up(rs, rec)
        return real(trigger)

    a["scout"] = scout_and_new_miss
    run_catch_up(s, actions=a, now=EVENING + timedelta(days=1, hours=3))
    assert set(load_catch_up(rs)["kinds"]) == {"prune"}
