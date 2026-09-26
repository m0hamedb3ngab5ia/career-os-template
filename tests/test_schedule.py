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
    return {d.kind: d.action for d in decisions if d.kind != "inbox_sync"}


# --- config -----------------------------------------------------------------------------------------------

def test_defaults_and_example_agree():
    ex = load_schedule(S(yaml.safe_load((EXAMPLE_REPO / "config" / "pipeline.yaml").read_text())["schedule"]))
    d = load_schedule(S())
    assert ex.tick_minutes == d.tick_minutes == 15
    assert (ex.quiet_start, ex.quiet_end) == (d.quiet_start, d.quiet_end) == (time(9), time(18))
    assert ex.missed_after_minutes == d.missed_after_minutes == 60
    assert {k: (j.every_minutes, j.at, j.enabled, j.mcp_servers) for k, j in ex.jobs.items()} == \
        {k: (j.every_minutes, j.at, j.enabled, j.mcp_servers) for k, j in d.jobs.items()}
    assert d.jobs["scout"].every_minutes == 180 and d.jobs["prune"].every_minutes == 7 * 24 * 60
    assert d.jobs["score"].at == [time(1)] and d.jobs["prepare"].at == [time(2)]
    assert d.jobs["inbox_sync"].at == [time(8), time(18)] and d.jobs["inbox_sync"].enabled is False
    assert d.jobs["inbox_sync"].mcp_servers == ["gmail"]


def test_old_cron_strings_fail_with_a_migration_hint():
    with pytest.raises(ConfigError, match="schedule.jobs"):
        load_schedule(S({"scout": "0 7 * * *", "prune": "0 3 * * 0"}))


@pytest.mark.parametrize("bad", [
    {"tick_minutes": 0}, {"quiet_hours": {"start": "9am", "end": "18:00"}}, {"quiet_hours": "09-18"},
    {"missed_after_minutes": -5}, {"jobs": {"scout": {"every_hours": 3, "every_days": 1}}},
    {"jobs": {"scout": []}}, {"jobs": {"email": {"every_hours": 1}}}, {"jobs": {"scout": {"preset": "medium"}}},
    {"jobs": {"score": {"every_hours": 6, "preset": "huge"}}}, {"jobs": {"score": {"enabled": "yes"}}},
    {"timezone": "Mars/Olympus"}, {"bogus": 1},
    {"jobs": {"score": {"at": ["1am"]}}}, {"jobs": {"score": {"at": ["01:00"], "every_hours": 6}}},
    {"jobs": {"score": {"at": []}}}, {"jobs": {"scout": {"every_hours": 3, "mcp_servers": ["gmail"]}}},
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
    assert [x.kind for x in d] == ["scout", "inbox_sync", "score", "prepare", "prune"]
    assert {x.kind: x.action for x in d}["inbox_sync"] == "disabled"


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



# --- time-of-day jobs (score 01:00, prepare 02:00 nightly; inbox_sync 08:00 + 18:00) ------------------------

def nightly(**extra):
    return cfg(score={"at": ["01:00"]}, prepare={"at": ["02:00"]}, **extra)


def test_first_tick_does_not_fire_a_time_of_day_job():
    d = {x.kind: x for x in plan_tick(nightly(), state(), at(15), paused=False)}
    assert d["score"].action == "not_due" and d["score"].due_at == at(1, day=27)


def test_nightly_slot_runs_once_after_its_time():
    s = state(at(0, 50, day=27), score=at(1), prepare=at(2))  # ran last night
    assert acts(plan_tick(nightly(), s, at(0, 55, day=27), paused=False))["score"] == "not_due"
    d = acts(plan_tick(nightly(), s, at(1, 5, day=27), paused=False))
    assert d["score"] == "run" and d["prepare"] == "not_due"
    s2 = state(at(1, 5, day=27), score=at(1, 5, day=27), prepare=at(2))
    assert acts(plan_tick(nightly(), s2, at(1, 20, day=27), paused=False))["score"] == "not_due"


def test_nightly_slot_uses_last_tick_as_reference_before_the_first_run():
    s = state(at(23, 50))  # installed yesterday evening, never ran
    assert acts(plan_tick(nightly(), s, at(1, 5, day=27), paused=False))["score"] == "run"


def test_nightly_slot_missed_while_asleep_goes_to_catch_up():
    s = state(at(23), score=at(1), prepare=at(2))
    d = {x.kind: x for x in plan_tick(nightly(), s, at(7, day=27), paused=False)}
    assert d["score"].action == "missed" and d["score"].slots == 1 and d["prepare"].action == "missed"


def test_time_of_day_slot_inside_quiet_hours_waits_for_their_end():
    c = cfg(score={"at": ["10:00"]})
    s = state(at(9, 50), score=at(10, day=25))
    d = {x.kind: x for x in plan_tick(c, s, at(10, 5), paused=False)}
    assert d["score"].action == "wait_quiet" and d["score"].due_at == at(18)


def test_next_runs_for_time_of_day_jobs():
    s = state(at(8), scout=at(8), score=at(1), prepare=at(2), prune=at(8))
    nxt = next_runs(nightly(), s, at(8))
    assert nxt["score"] == at(1, day=27) and nxt["prepare"] == at(2, day=27)
    assert nxt["inbox_sync"] is None  # disabled by default


def test_inbox_sync_when_enabled_runs_at_8_and_18():
    c = cfg(inbox_sync={"at": ["08:00", "18:00"], "enabled": True})
    s = state(at(7, 50), inbox_sync=at(18, day=25))
    assert acts_all(plan_tick(c, s, at(8, 5), paused=False))["inbox_sync"] == "run"
    s2 = state(at(8, 20), inbox_sync=at(8, 5))
    assert acts_all(plan_tick(c, s2, at(8, 35), paused=False))["inbox_sync"] == "not_due"
    assert next_runs(c, s2, at(8, 35))["inbox_sync"] == at(18)


def acts_all(decisions):
    return {d.kind: d.action for d in decisions}


def test_a_partial_job_block_keeps_the_default_timing():
    c = load_schedule(S({"jobs": {"inbox_sync": {"enabled": True}, "scout": {}}}))
    assert c.jobs["inbox_sync"].enabled and c.jobs["inbox_sync"].at == [time(8), time(18)]
    assert c.jobs["inbox_sync"].mcp_servers == ["gmail"] and c.jobs["scout"].every_minutes == 180
