"""Settings rows the mockup shows that had no config key: each new key has a loader check (ConfigError on a bad
value), changes the behaviour it names, and leaves today's behaviour alone at its default.

- pipeline.yaml outreach.mutuals_threshold     careeros.outreach (who is tailored by hand)
- targets.yaml  safety.pause_auto_submit       careeros.safety.scam.auto_submit_allowed (the apply gate)
- pipeline.yaml schedule.missed_runs           careeros.runs.tick (catch-up record or not)
- pipeline.yaml schedule.scout_quiet_hours     careeros.runs.schedule (scout waits out quiet hours or not)
- pipeline.yaml runs.on_usage_limit            careeros.runs.service (stop, or stop and pause runs)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from conftest import make_temp_root
from test_runs_runner import NOW, FakeInvoke, add_job

from careeros.config import ConfigError, Settings
from careeros.models import Posting
from careeros.outreach import LINKEDIN_MUTUALS, OutreachPolicy, check_contacts, needs_manual_outreach
from careeros.runs.config import budget_for, load_runs_config
from careeros.runs.schedule import load_schedule, plan_tick
from careeros.runs.service import run_batch, run_skill
from careeros.runs.store import RunStore
from careeros.runs.tick import load_catch_up, load_state, tick
from careeros.safety.scam import auto_submit_allowed
from careeros.store import Store

pytestmark = pytest.mark.unit

UTC = timezone.utc


# --- outreach.mutuals_threshold ---------------------------------------------------------------------------

def test_mutuals_threshold_defaults_to_one_like_today(example_settings):
    assert OutreachPolicy().mutuals_threshold == 1
    assert OutreachPolicy.from_settings(example_settings).mutuals_threshold == 1
    example_settings.pipeline["outreach"].pop("mutuals_threshold", None)
    assert OutreachPolicy.from_settings(example_settings).mutuals_threshold == 1


@pytest.mark.parametrize("mutuals,manual", [(None, False), (0, False), (1, True), (5, True)])
def test_default_threshold_keeps_any_mutual_manual(mutuals, manual):
    assert needs_manual_outreach({"mutuals": mutuals}, OutreachPolicy())[0] is manual


@pytest.mark.parametrize("mutuals,manual", [(0, False), (1, False), (2, False), (3, True), (12, True)])
def test_threshold_counts_only_people_with_at_least_that_many_mutuals(example_settings, mutuals, manual):
    example_settings.pipeline["outreach"]["mutuals_threshold"] = 3
    policy = OutreachPolicy.from_settings(example_settings)
    assert needs_manual_outreach({"linkedin_degree": 2, "mutuals": mutuals}, policy) == (
        (True, LINKEDIN_MUTUALS) if manual else (False, None))


def test_threshold_never_softens_the_connected_rule(example_settings):
    example_settings.pipeline["outreach"]["mutuals_threshold"] = 50
    rows = check_contacts({"contacts": [{"name": "A", "linkedin_degree": 1, "mutuals": 0},
                                        {"name": "B", "linkedin_degree": 2, "mutuals": 49}]},
                          OutreachPolicy.from_settings(example_settings))
    assert [r["manual"] for r in rows] == [True, False]


@pytest.mark.parametrize("bad", [0, -1, 51, 2.5, "3", True, None])
def test_bad_mutuals_threshold_is_a_config_error(example_settings, bad):
    example_settings.pipeline["outreach"]["mutuals_threshold"] = bad
    with pytest.raises(ConfigError, match="outreach.mutuals_threshold"):
        OutreachPolicy.from_settings(example_settings)


@pytest.mark.parametrize("key", ["manual_if_connected", "manual_if_mutuals"])
def test_outreach_switches_must_be_true_or_false(example_settings, key):
    example_settings.pipeline["outreach"][key] = "no"   # bool("no") is True: silently the opposite
    with pytest.raises(ConfigError, match=f"outreach.{key}"):
        OutreachPolicy.from_settings(example_settings)


# --- safety.pause_auto_submit ------------------------------------------------------------------------------

def _board_posting() -> Posting:
    return Posting(company="Acme", title="Software Engineer", ats="greenhouse",
                   url="https://boards.greenhouse.io/acme/jobs/1", apply_url="https://boards.greenhouse.io/acme/jobs/1")


def test_pause_auto_submit_is_off_in_the_examples_and_changes_nothing(example_settings):
    assert example_settings.targets["safety"]["pause_auto_submit"] is False
    assert auto_submit_allowed(_board_posting(), example_settings) == (True, "")


def test_pause_auto_submit_turns_every_auto_submit_off(example_settings):
    example_settings.targets["safety"]["pause_auto_submit"] = True
    ok, why = auto_submit_allowed(_board_posting(), example_settings)
    assert not ok and "safety.pause_auto_submit" in why


def _root_with(tmp_path: Path, file: str, edit) -> Path:
    root = make_temp_root(tmp_path / "repo")
    p = root / "config" / f"{file}.yaml"
    data = yaml.safe_load(p.read_text())
    edit(data)
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return root


@pytest.mark.parametrize("bad", ["yes", 1, None])
def test_bad_pause_auto_submit_is_a_config_error(tmp_path, bad):
    root = _root_with(tmp_path, "targets", lambda d: d["safety"].update(pause_auto_submit=bad))
    with pytest.raises(ConfigError, match="safety.pause_auto_submit"):
        Settings.load(root)


def test_safety_must_be_a_mapping(tmp_path):
    root = _root_with(tmp_path, "targets", lambda d: d.update(safety=["greenhouse"]))
    with pytest.raises(ConfigError, match="safety must be a mapping"):
        Settings.load(root)


# --- schedule.missed_runs and schedule.scout_quiet_hours ---------------------------------------------------

EVENING = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)
NOON = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _sched(settings, **extra):
    settings.pipeline = {**settings.pipeline, "schedule": {
        "timezone": "UTC", "quiet_hours": {"start": "09:00", "end": "18:00"}, "missed_after_minutes": 60,
        "jobs": {"scout": {"every_hours": 3}, "score": {"every_hours": 6}, "prepare": {"every_hours": 12},
                 "prune": {"every_days": 7}}, **extra}}
    return settings


def _actions(calls):
    def make(kind):
        def act(trigger):
            calls.append((kind, trigger))
            return "ok", kind
        return act
    return {k: make(k) for k in ("scout", "inbox_sync", "score", "prepare", "prune")}


def test_schedule_defaults_match_today(example_settings):
    cfg = load_schedule(example_settings)
    assert cfg.missed_runs == "ask" and cfg.scout_quiet_hours is False
    example_settings.pipeline["schedule"] = {}
    cfg = load_schedule(example_settings)
    assert cfg.missed_runs == "ask" and cfg.scout_quiet_hours is False


@pytest.mark.parametrize("key,bad", [("missed_runs", "run"), ("missed_runs", None), ("missed_runs", True),
                                     ("scout_quiet_hours", "no"), ("scout_quiet_hours", 0)])
def test_bad_schedule_choices_are_config_errors(example_settings, key, bad):
    example_settings.pipeline["schedule"][key] = bad
    with pytest.raises(ConfigError, match=f"schedule.{key}"):
        load_schedule(example_settings)


def test_missed_runs_ask_keeps_one_catch_up(settings):
    s = _sched(settings)
    tick(s, now=EVENING, actions=_actions([]))
    calls: list = []
    tick(s, now=EVENING + timedelta(days=1, hours=2), actions=_actions(calls))
    assert calls == [] and set(load_catch_up(RunStore(s))["kinds"]) == {"scout", "score", "prepare"}


def test_missed_runs_skip_drops_missed_slots_without_a_catch_up(settings):
    s = _sched(settings, missed_runs="skip")
    tick(s, now=EVENING, actions=_actions([]))
    calls: list = []
    later = EVENING + timedelta(days=1, hours=2)
    out = tick(s, now=later, actions=_actions(calls))
    assert calls == []                                     # still never auto-run
    assert "missed" in {d["action"] for d in out["decisions"]}
    assert load_catch_up(RunStore(s)) is None
    jobs = load_state(RunStore(s))["jobs"]
    assert jobs["score"]["last_status"] == "missed" and jobs["score"]["last_run"] == later.isoformat()
    # the next regular slot runs as usual
    calls2: list = []
    tick(s, now=later + timedelta(hours=6, minutes=1), actions=_actions(calls2))
    assert ("score", "schedule") in calls2


def test_missed_runs_skip_leaves_an_existing_catch_up_alone(settings):
    s = _sched(settings)
    tick(s, now=EVENING, actions=_actions([]))
    tick(s, now=EVENING + timedelta(days=1, hours=2), actions=_actions([]))
    before = load_catch_up(RunStore(s))
    s.pipeline["schedule"]["missed_runs"] = "skip"
    tick(s, now=EVENING + timedelta(days=3), actions=_actions([]))
    assert load_catch_up(RunStore(s)) == before           # dismiss it with `careeros run catch-up --dismiss`


def test_scout_ignores_quiet_hours_by_default():
    s = _sched(Settings(root=Path("/nonexistent")))
    d = {x.kind: x.action for x in plan_tick(load_schedule(s), {}, NOON, paused=False)}
    assert d["scout"] == "run" and d["score"] == "wait_quiet" and d["prune"] == "run"


def test_scout_quiet_hours_on_makes_scout_wait_like_claude_runs():
    s = _sched(Settings(root=Path("/nonexistent")), scout_quiet_hours=True)
    d = {x.kind: x for x in plan_tick(load_schedule(s), {}, NOON, paused=False)}
    assert d["scout"].action == "wait_quiet" and d["prune"].action == "run"
    after = {x.kind: x.action for x in plan_tick(load_schedule(s), {}, NOON.replace(hour=18, minute=5),
                                                  paused=False)}
    assert after["scout"] == "run"


# --- runs.on_usage_limit -----------------------------------------------------------------------------------

def _batch(settings, invoke, **runs):
    settings.pipeline = {**settings.pipeline, "runs": {**(settings.pipeline.get("runs") or {}),
                                                       "preflight_doctor": False, **runs}}
    cfg = load_runs_config(settings)
    return run_batch(settings, "score", budget_for(cfg, "score"), cfg=cfg, invoke=invoke, now=lambda: NOW)


def test_on_usage_limit_defaults_to_stop(example_settings):
    assert load_runs_config(example_settings).on_usage_limit == "stop"
    example_settings.pipeline["runs"].pop("on_usage_limit", None)
    assert load_runs_config(example_settings).on_usage_limit == "stop"


@pytest.mark.parametrize("bad", ["wait", None, True, 1])
def test_bad_on_usage_limit_is_a_config_error(example_settings, bad):
    example_settings.pipeline["runs"]["on_usage_limit"] = bad
    with pytest.raises(ConfigError, match="runs.on_usage_limit"):
        load_runs_config(example_settings)


def test_usage_limit_stop_leaves_runs_unpaused(settings):
    jid = add_job(Store(settings), 1, hours_old=60)
    rec = _batch(settings, FakeInvoke(settings, modes={jid: "usage_limit"}))
    assert rec["stop_reason"] == "usage_limit" and RunStore(settings).pause_state(NOW) is None


def test_usage_limit_pause_pauses_runs_until_resumed(settings):
    jid = add_job(Store(settings), 1, hours_old=60)
    rec = _batch(settings, FakeInvoke(settings, modes={jid: "usage_limit"}), on_usage_limit="pause")
    assert rec["stop_reason"] == "usage_limit"
    pause = RunStore(settings).pause_state(NOW + timedelta(days=30))
    assert pause and pause["until"] is None and "usage limit" in pause["reason"]
    assert "paused" in RunStore(settings).read_log(rec["id"])


def test_other_stops_never_pause(settings):
    jid = add_job(Store(settings), 1, hours_old=60)
    _batch(settings, FakeInvoke(settings, modes={jid: "auth"}), on_usage_limit="pause")
    assert RunStore(settings).pause_state(NOW) is None


def test_dry_run_never_pauses(settings):
    add_job(Store(settings), 1, hours_old=60)
    settings.pipeline = {**settings.pipeline, "runs": {**settings.pipeline["runs"], "preflight_doctor": False,
                                                       "on_usage_limit": "pause"}}
    cfg = load_runs_config(settings)
    run_batch(settings, "score", budget_for(cfg, "score"), cfg=cfg, dry_run=True, now=lambda: NOW)
    assert RunStore(settings).pause_state(NOW) is None


def test_inbox_sync_usage_limit_pauses_too(settings):
    from careeros.runs.headless import parse_stream
    import json

    def invoke(cmd, cwd, env, timeout_s, stream_path):
        Path(stream_path).write_text("{}")
        r = parse_stream([json.dumps({"type": "result", "is_error": True, "result": "You've hit your limit"})])
        r.exit_code = 1
        return r

    settings.pipeline = {**settings.pipeline, "runs": {**settings.pipeline["runs"], "preflight_doctor": False,
                                                       "on_usage_limit": "pause"}}
    rec = run_skill(settings, "inbox_sync", "inbox-sync", invoke=invoke, now=lambda: NOW)
    assert rec["stop_reason"] == "usage_limit" and RunStore(settings).pause_state(NOW) is not None


def _pause_seen_at_runner_release(settings, monkeypatch):
    """Record, at each release of the runner lock, whether pause.json was already set (no gap for another run)."""
    from careeros.runs import locks
    seen: list[bool] = []
    real = locks.release

    def release(path, token, force=False):
        if Path(path) == RunStore(settings).runner_lock_path:
            seen.append(RunStore(settings).pause_state(NOW) is not None)
        return real(path, token, force)

    monkeypatch.setattr(locks, "release", release)
    return seen


def test_batch_usage_limit_pause_is_set_before_the_runner_lock_is_released(settings, monkeypatch):
    jid = add_job(Store(settings), 1, hours_old=60)
    seen = _pause_seen_at_runner_release(settings, monkeypatch)
    _batch(settings, FakeInvoke(settings, modes={jid: "usage_limit"}), on_usage_limit="pause")
    assert seen == [True]


def test_skill_usage_limit_pause_is_set_before_the_runner_lock_is_released(settings, monkeypatch):
    from careeros.runs.headless import parse_stream
    import json

    def invoke(cmd, cwd, env, timeout_s, stream_path):
        Path(stream_path).write_text("{}")
        r = parse_stream([json.dumps({"type": "result", "is_error": True, "result": "You've hit your limit"})])
        r.exit_code = 1
        return r

    settings.pipeline = {**settings.pipeline, "runs": {**settings.pipeline["runs"], "preflight_doctor": False,
                                                       "on_usage_limit": "pause"}}
    seen = _pause_seen_at_runner_release(settings, monkeypatch)
    run_skill(settings, "inbox_sync", "inbox-sync", invoke=invoke, now=lambda: NOW)
    assert seen == [True]
