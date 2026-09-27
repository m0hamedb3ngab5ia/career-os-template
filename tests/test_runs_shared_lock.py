"""The shared pipeline lock (data/runs/runner.lock): scout, prune, batches and UI steps never overlap."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from careeros.runs import locks
from careeros.runs.config import load_runs_config
from careeros.runs.runner import RunBusy
from careeros.runs.store import RunStore

pytestmark = pytest.mark.unit

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "config" / "pipeline.yaml"


class Clock:
    """Fake monotonic clock + sleep: sleeping advances the clock, never blocks."""

    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def hold_batch(settings, rid="r1", pid=None):
    return locks.acquire(RunStore(settings).runner_lock_path, owner=f"run:{rid}", ttl_seconds=3600,
                         pid=pid or os.getpid(), note="score (manual)")


def with_runs(settings, **runs):
    settings.pipeline = {**settings.pipeline, "runs": {**(settings.pipeline.get("runs") or {}), **runs}}
    return settings


# --- config ---------------------------------------------------------------------------------------------------

def test_config_defaults_match_examples(settings):
    cfg = load_runs_config(settings)
    ex = yaml.safe_load(EXAMPLES.read_text())["runs"]
    assert cfg.scout_waits_for_batch is True and ex["scout_waits_for_batch"] is True
    assert cfg.lock_wait_s == 300 and ex["lock_wait_s"] == 300
    assert "(Recommended)" in [ln for ln in EXAMPLES.read_text().splitlines() if ln.strip().startswith("scout_waits_for_batch:")][0]
    assert "(Recommended)" in [ln for ln in EXAMPLES.read_text().splitlines() if ln.strip().startswith("lock_wait_s:")][0]


def test_config_validates(settings):
    with pytest.raises(ValueError):
        load_runs_config(with_runs(settings, lock_wait_s=-1))
    assert load_runs_config(with_runs(settings, scout_waits_for_batch=False, lock_wait_s=5)).lock_wait_s == 5


def test_wait_seconds_follow_the_switch(settings):
    assert locks.pipeline_wait_s(settings) == 300
    assert locks.pipeline_wait_s(with_runs(settings, scout_waits_for_batch=False)) == 0


# --- the helper -----------------------------------------------------------------------------------------------

def test_prune_while_a_batch_holds_the_lock_waits_then_refuses(settings):
    hold_batch(settings)
    c = Clock()
    with pytest.raises(locks.PipelineBusy) as e:
        with locks.pipeline_lock(settings, "cli:prune", note="prune", wait_s=3, poll_s=1, sleep=c.sleep, clock=c):
            pytest.fail("must not run")
    assert sum(c.sleeps) == pytest.approx(3) and len(c.sleeps) == 3
    msg = str(e.value)
    assert "run:r1" in msg and "waited 3s" in msg and "try again" in msg


def test_switch_off_refuses_at_once(settings):
    hold_batch(with_runs(settings, scout_waits_for_batch=False))
    c = Clock()
    with pytest.raises(locks.PipelineBusy):
        with locks.pipeline_lock(settings, "cli:scout", note="scout", sleep=c.sleep, clock=c):
            pass
    assert c.sleeps == []


def test_waiter_gets_the_lock_once_the_batch_ends(settings):
    rs = RunStore(settings)
    lk = hold_batch(settings)
    c = Clock()

    def sleep(s):
        c.sleep(s)
        locks.release(rs.runner_lock_path, lk.token)

    with locks.pipeline_lock(settings, "cli:prune", note="prune", wait_s=10, sleep=sleep, clock=c) as got:
        assert locks.read(rs.runner_lock_path)["owner"] == "cli:prune"
        assert got.info["pid"] == os.getpid() and got.info["note"] == "prune"
    assert locks.read(rs.runner_lock_path) is None


def test_batch_while_scout_holds_the_lock_is_run_busy(settings):
    from careeros.runs.config import budget_for
    from careeros.runs.runner import execute_run

    cfg = load_runs_config(settings)
    with locks.pipeline_lock(settings, "cli:scout", note="scout", wait_s=0):
        with pytest.raises(RunBusy) as e:
            execute_run(settings, "score", budget_for(cfg, "score"), cfg=cfg, invoke=lambda *a: None)
    assert "cli:scout" in str(e.value)
    assert RunStore(settings).list_runs() == []


def test_stale_lock_of_a_dead_pid_is_taken_over(settings):
    rs = RunStore(settings)
    locks.acquire(rs.runner_lock_path, owner="run:dead", ttl_seconds=3600, pid=999_999)
    with locks.pipeline_lock(settings, "cli:prune", note="prune", wait_s=0, pid_alive=lambda p: False) as lk:
        assert lk.stale_taken and locks.read(rs.runner_lock_path)["owner"] == "cli:prune"


def test_nested_use_is_reentrant_and_the_outer_holder_keeps_it(settings):
    rs = RunStore(settings)
    with locks.pipeline_lock(settings, "step:s1", note="scout", wait_s=0) as outer:
        with locks.pipeline_lock(settings, "tick:scout", note="scout", wait_s=0) as inner:
            assert inner.reentrant
        assert locks.read(rs.runner_lock_path)["token"] == outer.token
    assert locks.read(rs.runner_lock_path) is None


# --- tick -----------------------------------------------------------------------------------------------------

def test_tick_scout_during_a_batch_is_busy_and_stays_due(settings, monkeypatch):
    from careeros.runs import tick

    ran = []
    monkeypatch.setattr("careeros.scout.run_scout", lambda *a, **k: ran.append(1))
    hold_batch(with_runs(settings, scout_waits_for_batch=False))
    status, detail = tick._run_one(tick.default_actions(settings)["scout"], "schedule")
    assert status == "busy" and "run:r1" in detail and ran == []


def test_tick_prune_takes_the_lock(settings, monkeypatch):
    from careeros import retention
    from careeros.runs import tick

    seen = []
    monkeypatch.setattr(retention, "plan", lambda s: seen.append(locks.read(RunStore(s).runner_lock_path)) or [])
    status, _ = tick._run_one(tick.default_actions(settings)["prune"], "schedule")
    assert status == "ok" and seen[0]["owner"] == "schedule:prune"
    assert locks.read(RunStore(settings).runner_lock_path) is None


# --- UI step runner -------------------------------------------------------------------------------------------

def test_ui_start_step_scout_or_prune_during_a_batch_is_busy(settings):
    from test_ui_runs_service import make_rc

    from careeros.ui.services.runs import Busy

    rc = make_rc(settings)
    hold_batch(settings, pid=999)
    for kind in ("scout", "prune"):
        with pytest.raises(Busy):
            rc.start_step(kind)
    rc.start_step("tracker")  # the tracker writes atomically per op: it may run beside a batch


def test_step_process_refuses_without_recording_a_run(settings):
    from careeros.ui.services import step
    from careeros.ui.services.runs import Busy

    hold_batch(settings)
    with pytest.raises(Busy):
        step.run_step(settings, "prune", actions={"prune": lambda: ("ok", "")})
    rs = RunStore(settings)
    assert rs.list_runs() == [] and locks.read(step.step_lock_path(rs, "prune")) is None


def test_step_holds_the_pipeline_lock_under_its_own_owner(settings):
    from careeros.ui.services import step

    rs = RunStore(settings)
    seen = []
    run = step.run_step(settings, "scout", actions={"scout": lambda: (seen.append(locks.read(rs.runner_lock_path)),
                                                                      ("ok", ""))[1]})
    assert seen[0]["owner"] == f"step:{run['id']}" and locks.read(rs.runner_lock_path) is None


def test_current_reports_a_step_and_an_unrecorded_cli_holder(settings):
    from test_ui_runs_service import make_rc

    from careeros.ui.services import step

    rc = make_rc(settings)
    rs = RunStore(settings)
    run = rs.new_run("tracker", "manual", {}, rc.now(), step=True)
    locks.acquire(step.step_lock_path(rs, "tracker"), owner=f"step:{run['id']}", ttl_seconds=600, pid=4321,
                  note="tracker")
    cur = rc.current()
    assert cur["id"] == run["id"] and cur["kind"] == "tracker" and cur["holder"]["pid"] == 4321
    locks.release(step.step_lock_path(rs, "tracker"), None, force=True)

    locks.acquire(rs.runner_lock_path, owner="cli:prune", ttl_seconds=600, pid=4321, note="prune")
    cur = rc.current()
    assert cur["kind"] == "prune" and cur["state"] == "running" and cur["holder"]["pid"] == 4321
    assert cur["started_at"] == cur["holder"]["acquired_at"] and cur["attempts"] == []
    assert cur["used"]["max_jobs"] is None
