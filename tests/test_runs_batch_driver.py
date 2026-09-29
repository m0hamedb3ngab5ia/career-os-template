"""Batch driver (slice 8): outcome -> job state, pause / cancel / retry, the retry cap, the hard rules re-checked
right before each apply run (LinkedIn, auto-submit verdict), the batch lock, waiting on the runner lock."""
from __future__ import annotations

import json

import pytest
from test_runs_batches import allow_submit, put
from test_runs_runner import NOW, FakeInvoke, add_job

from careeros.runs import batches, locks
from careeros.runs.failures import Failures
from careeros.runs.runner import RunBusy
from careeros.runs.store import RunStore
from careeros.store import Store

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_doctor(settings):
    settings.pipeline = {**settings.pipeline, "runs": {**(settings.pipeline.get("runs") or {}),
                                                       "preflight_doctor": False}}


@pytest.mark.parametrize("kind,outcome,stop,session,want", [
    ("score", "ok", "completed", None, "next"),
    ("apply", "ok", "completed", {"outcome": "submitted"}, "done"),
    ("apply", "ok", "completed", {"outcome": "staged"}, "needs_you"),
    ("apply", "ok", "completed", {"outcome": "blocked"}, "needs_you"),
    ("apply", "ok", "completed", None, "needs_you"),
    ("prepare", "timeout", "completed", None, "failed"),
    ("apply", "skill_error", "completed", None, "failed"),
    ("score", "usage_limit", "usage_limit", None, "pause"),
    ("score", "auth_required", "auth_required", None, "pause"),
    ("score", None, "paused", None, "pause"),
    ("score", "cancelled", "cancelled", None, "cancelled"),
])
def test_bucket(kind, outcome, stop, session, want):
    assert batches.bucket(kind, outcome, stop, session)[0] == want


@pytest.mark.parametrize("reason,want", [
    ("already scored", "next"), ("qa not passed", "needs_you"), ("status needs_review", "needs_you"),
    ("application staged in the browser", "needs_you"), ("failed 2 times (last: timeout); see Action Items", "failed"),
    ("company gate: closed (x)", "skipped"), ("score decision skip", "skipped"), ("status applied", "skipped"),
])
def test_not_runnable(reason, want):
    assert batches.not_runnable(reason)[0] == want


def fake_run(outcomes, on_call=None):
    """A run_batch stand-in: records calls, saves one attempt with the next outcome."""
    calls = []

    def run(settings, kind, budget, *, cfg, job_ids, **kw):
        calls.append((kind, job_ids, cfg))
        if on_call:
            on_call(len(calls))
        rid = f"r{len(calls)}"
        out = outcomes.pop(0) if outcomes else "ok"
        RunStore(settings).save_attempt(rid, {"n": 1, "outcome": out})
        return {"id": rid, "stop_reason": out if out in ("usage_limit", "cancelled") else "completed"}
    run.calls = calls
    return run


def make(settings, n=2, stop_at="score"):
    s = Store(settings)
    ids = [add_job(s, i) for i in range(1, n + 1)]
    return batches.create(settings, ids, stop_at, now=NOW)


def states(b):
    return [r["state"] for r in b["selected"]]


def test_drive_score_end_to_end_with_fake_invoke(settings):
    b = make(settings)
    inv = FakeInvoke(settings)
    out = batches.drive(settings, b["id"], invoke=inv, now=lambda: NOW)
    assert out["status"] == "done" and states(out) == ["done", "done"]
    assert len(inv.calls) == 2 and all(r["result"] == "scored" for r in out["selected"])
    assert batches.load(settings, b["id"])["status"] == "done"
    assert not locks.read(batches._lock_path(settings, b["id"]))


def test_pause_request_takes_effect_after_current_job(settings):
    b = make(settings, 3)
    run = fake_run([], on_call=lambda n: batches.control(settings, b["id"], "pause"))
    out = batches.drive(settings, b["id"], run=run)
    assert out["status"] == "paused" and states(out) == ["done", "pending", "pending"]
    out = batches.drive(settings, b["id"], run=fake_run([]))  # resume
    assert out["status"] == "done" and states(out) == ["done"] * 3


