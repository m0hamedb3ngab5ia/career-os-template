"""TASK-039 (REQ-134, REQ-135, UC-017): ranked score queue (quick match desc, fresh before stale, below
min_prescore skipped) and per-scan / per-day caps. E2E-017-02/03."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from careeros.config import ConfigError
from careeros.runs.config import budget_for, load_runs_config
from careeros.runs.runner import CLEAN_STOPS
from careeros.runs.scoring import DEFAULT_SCORING, dry_run_line, load_scoring_config
from careeros.runs.service import run_batch
from careeros.runs.store import RunStore
from careeros.store import Store
from test_runs_runner import NOW, FakeInvoke, add_job

pytestmark = pytest.mark.unit


def job(store, n, prescore=None, days_old=1.0):
    return add_job(store, n, hours_old=days_old * 24, **({"raw": {"prescore": prescore}} if prescore is not None
                                                          else {}))


def score_run(settings, *, max_jobs=25, dry_run=False, job_ids=None, invoke=None, **scoring):
    settings.pipeline = {**settings.pipeline, "runs": {"preflight_doctor": False}, "scoring": scoring}
    cfg = load_runs_config(settings)
    inv = invoke or FakeInvoke(settings)
    rec = run_batch(settings, "score", budget_for(cfg, "score", max_jobs=max_jobs, max_minutes=600), cfg=cfg,
                    invoke=inv, dry_run=dry_run, job_ids=job_ids, now=lambda: NOW)
    return rec, inv


def earlier_run(settings, attempted, hours_ago=1.0, daily=True):
    rs = RunStore(settings)
    r = rs.new_run("score", "schedule", {}, NOW - timedelta(hours=hours_ago))
    r.update(status="done", stop_reason="completed", duration_s=attempted * 60.0,
             counters={"attempted": attempted}, daily_scoring=daily)
    rs.save_run(r)


@pytest.fixture
def store(settings) -> Store:
    return Store(settings)


def test_e2e_017_02_freshest_highest_first_stale_last(settings, store):
    a40, a80, a60 = job(store, 1, 40), job(store, 2, 80), job(store, 3, 60)
    s90, s95 = job(store, 4, 90, days_old=30), job(store, 5, 95, days_old=40)
    rec, inv = score_run(settings, per_scan=3)
    assert [c["job_id"] for c in inv.calls] == [a80, a60, a40]
    assert rec["stop_reason"] == "budget_reached"
    dry, _ = score_run(settings, dry_run=True)  # stale ones queue after every fresh one, never dropped
    assert dry["scoring"]["queue"] == 2 and [r["job_id"] for r in dry["selected"]] == [s95, s90]


def test_req_134_example_takes_the_two_fresh_jobs(settings, store):
    f80, f40 = job(store, 1, 80), job(store, 2, 40)
    job(store, 3, 90, days_old=30)
    _, inv = score_run(settings, per_scan=2, min_prescore=0)
    assert [c["job_id"] for c in inv.calls] == [f80, f40]


def test_below_min_prescore_is_not_auto_scored_but_listed(settings, store):
    low, ok, unknown = job(store, 1, 10), job(store, 2, 50), job(store, 3)  # no prescore yet: queued, not cut
    rec, inv = score_run(settings, min_prescore=20)
    assert [c["job_id"] for c in inv.calls] == [ok, unknown]
    assert Store(settings).get_status(low) == "found"
    assert any(e["job_id"] == low and e["reason"].startswith("below cutoff")
               for e in RunStore(settings).load_queue("score")["excluded"])


def test_e2e_017_03_daily_cap_reached_scores_nothing_exit_0(settings, store):
    job(store, 1, 80)
    earlier_run(settings, 5)
    rec, inv = score_run(settings, per_day=5)
    assert inv.calls == [] and rec["stop_reason"] in CLEAN_STOPS
    assert rec["detail"] == "daily scoring limit reached (5); next run tomorrow"


def test_req_135_daily_cap_stops_mid_run_and_counts_only_today(settings, store):
    ids = [job(store, i, 90 - i) for i in range(1, 5)]
    earlier_run(settings, 3)
    earlier_run(settings, 50, hours_ago=30)       # yesterday: not counted
    earlier_run(settings, 50, daily=False)        # Score now / --job runs: not counted
    rec, inv = score_run(settings, per_day=5)
    assert [c["job_id"] for c in inv.calls] == ids[:2]
    assert rec["detail"].startswith("daily scoring limit reached (5)") and rec["daily_scoring"] is True


def test_explicit_job_ignores_cutoff_and_caps(settings, store):
    low = job(store, 1, 5, days_old=40)
    earlier_run(settings, 9)
    rec, inv = score_run(settings, job_ids=[low], per_day=9, per_scan=1, min_prescore=50)
    assert [c["job_id"] for c in inv.calls] == [low] and rec["stop_reason"] == "completed"
    assert not rec.get("daily_scoring")


def test_dry_run_shows_queue_cap_left_and_eta(settings, store):
    for i in range(1, 5):
        job(store, i, 50)
    earlier_run(settings, 2)  # 2 attempts in 120 s: 1 min each
    rec, inv = score_run(settings, dry_run=True, per_scan=3, per_day=4)
    assert inv.calls == [] and len(rec["selected"]) == 2
    info = rec["scoring"]
    assert info == {"queue": 4, "per_scan": 3, "per_day": 4, "left_today": 2, "take": 2, "eta_minutes": 2}
    assert dry_run_line(info) == ("score queue 4; this run takes 2 (per scan 3, 2 of 4 left today); ETA ~2 min")


def test_scoring_config_defaults_validation_and_example(settings):
    assert load_scoring_config(None) == DEFAULT_SCORING == {"per_scan": 150, "per_day": 300, "stale_days": 21,
                                                            "min_prescore": 20}
    for bad in ({"per_scan": 0}, {"per_day": -1}, {"stale_days": 1.5}, {"min_prescore": 101}, {"nope": 1}, []):
        with pytest.raises(ConfigError):
            load_scoring_config(bad)
    ex = yaml.safe_load((Path(__file__).parents[1] / "examples/config/pipeline.yaml").read_text())
    assert load_scoring_config(ex["scoring"]) == DEFAULT_SCORING


def test_doctor_flags_a_bad_scoring_block():
    from careeros.doctor import FAIL, check_runs

    assert any(c.level == FAIL and c.name == "scoring" for c in check_runs({"scoring": {"per_day": "lots"}}))
    assert any(c.name == "scoring" and c.level != FAIL for c in check_runs({}))


def test_runs_config_without_scoring_block_uses_defaults(settings, store):
    from dataclasses import replace

    job(store, 1, 80)
    settings.pipeline = {**settings.pipeline, "runs": {"preflight_doctor": False}}
    cfg = replace(load_runs_config(settings), scoring={})  # e.g. RunsConfig() built directly
    inv = FakeInvoke(settings)
    rec = run_batch(settings, "score", budget_for(cfg, "score", max_jobs=5, max_minutes=600), cfg=cfg,
                    invoke=inv, now=lambda: NOW)
    assert len(inv.calls) == 1 and rec["daily_scoring"] is True


def test_req_134_equal_quick_match_newest_posting_first_not_rank_bonus():
    from careeros.runs.scoring import order_queue
    ranked = [{"job_id": "old-dream", "rank": 1}, {"job_id": "new", "rank": 2}]  # dream bonus put the older one first
    meta = {"old-dream": (50, NOW - timedelta(days=5)), "new": (50, NOW - timedelta(days=1))}
    queue, _ = order_queue(ranked, meta, NOW, DEFAULT_SCORING)
    assert [r["job_id"] for r in queue] == ["new", "old-dream"]


class _Boom(BaseException):
    pass


def test_req_135_a_run_that_raises_still_counts_toward_per_day(settings, store):
    job(store, 1, 80)
    inner = FakeInvoke(settings)

    def boom(*a, **k):
        inner(*a, **k)
        raise _Boom()
    with pytest.raises(_Boom):
        score_run(settings, invoke=boom)
    (saved,) = RunStore(settings).list_runs("score")
    assert saved.get("daily_scoring") is True
