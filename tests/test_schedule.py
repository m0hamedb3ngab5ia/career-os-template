"""Schedule config and the pure tick planner: intervals, quiet hours, missed slots -> one catch-up, pause."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest
import yaml
from conftest import EXAMPLE_REPO

from careeros.config import ConfigError
from careeros.runs.schedule import (
    in_quiet,
    load_schedule,
    merge_catch_up,
    next_runs,
    plan_tick,
    quiet_end_after,
)

pytestmark = pytest.mark.unit

UTC = timezone.utc


class S:
    def __init__(self, schedule=None, runs=None):
        self.pipeline = {"schedule": schedule} if schedule is not None else {}
        if runs:
            self.pipeline["runs"] = runs


def at(h, m=0, day=26):
    return datetime(2026, 9, day, h, m, tzinfo=UTC)


def cfg(**jobs):
    base = {"tick_minutes": 15, "timezone": "UTC", "quiet_hours": {"start": "09:00", "end": "18:00"},
            "missed_after_minutes": 60, "jobs": {"scout": {"every_hours": 3}, "score": {"every_hours": 6},
                                                  "prepare": {"every_hours": 12}, "prune": {"every_days": 7}}}
    base["jobs"].update(jobs)
    return load_schedule(S(base))


def state(last_tick=None, **last_runs):
    return {"last_tick": last_tick.isoformat() if last_tick else None,
            "jobs": {k: {"last_run": v.isoformat()} for k, v in last_runs.items()}}


def acts(decisions):
    return {d.kind: d.action for d in decisions}


# --- config -----------------------------------------------------------------------------------------------

def test_defaults_and_example_agree():
    ex = load_schedule(S(yaml.safe_load((EXAMPLE_REPO / "config" / "pipeline.yaml").read_text())["schedule"]))
    d = load_schedule(S())
    assert ex.tick_minutes == d.tick_minutes == 15
    assert (ex.quiet_start, ex.quiet_end) == (d.quiet_start, d.quiet_end) == (time(9), time(18))
    assert ex.missed_after_minutes == d.missed_after_minutes == 60
    assert {k: (j.every_minutes, j.enabled) for k, j in ex.jobs.items()} == \
        {k: (j.every_minutes, j.enabled) for k, j in d.jobs.items()}
    assert d.jobs["scout"].every_minutes == 180 and d.jobs["prune"].every_minutes == 7 * 24 * 60


def test_old_cron_strings_fail_with_a_migration_hint():
    with pytest.raises(ConfigError, match="schedule.jobs"):
        load_schedule(S({"scout": "0 7 * * *", "prune": "0 3 * * 0"}))


@pytest.mark.parametrize("bad", [
    {"tick_minutes": 0}, {"quiet_hours": {"start": "9am", "end": "18:00"}}, {"quiet_hours": "09-18"},
    {"missed_after_minutes": -5}, {"jobs": {"scout": {"every_hours": 3, "every_days": 1}}},
    {"jobs": {"scout": {}}}, {"jobs": {"email": {"every_hours": 1}}}, {"jobs": {"scout": {"preset": "medium"}}},
    {"jobs": {"score": {"every_hours": 6, "preset": "huge"}}}, {"jobs": {"score": {"enabled": "yes"}}},
    {"timezone": "Mars/Olympus"}, {"bogus": 1},
])
def test_bad_schedule_config_fails_closed(bad):
    with pytest.raises(ConfigError):
        load_schedule(S(bad))


def test_quiet_hours_null_turns_them_off():
    c = load_schedule(S({"quiet_hours": None}))
    assert c.quiet_start is None


# --- quiet hours ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("t,want", [(time(8, 59), False), (time(9), True), (time(17, 59), True), (time(18), False)])
def test_in_quiet_daytime(t, want):
    assert in_quiet(t, time(9), time(18)) is want


@pytest.mark.parametrize("t,want", [(time(23), True), (time(3), True), (time(7), False), (time(12), False)])
def test_in_quiet_wraps_midnight(t, want):
    assert in_quiet(t, time(22), time(6)) is want


def test_quiet_end_after():
    assert quiet_end_after(at(10), time(9), time(18)) == at(18)
    assert quiet_end_after(at(20), time(9), time(18)) == at(20)
    assert quiet_end_after(datetime(2026, 9, 26, 23, tzinfo=UTC), time(22), time(6)) == at(6, day=27)


# --- planning ---------------------------------------------------------------------------------------------

def test_first_tick_runs_everything_outside_quiet_hours():
    d = plan_tick(cfg(), state(), at(20), paused=False)
    assert acts(d) == {"scout": "run", "score": "run", "prepare": "run", "prune": "run"}
    assert [x.kind for x in d] == ["scout", "score", "prepare", "prune"]


def test_claude_runs_wait_in_quiet_hours_but_scout_does_not():
    d = plan_tick(cfg(), state(), at(11), paused=False)
    assert acts(d) == {"scout": "run", "score": "wait_quiet", "prepare": "wait_quiet", "prune": "run"}


def test_not_due_until_the_interval_passes():
    s = state(at(19, 50), scout=at(18), score=at(18), prepare=at(18), prune=at(18))
    d = plan_tick(cfg(), s, at(20), paused=False)
    assert acts(d) == {"scout": "not_due", "score": "not_due", "prepare": "not_due", "prune": "not_due"}
    assert acts(plan_tick(cfg(), s, at(21, 5), paused=False))["scout"] == "run"


def test_slot_deferred_by_quiet_hours_runs_when_they_end_not_missed():
    s = state(at(17, 50), score=at(4))  # score due at 10:00, inside quiet hours -> effective 18:00
    d = {x.kind: x for x in plan_tick(cfg(), s, at(18, 5), paused=False)}
    assert d["score"].action == "run"


def test_sleep_gap_collapses_missed_slots_into_catch_up():
    s = state(at(2), scout=at(2), score=at(0), prepare=at(0), prune=at(1))
    d = {x.kind: x for x in plan_tick(cfg(), s, at(22), paused=False)}  # Mac asleep 02:00 -> 22:00
    assert d["scout"].action == "missed" and d["score"].action == "missed"
    assert d["scout"].slots == 6  # due 05, 08, 11, 14, 17, 20
    assert d["prune"].action == "not_due"


def test_regular_ticks_never_mark_missed_even_when_late():
    s = state(at(21, 50), scout=at(2))  # ticks ran, scout was simply overdue (e.g. runner busy)
    d = {x.kind: x for x in plan_tick(cfg(), s, at(22), paused=False)}
    assert d["scout"].action == "run"


def test_paused_skips_due_slots():
    d = plan_tick(cfg(), state(), at(20), paused=True)
    assert set(acts(d).values()) == {"skip_paused"}


def test_disabled_jobs():
    d = plan_tick(cfg(prepare={"every_hours": 12, "enabled": False}), state(), at(20), paused=False)
    assert acts(d)["prepare"] == "disabled"


def test_merge_catch_up_keeps_one_record():
    s = state(at(2), scout=at(2), score=at(0))
    d1 = plan_tick(cfg(), s, at(22), paused=False)
    rec = merge_catch_up(None, d1, at(22))
    rec2 = merge_catch_up(rec, [x for x in d1 if x.kind == "scout"], at(23))
    assert set(rec2["kinds"]) >= {"scout", "score"}
    assert rec2["kinds"]["scout"]["slots"] == 2 * rec["kinds"]["scout"]["slots"]
    assert rec2["created_at"] == rec["created_at"]


def test_next_runs_push_claude_jobs_past_quiet_hours():
    s = state(at(8), scout=at(8), score=at(4), prepare=at(4), prune=at(8))
    nxt = next_runs(cfg(), s, at(8))
    assert nxt["scout"] == at(11)
    assert nxt["score"] == at(18)  # due 10:00, quiet until 18:00
    assert nxt["prune"] == at(8, day=26) + timedelta(days=7)