def test_cancel_stops_after_current_step(settings):
    b = make(settings, 2, stop_at="prepare")
    run = fake_run([], on_call=lambda n: batches.control(settings, b["id"], "cancel"))
    out = batches.drive(settings, b["id"], run=run)
    assert len(run.calls) == 1 and out["status"] == "cancelled" and states(out) == ["cancelled"] * 2


def test_control_without_driver_writes_status_under_lock(settings):
    b = make(settings)
    assert batches.control(settings, b["id"], "cancel")["status"] == "cancelled"
    assert batches.drive(settings, b["id"], run=fake_run([]))["status"] == "cancelled"  # nothing runs


def test_usage_limit_pauses_batch_and_keeps_job(settings):
    b = make(settings)
    out = batches.drive(settings, b["id"], run=fake_run(["usage_limit"]))
    assert out["status"] == "paused" and "usage_limit" in out["reason"] and states(out) == ["pending", "pending"]


def test_global_pause_pauses_batch(settings):
    b = make(settings)
    RunStore(settings).set_pause(None, "holiday", NOW)
    run = fake_run([])
    out = batches.drive(settings, b["id"], run=run)
    assert out["status"] == "paused" and not run.calls and "holiday" in out["reason"]


def test_retry_cap_then_retry_resets(settings):
    b = make(settings, 1)
    jid = b["selected"][0]["job_id"]
    inv = FakeInvoke(settings, default="timeout")
    out = batches.drive(settings, b["id"], invoke=inv, now=lambda: NOW)
    max_attempts = 2
    assert len(inv.calls) == max_attempts
    assert states(out) == ["failed"] and out["selected"][0]["reason"].startswith("failed 2 times")
    out = batches.retry(settings, b["id"])
    assert out["retried"] == 1 and states(out) == ["pending"] and out["status"] == "queued"
    assert Failures(RunStore(settings)).get("score", jid) is None


def test_retry_never_touches_hands_off_or_done(settings):
    b = make(settings, 2)
    batches.drive(settings, b["id"], run=fake_run(["timeout", "timeout", "ok"]))  # job1 fails twice via fake
    data = batches.load(settings, b["id"])
    data["selected"][0]["state"] = "failed"
    jd = Store(settings).job_dir(data["selected"][0]["job_id"])
    (jd / "apply_session.json").write_text(json.dumps({"outcome": "staged"}))
    batches._dump(batches._dir(settings) / f"{b['id']}.json", data)
    out = batches.retry(settings, b["id"])
    assert out["retried"] == 0 and "not retried" in out["selected"][0]["reason"]


def test_apply_rechecks_linkedin_before_run(settings):
    s = Store(settings)
    jid = put(s, add_job(s, 1), "prepared", tier="B", qa=True)
    b = batches.create(settings, [jid], "fill", now=NOW)
    p = s.job_dir(jid) / "posting.json"
    p.write_text(json.dumps({**json.loads(p.read_text()), "apply_url": "https://www.linkedin.com/jobs/1"}))
    run = fake_run([])
    out = batches.drive(settings, b["id"], run=run)
    assert not run.calls and states(out) == ["needs_you"] and "LinkedIn" in out["selected"][0]["reason"]


@pytest.mark.parametrize("stop_at,tier,want", [("submit", "B", "1"), ("submit", "A", "0"), ("fill", "B", "0")])
def test_apply_reruns_submit_verdict_tier_a_never_submits(settings, stop_at, tier, want):
    allow_submit(settings)
    settings.pipeline["runs"]["auto_submit"]["allow"] = ["tier_a", "tier_b"]
    settings.pipeline["runs"]["preflight_doctor"] = False
    s = Store(settings)
    jid = put(s, add_job(s, 1), "prepared", tier="B", qa=True)
    b = batches.create(settings, [jid], stop_at, now=NOW)
    put(s, jid, "prepared", tier=tier, qa=True)  # changed after the preview: the driver must not trust it
    sp = s.job_dir(jid) / "score.json"
    sp.write_text(json.dumps({**json.loads(sp.read_text()), "category": "swe_backend"}))  # the company gate needs it
    inv = FakeInvoke(settings, default="garbage")
    out = batches.drive(settings, b["id"], invoke=inv, now=lambda: NOW)
    assert inv.calls and all(c["env"]["CAREEROS_AUTO_SUBMIT"] == want for c in inv.calls)
    assert all(len(c["cmd"]) and c["job_id"] == jid for c in inv.calls)  # one job per apply run
    assert out["selected"][0]["auto_submit"] is (want == "1")


