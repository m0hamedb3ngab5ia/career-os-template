"""`runs.parallel.prepare: N`: a prepare run works on up to N jobs of different companies at once. Two jobs of
one company never overlap, so the company gate's slot check and the slot a prepare takes are never raced."""
from __future__ import annotations

import threading
import time

import pytest

from careeros.config import ConfigError
from careeros.runs import locks
from careeros.runs.store import RunStore
from careeros.store import Store
from test_runs_prepare import Fake, add_job, batch

pytestmark = pytest.mark.unit


class Slow(Fake):
    """Fake prepare that holds each call for `hold_s`; records peak overlap and which companies overlapped."""

    def __init__(self, settings, hold_s=0.15, **kw):
        super().__init__(settings, **kw)
        self.hold_s, self.mu, self.active, self.peak, self.clashes = hold_s, threading.Lock(), {}, 0, []

    def __call__(self, cmd, cwd, env, timeout_s, stream_path):
        from pathlib import Path
        jid = Path(cmd[-1].splitlines()[0].split()[1]).name
        co = (Store(self.s)._read(jid, "posting.json") or {})["company"]
        with self.mu:
            if co in self.active.values():
                self.clashes.append(co)
            self.active[jid] = co
            self.peak = max(self.peak, len(self.active))
        try:
            time.sleep(self.hold_s)
            return super().__call__(cmd, cwd, env, timeout_s, stream_path)
        finally:
            with self.mu:
                self.active.pop(jid)


@pytest.fixture
def store(settings):
    return Store(settings)


def test_config_accepts_prepare_and_rejects_apply(settings):
    from test_runs_runner import cfg_of
    assert cfg_of(settings).parallel == {"score": 1, "prepare": 1}
    assert cfg_of(settings, parallel={"prepare": 3}).parallel["prepare"] == 3
    for bad in ({"prepare": 0}, {"apply": 2}):
        with pytest.raises(ConfigError):
            cfg_of(settings, parallel=bad)


def test_default_prepare_is_sequential(settings, store):
    for i, co in enumerate("ABC", 1):
        add_job(store, i, company=co, fit=90 - i)
    fake = Slow(settings, hold_s=0.05)
    batch(settings, "prepare", fake)
    assert fake.peak == 1


def test_prepare_runs_n_jobs_at_once_and_launches_fit_first(settings, store):
    ids = [add_job(store, i, company=co, fit=90 - i) for i, co in enumerate("ABCD", 1)]
    fake = Slow(settings)
    rec = batch(settings, "prepare", fake, parallel={"prepare": 3})
    assert fake.peak == 3 and set(fake.calls[:3]) == set(ids[:3]) and sorted(fake.calls) == sorted(ids)
    assert rec["counters"]["attempted"] == 4 and rec["stop_reason"] == "completed"


def test_same_company_jobs_never_overlap(settings, store):
    a = add_job(store, 1, company="Acme", fit=90)
    b = add_job(store, 2, company="Acme", fit=85)
    c = add_job(store, 3, company="Other", fit=80)
    fake = Slow(settings)
    batch(settings, "prepare", fake, parallel={"prepare": 3})
    assert fake.clashes == [] and fake.peak == 2 and sorted(fake.calls) == sorted([a, b, c])


def test_last_slot_goes_to_exactly_one_of_two_same_company_candidates(settings, store):
    add_job(store, 1, company="Acme", status="queued", decision="prepare", fit=99)  # already holds 1 of 2 slots
    x = add_job(store, 2, company="Acme", fit=90)
    y = add_job(store, 3, company="Acme", fit=85)
    fake = Slow(settings)
    rec = batch(settings, "prepare", fake, parallel={"prepare": 3})
    assert len(fake.calls) == 1 and fake.calls[0] == x and rec["counters"]["gated"] == 1
    assert store.get_status(y) == "scored"


def test_explicit_job_runs_stay_sequential(settings, store):
    from careeros.runs.config import budget_for, load_runs_config
    from careeros.runs.service import run_batch
    from test_runs_prepare import NOW
    ids = [add_job(store, i, company=co) for i, co in enumerate("ABC", 1)]
    settings.pipeline = {**settings.pipeline, "runs": {"preflight_doctor": False, "parallel": {"prepare": 3}}}
    cfg = load_runs_config(settings)
    fake = Slow(settings, hold_s=0.05)
    run_batch(settings, "prepare", budget_for(cfg, "prepare", max_jobs=5), cfg=cfg, invoke=fake, now=lambda: NOW,
              job_ids=ids)
    assert fake.peak == 1 and sorted(fake.calls) == sorted(ids)


def test_daily_cap_stop_counts_jobs_in_flight(settings, store):
    """stop_at_daily_cap reads queued jobs; with workers the stop is still checked before each launch."""
    for i, co in enumerate("ABCDEF", 1):
        add_job(store, i, company=co, fit=90 - i)
    fake = Slow(settings, hold_s=0.05)
    rec = batch(settings, "prepare", fake, max_jobs=4, parallel={"prepare": 3})
    assert len(fake.calls) == 4 and rec["stop_reason"] == "budget_reached"
