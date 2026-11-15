"""`runs.parallel.score: N`: a score run scores up to N jobs at once (bounded worker pool) and keeps every guarantee
of the sequential loop: budgets, daily caps, pause, stop rules, one attempt record per job, ordered run record."""
from __future__ import annotations

import threading
import time
import pytest

from careeros.config import ConfigError
from careeros.runs.config import budget_for, load_runs_config
from careeros.runs.store import RunStore
from careeros.store import Store
from test_runs_runner import NOW, FakeInvoke, add_job, cfg_of, run
from test_scoring_queue import earlier_run

pytestmark = pytest.mark.unit


class Concurrent(FakeInvoke):
    """FakeInvoke that takes `hold_s` per call and records the peak number of calls in flight."""

    def __init__(self, settings, hold_s: float = 0.15, **kw):
        super().__init__(settings, **kw)
        self.hold_s, self.mu, self.active, self.peak = hold_s, threading.Lock(), 0, 0

    def __call__(self, cmd, cwd, env, timeout_s, stream_path):
        with self.mu:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.hold_s)
            with self.mu:
                return super().__call__(cmd, cwd, env, timeout_s, stream_path)
        finally:
            with self.mu:
                self.active -= 1


@pytest.fixture
def store(settings) -> Store:
    return Store(settings)


def jobs(store, n):
    return [add_job(store, i, hours_old=50 + i * 10) for i in range(1, n + 1)]


def test_default_is_one_job_at_a_time(settings, store):
    ids = jobs(store, 3)
    inv = Concurrent(settings, hold_s=0.05)
    rec = run(settings, inv)
    assert inv.peak == 1 and rec["stop_reason"] == "completed"
    assert [c["job_id"] for c in inv.calls] == ids


def test_parallel_three_scores_jobs_concurrently_and_records_each_once(settings, store):
    ids = jobs(store, 6)
    inv = Concurrent(settings)
    t0 = time.monotonic()
    rec = run(settings, inv, parallel={"score": 3})
    took = time.monotonic() - t0
    assert inv.peak == 3 and took < 6 * 0.15  # sequential would take >= 0.9 s
    assert rec["stop_reason"] == "completed" and rec["counters"]["attempted"] == 6 and rec["counters"]["ok"] == 6
    assert all(store.get_status(j) == "scored" for j in ids)
    atts = RunStore(settings).load_attempts(rec["id"])
    assert sorted(a["job_id"] for a in atts) == sorted(ids)  # one attempt per job, none lost or doubled
    assert [a["n"] for a in atts] == [1, 2, 3, 4, 5, 6] and rec["attempts"] == [1, 2, 3, 4, 5, 6]
    assert sorted(c["job_id"] for c in inv.calls) == sorted(ids)


def test_parallel_stops_launching_at_max_jobs(settings, store):
    ids = jobs(store, 7)
    inv = Concurrent(settings)
    rec = run(settings, inv, max_jobs=4, parallel={"score": 3})
    assert len(inv.calls) == 4 and rec["counters"]["attempted"] == 4
    assert rec["stop_reason"] == "budget_reached" and rec["detail"].startswith("4 job(s) done; 3 left")
    assert [store.get_status(j) for j in ids].count("found") == 3


def test_parallel_pause_stops_new_launches_and_lets_running_jobs_finish(settings, store):
    jobs(store, 6)
    both_started = threading.Barrier(2, timeout=5)

    class PauseAfterStart(Concurrent):
        def __call__(self, cmd, cwd, env, timeout_s, stream_path):
            both_started.wait()
            RunStore(settings).set_pause(until=None, reason="test", now=NOW)
            return super().__call__(cmd, cwd, env, timeout_s, stream_path)

    inv = PauseAfterStart(settings)
    rec = run(settings, inv, parallel={"score": 2})
    assert rec["stop_reason"] == "paused" and len(inv.calls) == 2
    assert rec["counters"]["attempted"] == 2 and rec["counters"]["ok"] == 2  # in-flight jobs finished and counted


def test_parallel_consecutive_failures_stop_the_run(settings, store):
    jobs(store, 9)
    inv = Concurrent(settings, default="garbage")
    rec = run(settings, inv, parallel={"score": 3})
    assert rec["stop_reason"] == "consecutive_failures"
    assert 3 <= len(inv.calls) <= 5 and rec["counters"]["attempted"] == len(inv.calls)


def test_parallel_usage_limit_is_a_hard_stop(settings, store):
    jobs(store, 6)
    inv = Concurrent(settings, default="usage_limit")
    rec = run(settings, inv, parallel={"score": 3})
    assert rec["stop_reason"] == "usage_limit" and len(inv.calls) <= 5


def test_parallel_daily_cap_counts_jobs_in_flight(settings, store):
    from careeros.runs.service import run_batch

    jobs(store, 6)
    earlier_run(settings, 3)
    settings.pipeline = {**settings.pipeline, "runs": {"preflight_doctor": False, "parallel": {"score": 3}},
                         "scoring": {"per_day": 5}}
    cfg = load_runs_config(settings)
    inv = Concurrent(settings)
    rec = run_batch(settings, "score", budget_for(cfg, "score", max_jobs=25, max_minutes=600), cfg=cfg,
                    invoke=inv, now=lambda: NOW)
    assert len(inv.calls) == 2 and rec["stop_reason"] == "daily_cap"


@pytest.mark.parametrize("bad", [{"score": 0}, {"score": 1.5}, {"prepare": 2}, 3])
def test_parallel_config_is_validated(settings, bad):
    with pytest.raises(ConfigError):
        cfg_of(settings, parallel=bad)


def test_parallel_config_default_is_one(settings):
    assert cfg_of(settings).parallel == {"score": 1}
    assert cfg_of(settings, parallel={"score": 3}).parallel == {"score": 3}



def test_explicit_jobs_stay_sequential_so_a_locked_job_leaves_the_rest_untouched(settings, store):
    import os

    from careeros.runs import locks
    from careeros.runs.runner import JobBusy, execute_run

    first, second = jobs(store, 2)  # `first` is fresher: ranked first
    locks.acquire(RunStore(settings).job_lock_path(first), owner="someone-else", pid=os.getpid(), ttl_seconds=600)
    cfg = cfg_of(settings, preflight_doctor=False, parallel={"score": 3})
    inv = Concurrent(settings)
    with pytest.raises(JobBusy):
        execute_run(settings, "score", budget_for(cfg, "score"), cfg=cfg, invoke=inv, now=lambda: NOW,
                    job_ids=[first, second])
    assert inv.calls == [] and store.get_status(second) == "found"
