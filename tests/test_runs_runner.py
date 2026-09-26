"""The run loop with a fake headless invoker (no subprocess, no claude): selection, budgets, stop reasons,
locks, run records."""
from __future__ import annotations

import json
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
