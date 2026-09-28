"""The run loop with a fake headless invoker (no subprocess, no claude): selection, budgets, stop reasons,
locks, run records."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from careeros.models import Posting
from careeros.runs import locks
from careeros.runs.config import budget_for, load_runs_config
from careeros.runs.headless import HeadlessResult, parse_stream
from careeros.runs.runner import RunBusy, execute_run, select_candidates
from careeros.runs.store import RunStore
from careeros.store import Store

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def add_job(store: Store, n: int, hours_old: float = 10, company: str = "Acme", title: str | None = None,
            **extra) -> str:
    p = Posting(company=company, title=title or f"Backend Software Engineer {n}", ats="greenhouse",
                ats_job_id=f"id{n}", url=f"https://boards.greenhouse.io/x/jobs/{n}",
                posted_at=(NOW - timedelta(hours=hours_old)).isoformat(), description_text="build apis " * 50)
    store.save_posting(p)
    if extra:
        path = store.job_dir(p.job_id) / "posting.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), **extra}))
    return p.job_id


def events(job_id: str, result: dict | None = None, **res_extra) -> list[str]:
    text = "RESULT: " + json.dumps(result) if result is not None else "no result"
    return [json.dumps({"type": "system", "subtype": "init", "session_id": f"s-{job_id}", "mcp_servers": []}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": f"s-{job_id}",
                        "result": text, "num_turns": 2, **res_extra})]


class FakeInvoke:
    """Records calls; per job returns a canned result and writes score.json like the skill."""

    def __init__(self, settings, modes: dict[str, str] | None = None, default: str = "prepare", clock=None,
                 step_s: float = 60):
        self.s, self.modes, self.default, self.calls = settings, modes or {}, default, []
        self.clock, self.step_s = clock, step_s

    def __call__(self, cmd, cwd, env, timeout_s, stream_path):
        job_id = Path(cmd[-1].split(" ", 1)[1]).name
        self.calls.append({"cmd": cmd, "cwd": cwd, "env": dict(env), "timeout_s": timeout_s, "job_id": job_id,
                           "lock": locks.read(RunStore(self.s).job_lock_path(job_id))})
        if self.clock:
            self.clock.t += self.step_s
        mode = self.modes.get(job_id, self.default)
        jd = Store(self.s).job_dir(job_id)
        if mode in ("prepare", "skip"):
            (jd / "score.json").write_text(json.dumps({"job_id": job_id, "decision": mode, "fit": 80,
                                                       "skip_reason": "below_min_fit" if mode == "skip" else None}))
            r = parse_stream(events(job_id, {"skill": "score-job", "job_id": job_id, "decision": mode,
                                             "skip_reason": "below_min_fit" if mode == "skip" else None}))
        elif mode == "garbage":
            r = parse_stream(events(job_id))
        elif mode == "usage_limit":
            r = parse_stream([json.dumps({"type": "result", "is_error": True, "result": "You've hit your limit"})])
            r.exit_code = 1
        elif mode == "auth":
            r = parse_stream([json.dumps({"type": "assistant", "error": "authentication_failed", "message": {}})])
            r.exit_code = 1
        elif mode == "deny":
            r = parse_stream(events(job_id, None, permission_denials=[{"tool_name": "Bash"}]))
        elif mode == "timeout":
            r = HeadlessResult(timed_out=True, exit_code=-9)
        elif mode == "cancel":
            r = HeadlessResult(cancelled=True, exit_code=-15)
        else:
            raise AssertionError(mode)
        Path(stream_path).write_text("\n".join(["{}"]))
        return r


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def cfg_of(settings, **runs):
    settings.pipeline = {**settings.pipeline, "runs": {**(settings.pipeline.get("runs") or {}), **runs}}
    return load_runs_config(settings)


def run(settings, invoke, max_jobs=25, max_minutes=90, doctor=None, dry_run=False, clock=None, **runs):
    cfg = cfg_of(settings, preflight_doctor=doctor is not None, **runs)
    b = budget_for(cfg, "score", max_jobs=max_jobs, max_minutes=max_minutes)
    return execute_run(settings, "score", b, cfg=cfg, invoke=invoke, doctor=doctor, dry_run=dry_run,
                       now=lambda: NOW, clock=clock or Clock())


@pytest.fixture
def store(settings) -> Store:
    return Store(settings)


def test_selects_top_ranked_and_leaves_the_rest_found(settings, store):
    fresh = [add_job(store, i, hours_old=50 + i * 10) for i in range(1, 4)]  # past 48h: distinct scores
    old = add_job(store, 9, hours_old=24 * 20)
    inv = FakeInvoke(settings)
    rec = run(settings, inv, max_jobs=3)
    assert [c["job_id"] for c in inv.calls] == [fresh[0], fresh[1], fresh[2]]
    assert rec["stop_reason"] == "budget_reached" and rec["status"] == "done"
    assert store.get_status(old) == "found"
    assert all(store.get_status(j) == "scored" for j in fresh)
    assert rec["counters"]["attempted"] == 3 and rec["counters"]["ok"] == 3 and rec["counters"]["candidates"] == 4


def test_run_record_attempts_log_and_queue(settings, store):
    jid = add_job(store, 1)
    rec = run(settings, FakeInvoke(settings))
    rs = RunStore(settings)
    saved = rs.load_run(rec["id"])
    assert saved["kind"] == "score" and saved["trigger"] == "manual" and saved["stop_reason"] == "completed"
    assert saved["budget"] == {"preset": "medium", "max_jobs": 25, "max_minutes": 90}
    assert saved["started_at"] and saved["ended_at"]
    (att,) = rs.load_attempts(rec["id"])
    assert att["job_id"] == jid and att["stage"] == "score" and att["outcome"] == "ok"
    assert att["session_id"] == f"s-{jid}" and att["result"]["decision"] == "prepare"
    assert (rs.run_dir(rec["id"]) / att["stream"]).exists()
    assert "completed" in (rs.run_dir(rec["id"]) / "run.log").read_text()
    q = rs.load_queue("score")
    assert q["items"][0]["job_id"] == jid and q["items"][0]["why"]


def test_skip_decision_records_skipped_with_reason_first(settings, store):
    jid = add_job(store, 1)
    run(settings, FakeInvoke(settings, default="skip"))
    st = json.loads((store.job_dir(jid) / "status.json").read_text())
    assert st["status"] == "skipped" and st["history"][-1]["note"].startswith("below_min_fit")


def test_invoker_gets_prompt_cwd_env_and_job_lock(settings, store):
    jid = add_job(store, 1)
    inv = FakeInvoke(settings)
    rec = run(settings, inv)
    c = inv.calls[0]
    assert c["cmd"][-1] == f"/score-job {store.job_dir(jid)}"  # absolute: jobs_dir is outside the root here
    assert c["cwd"] == str(settings.root)
    assert c["env"]["CAREEROS_RUN_ID"] == rec["id"]
    assert c["lock"]["owner"] == f"run:{rec['id']}" and c["env"]["CAREEROS_LOCK_TOKEN"] == c["lock"]["token"]
    assert c["timeout_s"] == 10 * 60
    assert not RunStore(settings).job_lock_path(jid).exists()  # released
    assert not RunStore(settings).runner_lock_path.exists()


@pytest.mark.parametrize("mode,reason", [("usage_limit", "usage_limit"), ("auth", "auth_required"),
                                         ("deny", "permission_denied"), ("timeout", "timeout"),
                                         ("cancel", "cancelled")])
def test_hard_stops_end_the_run_at_once(settings, store, mode, reason):
    a, b = add_job(store, 1, hours_old=60), add_job(store, 2, hours_old=70)
    inv = FakeInvoke(settings, modes={a: mode})
    rec = run(settings, inv)
    assert rec["stop_reason"] == reason and [c["job_id"] for c in inv.calls] == [a]
    assert store.get_status(b) == "found" and store.get_status(a) == "found"
    (att,) = RunStore(settings).load_attempts(rec["id"])
    assert att["outcome"] == reason


def test_timeout_can_be_configured_to_continue(settings, store):
    a, b = add_job(store, 1, hours_old=60), add_job(store, 2, hours_old=70)
    rec = run(settings, FakeInvoke(settings, modes={a: "timeout"}), stop_on_timeout=False)
    assert rec["stop_reason"] == "completed" and rec["counters"]["failed"] == 1
    assert "1 failed" in rec["detail"] and "done" not in rec["detail"]


def test_consecutive_failures(settings, store):
    ids = [add_job(store, i, hours_old=50 + i * 10) for i in range(1, 6)]
    inv = FakeInvoke(settings, default="garbage")
    rec = run(settings, inv, max_consecutive_failures=3)
    assert rec["stop_reason"] == "consecutive_failures" and len(inv.calls) == 3
    assert all(store.get_status(j) == "found" for j in ids)


def test_success_resets_the_failure_streak(settings, store):
    ids = [add_job(store, i, hours_old=50 + i * 10) for i in range(1, 6)]
    modes = {ids[0]: "garbage", ids[1]: "garbage", ids[2]: "prepare", ids[3]: "garbage", ids[4]: "garbage"}
    rec = run(settings, FakeInvoke(settings, modes=modes), max_consecutive_failures=3)
    assert rec["stop_reason"] == "completed" and rec["counters"]["failed"] == 4


def test_time_budget_uses_average_attempt_time(settings, store):
    for i in range(1, 5):
        add_job(store, i, hours_old=50 + i * 10)
    clock = Clock()
    inv = FakeInvoke(settings, clock=clock, step_s=50 * 60)
    rec = run(settings, inv, max_minutes=90, clock=clock)
    assert rec["stop_reason"] == "time_budget" and len(inv.calls) == 1


def test_doctor_failure_stops_before_any_attempt(settings, store):
    add_job(store, 1)
    inv = FakeInvoke(settings)
    rec = run(settings, inv, doctor=lambda root: ["profile still has example data"])
    assert rec["stop_reason"] == "doctor_failed" and inv.calls == []
    assert "example data" in rec["detail"]


def test_busy_runner_lock_raises_and_writes_no_run(settings, store):
    add_job(store, 1)
    rs = RunStore(settings)
    locks.acquire(rs.runner_lock_path, owner="run:other", ttl_seconds=3600)
    with pytest.raises(RunBusy):
        run(settings, FakeInvoke(settings))
    assert rs.list_runs() == []


def test_job_locked_by_someone_else_is_passed_over(settings, store):
    a, b = add_job(store, 1, hours_old=60), add_job(store, 2, hours_old=70)
    locks.acquire(RunStore(settings).job_lock_path(a), owner="prepare-job", ttl_seconds=3600)
    inv = FakeInvoke(settings)
    rec = run(settings, inv)
    assert [c["job_id"] for c in inv.calls] == [b] and rec["counters"]["locked"] == 1


def test_dry_run_writes_queue_only(settings, store):
    add_job(store, 1)
    inv = FakeInvoke(settings)
    rec = run(settings, inv, dry_run=True)
    rs = RunStore(settings)
    assert inv.calls == [] and rs.list_runs() == [] and rec["dry_run"]
    assert rs.load_queue("score")["items"]


def test_paused_stops_before_first_attempt(settings, store):
    add_job(store, 1)
    RunStore(settings).set_pause(until=None, reason="test", now=NOW)
    inv = FakeInvoke(settings)
    rec = run(settings, inv)
    assert rec["stop_reason"] == "paused" and inv.calls == []


def test_expired_pause_is_ignored(settings, store):
    add_job(store, 1)
    RunStore(settings).set_pause(until=NOW - timedelta(minutes=1), reason="test", now=NOW - timedelta(hours=1))
    assert run(settings, FakeInvoke(settings))["stop_reason"] == "completed"


def test_selection_excludes_scored_pruned_filtered_and_underscore_dirs(settings, store):
    keep = add_job(store, 1)
    scored = add_job(store, 2)
    (store.job_dir(scored) / "score.json").write_text("{}")
    pruned = add_job(store, 3, pruned=True)
    senior = add_job(store, 4, title="Senior Backend Software Engineer")
    ex = store.jobs_dir / "_example"
    ex.mkdir()
    (ex / "posting.json").write_text((store.job_dir(keep) / "posting.json").read_text())
    cfg = load_runs_config(settings)
    sel, excluded = select_candidates(settings, "score", cfg, NOW)
    assert [c["job_id"] for c in sel] == [keep]
    why = {e["job_id"]: e["reason"] for e in excluded}
    assert why[pruned] == "pruned" and why[senior].startswith("filtered")
    assert scored not in why and "_example" not in why


def test_dream_company_ranks_first_even_when_older(settings, store):
    plain = add_job(store, 1, hours_old=100)
    dream = add_job(store, 2, hours_old=100, company="Stripe")
    sel, _ = select_candidates(settings, "score", load_runs_config(settings), NOW)
    assert [c["job_id"] for c in sel] == [dream, plain]
    assert "dream company" in sel[0]["why"]


def test_budget_caps_the_in_flight_job_and_stops_as_time_budget(settings, store):
    add_job(store, 1)
    seen = {}

    def slow(cmd, cwd, env, timeout_s, stream_path):
        seen["timeout_s"] = timeout_s
        Path(stream_path).write_text("")
        return HeadlessResult(timed_out=True, exit_code=-15)

    rec = run(settings, slow, max_minutes=0.01)
    assert seen["timeout_s"] == pytest.approx(0.6, abs=0.05)
    assert rec["stop_reason"] == "time_budget"
    (att,) = RunStore(settings).load_attempts(rec["id"])
    assert att["outcome"] == "time_budget"


def test_job_timeout_still_applies_when_the_budget_is_larger(settings, store):
    add_job(store, 1)
    seen = {}

    def slow(cmd, cwd, env, timeout_s, stream_path):
        seen["timeout_s"] = timeout_s
        Path(stream_path).write_text("")
        return HeadlessResult(timed_out=True, exit_code=-15)

    rec = run(settings, slow, max_minutes=90)
    assert seen["timeout_s"] == 10 * 60 and rec["stop_reason"] == "timeout"


# --- lock safety: the runner lock is released whatever the teardown does ----------------------------------------

def _exec(settings, invoke, **kw):
    cfg = cfg_of(settings, preflight_doctor=False)
    return execute_run(settings, "score", budget_for(cfg, "score"), cfg=cfg, invoke=invoke, now=lambda: NOW,
                       clock=Clock(), **kw)


def _boom_invoke(*a, **kw):
    raise RuntimeError("invoke exploded")


def test_raising_finalize_after_a_good_run_surfaces_and_releases_the_lock(settings, store):
    add_job(store, 1)

    def finalize(r):
        raise OSError("pause hook failed")
    with pytest.raises(OSError, match="pause hook failed"):
        _exec(settings, FakeInvoke(settings), finalize=finalize)
    rs = RunStore(settings)
    assert not rs.runner_lock_path.exists()
    (rid,) = [p.name for p in rs.dir.iterdir() if (p / "run.json").exists()]
    assert rs.load_run(rid)["status"] == "done"  # run.json saved before the hook


def test_raising_finalize_does_not_mask_the_original_run_error(settings, store):
    add_job(store, 1)
    seen = []

    def finalize(r):
        seen.append(r["status"])
        raise OSError("pause hook failed")
    with pytest.raises(RuntimeError, match="invoke exploded"):
        _exec(settings, _boom_invoke, finalize=finalize)
    assert seen == ["failed"]
    rs = RunStore(settings)
    assert not rs.runner_lock_path.exists()
    (rid,) = [p.name for p in rs.dir.iterdir() if (p / "run.json").exists()]
    assert "pause hook failed" in (rs.run_dir(rid) / "run.log").read_text()


def _fail_save_from(monkeypatch, n: int):
    """save_run raises from its n-th call on (1 = new_run's first save, 2 = the final run.json save)."""
    real, calls = RunStore.save_run, []

    def save(self, run):
        calls.append(1)
        if len(calls) >= n:
            raise OSError("disk full")
        return real(self, run)
    monkeypatch.setattr(RunStore, "save_run", save)


def test_final_save_run_raising_still_runs_finalize_and_releases_the_lock(settings, store, monkeypatch):
    add_job(store, 1)
    _fail_save_from(monkeypatch, 2)
    seen = []
    with pytest.raises(OSError, match="disk full"):
        _exec(settings, FakeInvoke(settings), finalize=lambda r: seen.append(r["status"]))
    assert seen == ["done"]
    assert not RunStore(settings).runner_lock_path.exists()


def test_raising_save_run_still_releases_the_lock(settings, store, monkeypatch):
    add_job(store, 1)

    def bad_save(self, run):
        raise OSError("disk full")
    monkeypatch.setattr(RunStore, "save_run", bad_save)
    with pytest.raises(OSError, match="disk full"):
        _exec(settings, FakeInvoke(settings))
    assert not RunStore(settings).runner_lock_path.exists()


def test_raising_save_run_does_not_mask_the_original_run_error(settings, store, monkeypatch):
    add_job(store, 1)
    _fail_save_from(monkeypatch, 2)
    with pytest.raises(RuntimeError, match="invoke exploded"):
        _exec(settings, _boom_invoke)
    assert not RunStore(settings).runner_lock_path.exists()


def test_teardown_error_is_warned_when_run_log_is_unwritable(settings, store, monkeypatch):
    add_job(store, 1)
    real_log = RunStore.log

    def log(self, rid, msg):
        if msg.startswith("teardown"):
            raise OSError("log gone")
        return real_log(self, rid, msg)
    monkeypatch.setattr(RunStore, "log", log)

    def finalize(r):
        raise OSError("pause hook failed")
    with pytest.warns(UserWarning, match="pause hook failed"), pytest.raises(RuntimeError, match="invoke exploded"):
        _exec(settings, _boom_invoke, finalize=finalize)
    assert not RunStore(settings).runner_lock_path.exists()


# --- single-job runs (`--job`, `--force`) and the apply kind ---------------------------------------------

def _scored(store: Store, jid: str, tier: str = "C", decision: str = "prepare", status: str = "scored") -> None:
    (store.job_dir(jid) / "score.json").write_text(json.dumps({"job_id": jid, "decision": decision, "fit": 80,
                                                               "tier": tier, "category": "swe_backend"}))
    store.set_status(jid, status, "test")


def _prepared(store: Store, jid: str, qa_pass: bool = True, status: str = "queued", tier: str = "C") -> None:
    _scored(store, jid, tier=tier, status=status)
    (store.job_dir(jid) / "prepare.json").write_text(json.dumps({"job_id": jid, "status": status,
                                                                 "qa_pass": qa_pass}))


def _session(store: Store, jid: str, outcome: str, submit_clicked: bool = False) -> None:
    (store.job_dir(jid) / "apply_session.json").write_text(json.dumps({"job_id": jid, "outcome": outcome,
                                                                       "submit_clicked": submit_clicked}))


def test_job_ids_selects_only_those_jobs_and_keeps_the_ranking(settings, store):
    ids = [add_job(store, i, hours_old=50 + i * 10) for i in range(1, 4)]
    cfg = cfg_of(settings)
    ranked, excluded = select_candidates(settings, "score", cfg, NOW, job_ids=[ids[2], ids[0]])
    assert [r["job_id"] for r in ranked] == [ids[0], ids[2]] and excluded == []


def test_job_ids_reports_why_a_job_is_not_a_candidate(settings, store):
    scored = add_job(store, 1)
    _scored(store, scored)
    pruned = add_job(store, 2, pruned=True)
    cfg = cfg_of(settings)
    ranked, excluded = select_candidates(settings, "score", cfg, NOW, job_ids=[scored, pruned, "nope"])
    assert ranked == []
    assert {e["job_id"]: e["reason"] for e in excluded} == {scored: "status scored", pruned: "pruned",
                                                             "nope": "not found"}


def test_force_reruns_a_scored_or_prepared_job_but_never_the_wrong_status(settings, store):
    from careeros.runs.runner import eligibility

    assert eligibility("score", "found", True, {}, False) == "already scored"  # score.json but status never set
    assert eligibility("score", "found", True, {}, False, force=True) is None
    assert eligibility("score", "scored", True, {}, False) == "status scored"
    assert eligibility("score", "scored", True, {}, False, force=True) is None
    assert eligibility("score", "applied", True, {}, False, force=True) == "status applied"
    assert eligibility("score", "skipped", True, {}, False, force=True) == "status skipped"
    prep = {"decision": "prepare"}
    assert eligibility("prepare", "scored", True, prep, True) == "already prepared"  # prepare.json, status never set
    assert eligibility("prepare", "scored", True, prep, True, force=True) is None
    assert eligibility("prepare", "queued", True, prep, True) == "status queued"
    assert eligibility("prepare", "queued", True, prep, True, force=True) is None
    assert eligibility("prepare", "needs_review", True, prep, False, force=True) is None
    assert eligibility("prepare", "applied", True, prep, True, force=True) == "status applied"
    assert eligibility("prepare", "scored", True, {"decision": "skip"}, False, force=True).startswith("score decision")
    assert eligibility("apply", "applied", True, prep, True, force=True) == "status applied"
    # needs_review is only a Tier A apply candidate (assisted); B/C wait for the human's Approve (status queued)
    assert eligibility("apply", "needs_review", True, {"tier": "A"}, True) is None
    assert eligibility("apply", "needs_review", True, {"tier": "B"}, True) == "status needs_review"
    assert eligibility("apply", "needs_review", True, {"tier": "B"}, True, force=True) == "status needs_review"
    # the browser holds the form (apply_session.json): never refill or re-submit, whatever the status
    for outcome in ("staged", "submitted", "blocked"):
        assert eligibility("apply", "queued", True, prep, True,
                           apply_session={"outcome": outcome}) == f"application {outcome} in the browser"
    assert eligibility("apply", "queued", True, prep, True,
                       apply_session={"outcome": "failed", "submit_clicked": True}) == "submit already clicked"
    assert eligibility("apply", "queued", True, prep, True, apply_session={"outcome": "failed"}) is None


def test_force_selects_an_already_scored_job(settings, store):
    jid = add_job(store, 1)
    _scored(store, jid, status="found")
    cfg = cfg_of(settings)
    assert select_candidates(settings, "score", cfg, NOW, job_ids=[jid])[0] == []
    ranked, _ = select_candidates(settings, "score", cfg, NOW, job_ids=[jid], force=True)
    assert [r["job_id"] for r in ranked] == [jid]


@pytest.mark.parametrize("setup,reason", [
    (lambda s, j: _prepared(s, j), None),
    (lambda s, j: _prepared(s, j, status="prepared"), None),
    (lambda s, j: _prepared(s, j, qa_pass=False), "qa not passed"),
    (lambda s, j: _scored(s, j), "status scored"),
    (lambda s, j: _prepared(s, j, status="applied"), "status applied"),
    (lambda s, j: _prepared(s, j, status="needs_review"), "status needs_review"),  # Tier C: waits for Approve
    (lambda s, j: _prepared(s, j, status="needs_review", qa_pass=False), "status needs_review"),
    (lambda s, j: _prepared(s, j, tier="A"), None),  # Tier A is staged for review, never refused
    (lambda s, j: _prepared(s, j, tier="a", status="needs_review"), None),
    (lambda s, j: _prepared(s, j, tier="B", status="needs_review"), "status needs_review"),  # waits for Approve
    (lambda s, j: (_prepared(s, j, tier="A", status="needs_review"), _session(s, j, "staged")),
     "application staged in the browser"),
    (lambda s, j: (_prepared(s, j), _session(s, j, "submitted")), "application submitted in the browser"),
    (lambda s, j: (_prepared(s, j), _session(s, j, "blocked")), "application blocked in the browser"),
    (lambda s, j: (_prepared(s, j), _session(s, j, "failed", submit_clicked=True)), "submit already clicked"),
    (lambda s, j: (_prepared(s, j), _session(s, j, "failed")), None),  # a failed attempt may be retried
])
def test_apply_eligibility(settings, store, setup, reason):
    jid = add_job(store, 1)
    setup(store, jid)
    ranked, excluded = select_candidates(settings, "apply", cfg_of(settings), NOW, job_ids=[jid], force=True)
    if reason is None:
        assert [r["job_id"] for r in ranked] == [jid]
    else:
        assert ranked == [] and excluded == [{"job_id": jid, "reason": reason}]


def test_batch_apply_skips_tier_b_needs_review_and_staged_jobs_even_with_auto_submit_on(settings, store):
    """A scheduled `run apply` (no --job) never picks a Tier B/C job prepare-job parked in needs_review (only the
    human's Approve moves it to queued) nor a job whose form is already staged in the browser."""
    parked = add_job(store, 1)
    _prepared(store, parked, tier="B", status="needs_review")
    staged = add_job(store, 2)
    _prepared(store, staged, tier="A", status="needs_review")
    _session(store, staged, "staged")
    ready = add_job(store, 3)
    _prepared(store, ready, tier="B")
    cfg = cfg_of(settings, auto_submit={"enabled": True, "allow": ["tier_b", "tier_c"], "manual": ["tier_a"]})
    ranked, _ = select_candidates(settings, "apply", cfg, NOW)
    assert [r["job_id"] for r in ranked] == [ready]


@pytest.mark.parametrize("status", ["queued", "needs_review"])
def test_apply_run_stages_tier_a_with_auto_submit_0_even_when_config_allows(settings, store, status):
    """Tier A is never refused and never auto-submitted: the attempt runs assisted (CAREEROS_AUTO_SUBMIT=0,
    reason names tier_a) and a staged result with status needs_review is accepted."""
    jid = add_job(store, 1)
    _prepared(store, jid, tier="A", status=status)
    _safety(store, jid)
    calls: list = []
    rec = _apply_run(settings, _apply_invoke(store, jid, calls, outcome="staged", status="needs_review"), jid,
                     auto_submit={"enabled": True})
    assert rec["counters"]["ok"] == 1 and len(calls) == 1
    assert calls[0]["CAREEROS_AUTO_SUBMIT"] == "0" and "tier_a" in calls[0]["CAREEROS_AUTO_SUBMIT_REASON"]
    att = RunStore(settings).load_attempts(rec["id"])[0]
    assert att["auto_submit"]["allowed"] is False and att["result"]["outcome"] == "staged"
    assert store.get_status(jid) == "needs_review"


def test_apply_run_calls_apply_job_with_chrome_tools_and_checks_the_status(settings, store):
    jid = add_job(store, 1)
    _prepared(store, jid)

    def invoke(cmd, cwd, env, timeout_s, stream_path):
        Path(stream_path).write_text("{}")
        store.set_status(jid, "applied", "fake apply")
        return parse_stream(events(jid, {"job_id": jid, "outcome": "submitted", "status": "applied"}))

    cfg = cfg_of(settings, preflight_doctor=False)
    rec = execute_run(settings, "apply", budget_for(cfg, "apply", max_jobs=1, max_minutes=30), cfg=cfg,
                      invoke=invoke, now=lambda: NOW, clock=Clock(), job_ids=[jid])
    assert rec["stop_reason"] == "completed" and rec["counters"]["ok"] == 1
    att = RunStore(settings).load_attempts(rec["id"])[0]
    assert att["outcome"] == "ok" and att["result"]["status"] == "applied"
    cmd = rec["cmd"]
    assert cmd[-1] == "/apply-job <job_dir>"
    assert "mcp__claude-in-chrome__*" in cmd[cmd.index("--allowedTools") + 1].split(",")


def test_apply_result_that_lies_about_the_status_is_invalid(settings, store):
    jid = add_job(store, 1)
    _prepared(store, jid)

    def invoke(cmd, cwd, env, timeout_s, stream_path):
        Path(stream_path).write_text("{}")
        return parse_stream(events(jid, {"job_id": jid, "outcome": "submitted", "status": "applied"}))

    cfg = cfg_of(settings, preflight_doctor=False)
    rec = execute_run(settings, "apply", budget_for(cfg, "apply", max_jobs=1, max_minutes=30), cfg=cfg,
                      invoke=invoke, now=lambda: NOW, clock=Clock(), job_ids=[jid])
    att = RunStore(settings).load_attempts(rec["id"])[0]
    assert att["outcome"] == "invalid_result" and "status.json says queued" in att["detail"]


def test_single_job_run_leaves_the_batch_queue_alone(settings, store):
    ids = [add_job(store, i, hours_old=50 + i * 10) for i in range(1, 3)]
    inv = FakeInvoke(settings)
    run(settings, inv, max_jobs=1)  # a batch: writes queue.json
    q_before = RunStore(settings).load_queue("score")
    cfg = cfg_of(settings)
    execute_run(settings, "score", budget_for(cfg, "score", max_jobs=1, max_minutes=30), cfg=cfg, invoke=inv,
                now=lambda: NOW, clock=Clock(), job_ids=[ids[1]])
    assert [c["job_id"] for c in inv.calls] == [ids[0], ids[1]]
    assert RunStore(settings).load_queue("score") == q_before


def test_apply_is_never_a_scheduled_or_batch_kind():
    from careeros.runs import schedule
    from careeros.runs.config import BATCH_KINDS

    assert "apply" not in schedule.JOB_KINDS and "apply" not in schedule.CLAUDE_KINDS
    assert "apply" not in BATCH_KINDS


# --- submit safety, `--force` contract and explicit-run exit semantics -------------------------------------

def _safety(store: Store, jid: str, verdict: str = "pass") -> None:
    (store.job_dir(jid) / "safety.json").write_text(json.dumps({"job_id": jid, "verdict": verdict}))


def _apply_invoke(store: Store, jid: str, calls: list, outcome: str = "submitted", status: str = "applied"):
    def invoke(cmd, cwd, env, timeout_s, stream_path):
        calls.append(dict(env))
        Path(stream_path).write_text("{}")
        store.set_status(jid, status, "fake apply")
        return parse_stream(events(jid, {"job_id": jid, "outcome": outcome, "status": status}))
    return invoke


def _apply_run(settings, invoke, jid, **runs):
    cfg = cfg_of(settings, preflight_doctor=False, **runs)
    return execute_run(settings, "apply", budget_for(cfg, "apply", max_jobs=1, max_minutes=30), cfg=cfg,
                       invoke=invoke, now=lambda: NOW, clock=Clock(), job_ids=[jid])


def test_apply_run_passes_auto_submit_0_with_the_default_config(settings, store):
    jid = add_job(store, 1)
    _prepared(store, jid, tier="B")
    _safety(store, jid)
    calls: list = []
    rec = _apply_run(settings, _apply_invoke(store, jid, calls), jid)
    assert rec["counters"]["ok"] == 1
    assert calls[0]["CAREEROS_AUTO_SUBMIT"] == "0"
    assert calls[0]["CAREEROS_AUTO_SUBMIT_REASON"] == "auto_submit disabled"
    att = RunStore(settings).load_attempts(rec["id"])[0]
    assert att["auto_submit"] == {"allowed": False, "reason": "auto_submit disabled"}


def test_apply_run_passes_auto_submit_1_for_an_allowed_tier_b_job_with_a_safety_pass(settings, store):
    jid = add_job(store, 1)
    _prepared(store, jid, tier="B")
    _safety(store, jid)
    calls: list = []
    _apply_run(settings, _apply_invoke(store, jid, calls), jid, auto_submit={"enabled": True})
    assert calls[0]["CAREEROS_AUTO_SUBMIT"] == "1" and calls[0]["CAREEROS_AUTO_SUBMIT_REASON"] == "allowed: tier_b"


@pytest.mark.parametrize("verdict", [None, "review", "block"])
def test_apply_run_never_passes_auto_submit_1_without_a_safety_pass(settings, store, verdict):
    jid = add_job(store, 1)
    _prepared(store, jid, tier="B")
    if verdict:
        _safety(store, jid, verdict)
    calls: list = []
    _apply_run(settings, _apply_invoke(store, jid, calls), jid, auto_submit={"enabled": True})
    assert calls[0]["CAREEROS_AUTO_SUBMIT"] == "0" and "safety" in calls[0]["CAREEROS_AUTO_SUBMIT_REASON"]


def test_apply_run_accepts_a_staged_result_in_assisted_mode(settings, store):
    jid = add_job(store, 1)
    _prepared(store, jid)
    calls: list = []
    rec = _apply_run(settings, _apply_invoke(store, jid, calls, outcome="staged", status="needs_review"), jid)
    att = RunStore(settings).load_attempts(rec["id"])[0]
    assert att["outcome"] == "ok" and att["result"]["outcome"] == "staged" and rec["counters"]["ok"] == 1


def test_force_without_job_is_rejected_before_anything_runs(settings, store):
    from careeros.runs.service import run_batch

    add_job(store, 1)
    inv = FakeInvoke(settings)
    cfg = cfg_of(settings, preflight_doctor=False)
    with pytest.raises(ValueError, match="--force"):
        run_batch(settings, "score", budget_for(cfg, "score", max_jobs=1, max_minutes=30), cfg=cfg, invoke=inv,
                  force=True)
    assert inv.calls == [] and RunStore(settings).list_runs() == []


def test_explicit_run_refused_by_the_company_gate_is_not_completed(settings, store):
    from careeros.runs.runner import JobNotRunnable

    jid = add_job(store, 1)
    _scored(store, jid)
    inv = FakeInvoke(settings)
    cfg = cfg_of(settings, preflight_doctor=False)
    with pytest.raises(JobNotRunnable) as ei:
        execute_run(settings, "prepare", budget_for(cfg, "prepare", max_jobs=1, max_minutes=30), cfg=cfg,
                    invoke=inv, now=lambda: NOW, clock=Clock(), job_ids=[jid],
                    pre_attempt=lambda item: "company cap: 2 of 2 in 90 days")
    assert ei.value.reasons == {jid: "company cap: 2 of 2 in 90 days"} and inv.calls == []
    runs = RunStore(settings).list_runs()
    assert all(r.get("stop_reason") != "completed" for r in runs)


def test_explicit_run_on_a_locked_job_raises_job_busy_with_the_holder(settings, store):
    from careeros.runs.runner import JobBusy, RunBusy

    jid = add_job(store, 1)
    inv = FakeInvoke(settings)
    cfg = cfg_of(settings, preflight_doctor=False)
    rs = RunStore(settings)
    locks.acquire(rs.job_lock_path(jid), owner="skill:other", pid=os.getpid(), ttl_seconds=600)
    with pytest.raises(JobBusy) as ei:
        execute_run(settings, "score", budget_for(cfg, "score", max_jobs=1, max_minutes=30), cfg=cfg,
                    invoke=inv, now=lambda: NOW, clock=Clock(), job_ids=[jid])
    assert isinstance(ei.value, RunBusy) and ei.value.job_id == jid and ei.value.holder["owner"] == "skill:other"
    assert inv.calls == [] and all(r.get("stop_reason") != "completed" for r in rs.list_runs())
    assert locks.read(rs.runner_lock_path) is None  # the global runner lock is released again
