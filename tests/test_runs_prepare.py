"""Prepare runs, retry-once-then-Action-Item and the daily-cap stop, with a fake invoker (no claude)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from careeros.models import Posting
from careeros.runs.config import budget_for, load_runs_config
from careeros.runs.failures import Failures
from careeros.runs.headless import HeadlessResult, parse_stream
from careeros.runs.runner import select_candidates
from careeros.runs.service import run_batch
from careeros.runs.store import RunStore
from careeros.store import Store
from careeros.tracker import Tracker

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def add_job(store: Store, n: int, company="Acme", fit=80, decision="prepare", status="scored", hours_old=60,
            category="swe_backend") -> str:
    p = Posting(company=company, title=f"Backend Software Engineer {n}", ats="greenhouse", ats_job_id=f"id{n}",
                url=f"https://boards.greenhouse.io/x/jobs/{n}", description_text="apis " * 50,
                posted_at=(NOW - timedelta(hours=hours_old)).isoformat())
    store.save_posting(p)
    if decision:
        (store.job_dir(p.job_id) / "score.json").write_text(json.dumps(
            {"job_id": p.job_id, "decision": decision, "fit": fit, "category": category, "tier": "C"}))
    if status != "found":
        store.set_status(p.job_id, status, "test")
    return p.job_id


def events(result: dict | None) -> list[str]:
    text = "RESULT: " + json.dumps(result) if result is not None else "no result"
    return [json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "s",
                        "result": text})]


class Fake:
    def __init__(self, settings, modes=None, default="queued"):
        self.s, self.modes, self.default, self.calls = settings, modes or {}, default, []

    def __call__(self, cmd, cwd, env, timeout_s, stream_path):
        jid = Path(cmd[-1].split(" ", 1)[1]).name
        self.calls.append(jid)
        mode = self.modes.get(jid, self.default)
        Path(stream_path).write_text("{}")
        store = Store(self.s)
        if mode in ("queued", "needs_review", "skipped"):
            store.set_status(jid, mode, "fake prepare")
            return parse_stream(events({"skill": "prepare-job", "job_id": jid, "status": mode}))
        if mode == "lie":  # RESULT says queued, status.json was never updated
            return parse_stream(events({"skill": "prepare-job", "job_id": jid, "status": "queued"}))
        if mode == "garbage":
            return parse_stream(events(None))
        if mode == "usage_limit":
            r = parse_stream([json.dumps({"type": "result", "is_error": True, "result": "hit your limit"})])
            r.exit_code = 1
            return r
        if mode == "score_ok":
            (store.job_dir(jid) / "score.json").write_text(json.dumps({"decision": "prepare", "fit": 80}))
            return parse_stream(events({"job_id": jid, "decision": "prepare"}))
        if mode == "score_garbage":
            return parse_stream(events(None))
        raise AssertionError(mode)


def batch(settings, kind, fake, max_jobs=5, **runs):
    settings.pipeline = {**settings.pipeline, "runs": {**(settings.pipeline.get("runs") or {}),
                                                       "preflight_doctor": False, **runs}}
    cfg = load_runs_config(settings)
    return run_batch(settings, kind, budget_for(cfg, kind, max_jobs=max_jobs), cfg=cfg, invoke=fake,
                     now=lambda: NOW)


@pytest.fixture
def store(settings):
    return Store(settings)


def test_prepare_selects_scored_prepare_jobs_by_fit(settings, store):
    low = add_job(store, 1, company="A", fit=70)
    high = add_job(store, 2, company="B", fit=95)
    add_job(store, 3, company="C", decision="skip")
    add_job(store, 4, company="D", status="queued")
    unscored = add_job(store, 5, company="E", decision=None, status="found")
    fake = Fake(settings)
    rec = batch(settings, "prepare", fake)
    assert fake.calls == [high, low] and rec["stop_reason"] == "completed"
    assert unscored not in fake.calls
    assert store.get_status(high) == "queued"


def test_found_job_with_prepare_score_is_a_candidate(settings, store):
    jid = add_job(store, 1, status="found")
    sel, _ = select_candidates(settings, "prepare", load_runs_config(settings), NOW)
    assert [c["job_id"] for c in sel] == [jid]


def test_prepared_job_with_qa_pass_is_not_redone(settings, store):
    jid = add_job(store, 1)
    (store.job_dir(jid) / "prepare.json").write_text(json.dumps({"qa_pass": True}))
    sel, _ = select_candidates(settings, "prepare", load_runs_config(settings), NOW)
    assert sel == []


def test_company_gate_blocked_job_is_passed_over_without_a_call(settings, store):
    a = add_job(store, 1, company="Acme", fit=90)
    b = add_job(store, 2, company="Acme", fit=85)
    c = add_job(store, 3, company="Acme", fit=80)  # cap 2 per company: the third waits
    fake = Fake(settings)
    rec = batch(settings, "prepare", fake)
    assert fake.calls == [a, b] and rec["counters"]["gated"] == 1
    assert store.get_status(c) == "scored"  # untouched, never bulk-skipped


def test_result_that_disagrees_with_status_json_is_invalid(settings, store):
    jid = add_job(store, 1)
    batch(settings, "prepare", Fake(settings, default="lie"))
    (att,) = RunStore(settings).load_attempts(RunStore(settings).list_runs()[0]["id"])
    assert att["outcome"] == "invalid_result" and "status.json" in att["detail"]
    assert jid


def test_failed_job_is_retried_once_then_becomes_an_action_item(settings, store):
    jid = add_job(store, 1, status="found", decision=None)
    first = batch(settings, "score", Fake(settings, default="score_garbage"))
    assert first["counters"]["failed"] == 1
    f = Failures(RunStore(settings))
    assert f.get("score", jid)["count"] == 1
    sel, _ = select_candidates(settings, "score", load_runs_config(settings), NOW, retry_ids=f.retry_ids("score", 2))
    assert "retry" in sel[0]["why"]

    fake = Fake(settings, default="score_garbage")
    second = batch(settings, "score", fake)
    assert fake.calls == [jid] and second["counters"]["failed"] == 1
    items = Tracker(settings=settings).list_action_items()
    assert len(items) == 1 and items[0]["JobID"] == jid and "score" in items[0]["What to do"]

    fake3 = Fake(settings, default="score_garbage")
    third = batch(settings, "score", fake3)
    assert fake3.calls == [] and third["stop_reason"] == "completed"
    assert len(Tracker(settings=settings).list_action_items()) == 1  # deduped, not re-added
    assert store.get_status(jid) == "found"  # never bulk-skipped


def test_success_clears_the_failure(settings, store):
    jid = add_job(store, 1, status="found", decision=None)
    batch(settings, "score", Fake(settings, default="score_garbage"))
    batch(settings, "score", Fake(settings, default="score_ok"))
    assert Failures(RunStore(settings)).get("score", jid) is None


def test_system_stops_do_not_count_against_the_job(settings, store):
    jid = add_job(store, 1)
    rec = batch(settings, "prepare", Fake(settings, default="usage_limit"))
    assert rec["stop_reason"] == "usage_limit"
    assert Failures(RunStore(settings)).get("prepare", jid) is None


def test_retry_limit_is_configurable(settings, store):
    jid = add_job(store, 1, status="found", decision=None)
    for _ in range(2):
        batch(settings, "score", Fake(settings, default="score_garbage"), retry={"max_attempts": 3})
    assert Tracker(settings=settings).list_action_items() == []
    assert jid


def test_daily_cap_stops_prepare_when_the_backlog_fills_it(settings, store):
    settings.targets = {**settings.targets, "volume": {**settings.targets["volume"],
                                                        "max_applications_per_day": 1, "season_multiplier": {}}}
    add_job(store, 1, company="A", fit=90)
    add_job(store, 2, company="B", fit=80)
    fake = Fake(settings)
    rec = batch(settings, "prepare", fake)
    assert rec["stop_reason"] == "daily_cap" and len(fake.calls) == 1


def test_daily_cap_stop_can_be_turned_off(settings, store):
    settings.targets = {**settings.targets, "volume": {**settings.targets["volume"],
                                                        "max_applications_per_day": 1, "season_multiplier": {}}}
    add_job(store, 1, company="A", fit=90)
    add_job(store, 2, company="B", fit=80)
    rec = batch(settings, "prepare", Fake(settings), prepare={"stop_at_daily_cap": False})
    assert rec["stop_reason"] == "completed"