def test_batch_lock_single_driver(settings):
    b = make(settings, 1)
    lk = locks.acquire(batches._lock_path(settings, b["id"]), owner="other", ttl_seconds=60, pid=None)
    with pytest.raises(batches.BatchBusy):
        batches.drive(settings, b["id"], run=fake_run([]))
    assert batches.control(settings, b["id"], "pause")["requested"] == "pause"  # a request, status untouched
    assert batches.load(settings, b["id"])["status"] == "queued"
    with pytest.raises(batches.BatchBusy):
        batches.retry(settings, b["id"])
    locks.release(lk.path, lk.token)


def test_waits_while_runner_lock_is_held(settings):
    b = make(settings, 1)
    busy = [True]

    def run(settings_, kind, budget, **kw):
        if busy[0]:
            raise RunBusy({"owner": "run:x", "pid": 1})
        return fake_run([])(settings_, kind, budget, **kw)

    slept = []
    out = batches.drive(settings, b["id"], run=run, sleep=lambda s: (slept.append(s), busy.__setitem__(0, False)))
    assert slept and states(out) == ["done"]


def test_drive_loads_batch_after_taking_the_lock(settings, monkeypatch):
    b = make(settings)
    real = locks.acquire

    def acquire(*a, **kw):  # a control that finished just before the driver got the lock
        if kw.get("owner") == f"batch:{b['id']}":
            batches.control(settings, b["id"], "cancel")
        return real(*a, **kw)
    monkeypatch.setattr(batches.locks, "acquire", acquire)
    run = fake_run([])
    out = batches.drive(settings, b["id"], run=run)
    assert not run.calls and out["status"] == "cancelled"
    assert batches.load(settings, b["id"])["status"] == "cancelled"


def test_stale_request_is_dropped_when_driver_starts(settings):
    b = make(settings)
    batches._req_path(settings, b["id"]).write_text("cancel", encoding="utf-8")
    out = batches.drive(settings, b["id"], run=fake_run([]))
    assert out["status"] == "done" and states(out) == ["done", "done"]


def test_apply_verdict_rerun_on_each_retry_pass(settings, monkeypatch):
    allow_submit(settings)
    s = Store(settings)
    jid = put(s, add_job(s, 1), "prepared", tier="B", qa=True)
    b = batches.create(settings, [jid], "submit", now=NOW)
    seen = []
    monkeypatch.setattr(batches, "auto_submit_verdict", lambda *a: (seen.append(1), (False, "no"))[1])
    run = fake_run(["timeout", "ok"])
    batches.drive(settings, b["id"], run=run)
    assert len(run.calls) == 2 and len(seen) == 2


def test_runner_busy_waits_do_not_count_against_the_cap(settings):
    b = make(settings, 1)
    busy = [60]

    def run(settings_, kind, budget, **kw):
        if busy[0]:
            busy[0] -= 1
            raise RunBusy({"owner": "run:x", "pid": 1})
        return fake_run([])(settings_, kind, budget, **kw)

    out = batches.drive(settings, b["id"], run=run, sleep=lambda s: None)
    assert states(out) == ["done"]


def test_pause_request_while_waiting_on_runner(settings):
    b = make(settings, 1)

    def run(settings_, kind, budget, **kw):
        raise RunBusy({"owner": "run:x", "pid": 1})

    out = batches.drive(settings, b["id"], run=run,
                        sleep=lambda s: batches._req_path(settings, b["id"]).write_text("pause"))
    assert out["status"] == "paused" and states(out) == ["pending"]


def test_driver_renews_its_lock_per_job(settings, monkeypatch):
    b = make(settings, 2)
    refreshed = []
    monkeypatch.setattr(batches.locks, "refresh", lambda *a, **kw: refreshed.append(a) or True)
    batches.drive(settings, b["id"], run=fake_run([]))
    assert len(refreshed) == 2
