"""`run_batch`: execute_run plus the policies around it. The CLI and the scheduler call this, not the loop.

- retry: a job that failed on its own (failures.JOB_FAILURES) is retried once in a later run (it gets the
  ranking's retry bonus); when it reaches `runs.retry.max_attempts` it becomes an Action Item (deduped) and
  runs leave it alone. Its status never changes.
- prepare runs: the company gate is checked before each call (a blocked job is passed over, not skipped: the
  skill would record the deferral itself), and with `runs.prepare.stop_at_daily_cap` the run stops once the jobs
  ready to submit (queued) reach today's daily apply cap: preparing more than can be sent today is wasted work.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from careeros.config import Settings
from careeros.runs.config import Budget, RunsConfig, load_runs_config
from careeros.runs.failures import JOB_FAILURES, Failures
from careeros.runs.policy import current_cap, load_prepare_config, load_retry_config
from careeros.runs.runner import SKILLS, execute_run
from careeros.runs.store import RunStore
from careeros.store import Store

READY = ("queued", "prepared")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def gate_check(settings: Settings) -> Callable[[dict[str, Any]], str | None]:
    from careeros.company_policy import Policy, gate, load_records

    policy = Policy.from_settings(settings)

    def check(item: dict[str, Any]) -> str | None:
        try:
            g = gate(item["job_id"], records=load_records(settings), policy=policy)
        except KeyError:
            return None
        return None if g["allowed"] else f"company gate: {g['reason']} ({g['detail']})"

    return check


def daily_cap_stop(settings: Settings) -> Callable[[], tuple[str, str] | None]:
    def check() -> tuple[str, str] | None:
        cap = current_cap(settings)
        store = Store(settings)
        ready = sum(1 for j in store.iter_job_ids() if store.get_status(j) in READY)
        if ready >= cap["remaining"]:
            return "daily_cap", (f"{ready} application(s) ready to submit; today's cap leaves {cap['remaining']} "
                                 f"({cap['applied']}/{cap['cap']} sent)")
        return None

    return check


def run_batch(settings: Settings, kind: str, budget: Budget, *, cfg: RunsConfig | None = None,
              trigger: str = "manual", dry_run: bool = False, invoke=None, doctor=None,
              now: Callable[[], datetime] = _utcnow, clock: Callable[[], float] = time.monotonic, cancel=None,
              echo: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    from careeros.tracker import add_action

    cfg = cfg or load_runs_config(settings)
    retry = load_retry_config(cfg.raw)
    fails = Failures(RunStore(settings))
    max_attempts = retry["max_attempts"]

    def after(att: dict[str, Any]) -> None:
        jid, outcome = att["job_id"], att["outcome"]
        if outcome == "ok":
            fails.clear(kind, jid)
            return
        if outcome not in JOB_FAILURES:
            return
        n = fails.record(kind, jid, outcome, att.get("detail") or "", att["run_id"], now())
        if n >= max_attempts and retry["action_item"]:
            what = (f"careeros run: /{SKILLS[kind]} failed {n} times on job {jid} ({outcome}: "
                    f"{(att.get('detail') or '')[:120]}). Run it by hand or see `careeros run show {att['run_id']}`")
            add_action(settings, what, "other", job_id=jid, priority="M", needs="laptop", dedupe=True)
            echo(f"    {jid}: out of retries -> Action Item")

    extra_stop = None
    pre_attempt = None
    if kind == "prepare":
        pre_attempt = gate_check(settings)
        if load_prepare_config(cfg.raw)["stop_at_daily_cap"]:
            extra_stop = daily_cap_stop(settings)
    return execute_run(settings, kind, budget, cfg=cfg, trigger=trigger, dry_run=dry_run, invoke=invoke,
                       doctor=doctor, now=now, clock=clock, cancel=cancel, echo=echo,
                       retry_ids=fails.retry_ids(kind, max_attempts), skip_ids=fails.exhausted(kind, max_attempts),
                       extra_stop=extra_stop, after_attempt=after, pre_attempt=pre_attempt)


def run_skill(settings: Settings, kind: str, skill: str, *, mcp_servers: list[str] | None = None,
              allowed_tools_extra: list[str] | None = None, trigger: str = "manual", invoke=None, doctor=None,
              now: Callable[[], datetime] = _utcnow, cancel=None,
              echo: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    """One headless call of a skill that is not about a single job (the scheduled inbox_sync). Same runner lock,
    pause, doctor preflight and run records as a batch; `mcp_servers` must be logged in (auth_required if not).
    Stop reason: completed, a hard stop (usage_limit, auth_required, permission_denied, timeout, cancelled),
    paused, doctor_failed, or error (the call failed any other way)."""
    import os
    import uuid
    from dataclasses import replace

    from careeros.runs import locks
    from careeros.runs.headless import build_command, classify, parse_result_line
    from careeros.runs.headless import invoke as default_invoke
    from careeros.runs.runner import RunBusy, default_doctor
    from careeros.runs.store import iso

    base = load_runs_config(settings)
    cfg = replace(base, required_mcp_servers=list(dict.fromkeys([*base.required_mcp_servers, *(mcp_servers or [])])),
                  allowed_tools=list(dict.fromkeys([*base.allowed_tools, *(allowed_tools_extra or [])])))
    if invoke is None:
        def invoke(cmd, cwd, env, timeout_s, stream_path):  # noqa: E306
            return default_invoke(cmd, cwd, env, timeout_s, stream_path, cancel=cancel)
    if doctor is None and cfg.preflight_doctor:
        doctor = default_doctor
    rs = RunStore(settings)
    start = now()
    timeout_s = float(cfg.job_timeout_minutes.get(kind, 20)) * 60
    rid = f"{start.astimezone().strftime('%Y%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:4]}"
    try:
        lk = locks.acquire(rs.runner_lock_path, owner=f"run:{rid}", ttl_seconds=timeout_s + 600, pid=os.getpid(),
                           now=start, note=f"{kind} ({trigger})")
    except locks.LockBusy as e:
        raise RunBusy(e.holder) from None
    run = rs.new_run(kind, trigger, {"preset": None, "max_jobs": 1, "max_minutes": timeout_s / 60}, start,
                     run_id=rid, dry_run=False, cmd=build_command(cfg, f"/{skill}"),
                     counters={"candidates": 1, "attempted": 0, "ok": 0, "failed": 0, "locked": 0, "gated": 0})
    stop, detail = "completed", ""
    try:
        pause = rs.pause_state(start)
        fails = [] if pause else (doctor(settings.root) if doctor else [])
        if pause:
            stop, detail = "paused", f"paused ({pause.get('reason') or 'careeros run pause'})"
        elif fails:
            stop, detail = "doctor_failed", "; ".join(fails)[:500]
        else:
            n, stream_path = rs.next_attempt(rid)
            sid = str(uuid.uuid4())
            env = {**os.environ, "CAREEROS_RUN_ID": rid, "CAREEROS_ROOT": str(settings.root)}
            t0 = now()
            echo(f"[{n}] {kind}: /{skill}")
            res = invoke(build_command(cfg, f"/{skill}", session_id=sid), str(settings.root), env, timeout_s,
                         stream_path)
            outcome, detail = classify(res, cfg, kind, "")
            run["counters"]["attempted"] = 1
            run["counters"]["ok" if outcome == "ok" else "failed"] = 1
            att = {"n": n, "run_id": rid, "job_id": None, "stage": kind, "session_id": res.session_id or sid,
                   "outcome": outcome, "detail": detail,
                   "result": parse_result_line(res.result_text) if res.saw_result else None,
                   "started_at": iso(t0), "ended_at": iso(now()), "duration_s": round(res.duration_s, 1),
                   "stream": f"attempts/{n:03d}.stream.jsonl", "headless": res.summary()}
            rs.save_attempt(rid, att)
            run["attempts"].append(n)
            rs.log(rid, f"attempt {n} {kind} -> {outcome}" + (f": {detail}" if detail else ""))
            if outcome != "ok":
                stop = outcome if outcome in ("usage_limit", "auth_required", "permission_denied", "timeout",
                                              "cancelled") else "error"
    finally:
        end = now()
        run.update(status="done", stop_reason=stop, detail=detail, ended_at=iso(end),
                   duration_s=round((end - start).total_seconds(), 1))
        rs.save_run(run)
        rs.log(rid, f"stop {stop}" + (f": {detail}" if detail else ""))
        locks.release(rs.runner_lock_path, lk.token)
    return run
