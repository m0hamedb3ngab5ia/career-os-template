"""The run loop. Python selects the jobs and enforces the budget; each job is one headless skill call.

execute_run(settings, "score", budget):
  1. rank candidates (ranking.py) and write queue-<kind>.json ("why next"); a dry run stops here
  2. take the global runner lock (busy -> RunBusy, nothing recorded)
  3. preflight: pause (-> paused), `careeros doctor` FAILs (-> doctor_failed)
  4. for each ranked job until the budget is spent: take its job lock (held by someone else -> passed over),
     call the skill headless, classify, record the attempt, release the job lock
  5. stop reason: completed | budget_reached | time_budget | usage_limit | auth_required | permission_denied |
     timeout | consecutive_failures | paused | cancelled | doctor_failed

Jobs the run does not reach keep their status (`found` stays `found`): nothing is bulk-skipped.
After a valid score-job RESULT the runner records the verdict the way prepare-job would: `scored`
(decision prepare) or `skipped` with a note that starts with the skip reason (so `careeros company requeue`
still recognises gate deferrals). A job whose status the skill already moved (e.g. a safety block set
`needs_review`) is left alone.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from careeros.config import Settings
from careeros.runs import locks
from careeros.runs.config import Budget, RunsConfig, load_runs_config
from careeros.runs.headless import HARD_STOPS, HeadlessResult, build_command, classify, parse_result_line
from careeros.runs.headless import invoke as default_invoke
from careeros.runs.ranking import Candidate, fit_first_within_company, rank
from careeros.runs.store import RunStore, iso
from careeros.store import Store

SKILLS = {"score": "score-job", "prepare": "prepare-job"}
STOP_REASONS = ("completed", "budget_reached", "time_budget", "usage_limit", "auth_required", "permission_denied",
                "timeout", "consecutive_failures", "daily_cap", "paused", "cancelled", "doctor_failed")
# Stops that mean "nothing wrong, the run did its job": the CLI exits 0 on these.
CLEAN_STOPS = ("completed", "budget_reached", "time_budget", "daily_cap", "paused", "cancelled")


class RunBusy(RuntimeError):
    def __init__(self, holder: dict[str, Any]):
        self.holder = holder
        super().__init__(f"another run is already running ({holder.get('owner')}, pid {holder.get('pid')}, "
                         f"started {holder.get('acquired_at')})")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.fromisoformat(str(v)[:10])
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def default_doctor(root: Path) -> list[str]:
    """FAIL lines of `careeros doctor` for this root (empty = ready)."""
    from careeros.doctor import FAIL, run_doctor

    return [f"{c.name}: {c.detail}" for c in run_doctor(root) if c.level == FAIL]


# --------------------------------------------------------------------------------------------------------
# selection
# --------------------------------------------------------------------------------------------------------

def _prefilter(settings: Settings):
    from careeros.safety import registry
    from careeros.scout import Prefilter, scout_config

    try:
        flagged = registry.load(registry.default_path(settings))
    except Exception:  # noqa: BLE001 - a broken registry must not stop ranking; scout reports it
        flagged = []
    return Prefilter(settings, flagged=flagged, filters=scout_config(settings)["filters"])


def eligibility(kind: str, status: str, has_score: bool, score: dict[str, Any], prepared_ok: bool) -> str | None:
    """Why a job is not a candidate for this kind of run (None = it is). Only job-state rules; the scout
    filters and the pruned check run separately."""
    if kind == "score":
        if status != "found":
            return "status"
        return "already scored" if has_score else None
    if status not in ("found", "scored"):
        return "status"
    if not has_score:
        return "not scored"
    if score.get("decision") != "prepare" and status != "scored":
        return f"score decision {score.get('decision')}"
    return "already prepared" if prepared_ok else None


def select_candidates(settings: Settings, kind: str, cfg: RunsConfig, now: datetime,
                      retry_ids: set[str] | None = None, skip_ids: dict[str, str] | None = None,
                      ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(ranked candidates, excluded [{job_id, reason}]). Excluded lists only jobs that would otherwise be
    candidates (pruned postings, scout filters that now fail, `skip_ids`), not every other status."""
    from careeros.company_policy import posting_closes_at

    store = Store(settings)
    pre = _prefilter(settings)
    retry_ids, skip_ids = retry_ids or set(), skip_ids or {}
    cands: list[Candidate] = []
    excluded: list[dict[str, Any]] = []
    for jid in store.iter_job_ids():
        status = store.get_status(jid) or "found"
        score = store._read(jid, "score.json") or {}
        prep = store._read(jid, "prepare.json") or {}
        if eligibility(kind, status, bool(score) or (store.job_dir(jid) / "score.json").exists(), score,
                       bool(prep.get("qa_pass"))):
            continue
        raw = store._read(jid, "posting.json") or {}
        if raw.get("pruned"):
            excluded.append({"job_id": jid, "reason": "pruned"})
            continue
        p = store.load_posting(jid)
        if p is None:
            continue
        ok, why, _ = pre.check(p)
        if not ok:
            excluded.append({"job_id": jid, "reason": f"filtered: {why}"})
            continue
        if jid in skip_ids:
            excluded.append({"job_id": jid, "reason": skip_ids[jid]})
            continue
        fit = score.get("fit")
        cands.append(Candidate(
            job_id=jid, company=p.company, title=p.title, status=status,
            posted_at=_parse_dt(p.first_published or p.posted_at or p.fetched_at),
            closes_at=posting_closes_at(p), dream=settings.is_dream(p.company),
            fit=int(fit) if isinstance(fit, (int, float)) and not isinstance(fit, bool) else None,
            retry=jid in retry_ids))
    ranked = rank(cands, cfg.ranking, now, stage=kind)
    if kind == "prepare":
        ranked = fit_first_within_company(ranked)
    return ranked, excluded


# --------------------------------------------------------------------------------------------------------
# the loop
# --------------------------------------------------------------------------------------------------------

def _job_arg(root: Path, job_dir: Path) -> str:
    try:
        return str(job_dir.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(job_dir)


def _record_score_verdict(settings: Settings, store: Store, job_id: str, res: dict[str, Any], run_id: str) -> None:
    from careeros.tracker import set_status_both

    if (store.get_status(job_id) or "found") != "found":
        return  # the skill (or its safety gate) already moved it
    if res.get("decision") == "prepare":
        set_status_both(settings, job_id, "scored", f"score-job fit={res.get('fit')} (run {run_id})")
    else:
        reason = res.get("skip_reason") or (res.get("hard_filter_fails") or ["skip"])[0]
        set_status_both(settings, job_id, "skipped", f"{reason}: score-job (run {run_id})"[:200])


class _Loop:
    def __init__(self, settings: Settings, kind: str, budget: Budget, cfg: RunsConfig, rs: RunStore,
                 run: dict[str, Any], invoke: Callable[..., HeadlessResult], now: Callable[[], datetime],
                 clock: Callable[[], float], cancel: threading.Event | None, echo: Callable[[str], None],
                 after_attempt: Callable[[dict[str, Any]], None] | None):
        self.s, self.kind, self.budget, self.cfg, self.rs, self.run = settings, kind, budget, cfg, rs, run
        self.invoke, self.now, self.clock, self.cancel, self.echo = invoke, now, clock, cancel, echo
        self.after_attempt = after_attempt
        self.store = Store(settings)
        self.c = run["counters"]
        self.durations: list[float] = []

    def attempt(self, item: dict[str, Any]) -> dict[str, Any]:
        jid = item["job_id"]
        n, stream_path = self.rs.next_attempt(self.run["id"])
        prompt = f"/{SKILLS[self.kind]} {_job_arg(self.s.root, self.store.job_dir(jid))}"
        sid = str(uuid.uuid4())
        cmd = build_command(self.cfg, prompt, session_id=sid)
        job_s = float(self.cfg.job_timeout_minutes[self.kind]) * 60
        left_s = float(self.budget.max_minutes) * 60 - (self.clock() - self.t_start)
        timeout_s = max(1e-3, min(job_s, left_s))  # the run's time budget also caps the job in flight
        budget_bound = left_s < job_s
        lock = locks.acquire(self.rs.job_lock_path(jid), owner=f"run:{self.run['id']}", pid=os.getpid(),
                             ttl_seconds=job_s + 300, note=f"{self.kind} {jid}")
        env = {**os.environ, "CAREEROS_RUN_ID": self.run["id"], "CAREEROS_LOCK_TOKEN": lock.token,
               "CAREEROS_ROOT": str(self.s.root)}
        started, t0 = self.now(), self.clock()
        self.echo(f"[{n}] {self.kind} {jid} {item.get('company', '')} — {item.get('title', '')}")
        try:
            res = self.invoke(cmd, str(self.s.root), env, timeout_s, stream_path)
        finally:
            locks.release(self.rs.job_lock_path(jid), lock.token)
        took = self.clock() - t0
        self.durations.append(took)
        outcome, detail = classify(res, self.cfg, self.kind, jid)
        if outcome == "timeout" and budget_bound:
            outcome, detail = "time_budget", f"stopped at the run's {self.budget.max_minutes:g}-minute budget"
        result = parse_result_line(res.result_text) if res.saw_result else None
        if outcome == "ok" and self.kind == "score" and result:
            _record_score_verdict(self.s, self.store, jid, result, self.run["id"])
        att = {"n": n, "run_id": self.run["id"], "job_id": jid, "company": item.get("company"),
               "title": item.get("title"), "stage": self.kind, "rank": item.get("rank"), "why": item.get("why"),
               "session_id": res.session_id or sid, "outcome": outcome, "detail": detail, "result": result,
               "started_at": iso(started), "ended_at": iso(self.now()), "duration_s": round(took, 1),
               "stream": f"attempts/{n:03d}.stream.jsonl", "headless": res.summary()}
        self.rs.save_attempt(self.run["id"], att)
        self.run["attempts"].append(n)
        self.rs.log(self.run["id"], f"attempt {n} {self.kind} {jid} -> {outcome}" + (f": {detail}" if detail else ""))
        self.echo(f"    -> {outcome}" + (f": {detail}" if detail else ""))
        if self.after_attempt:
            self.after_attempt(att)
        return att

    def stop_before_next(self) -> tuple[str, str] | None:
        if self.cancel is not None and self.cancel.is_set():
            return "cancelled", "cancelled by signal"
        p = self.rs.pause_state(self.now())
        if p:
            return "paused", f"paused ({p.get('reason') or 'careeros run pause'})"
        elapsed = self.clock() - self.t_start
        limit = float(self.budget.max_minutes) * 60
        avg = sum(self.durations) / len(self.durations) if self.durations else 0.0
        if elapsed >= limit or (self.durations and elapsed + avg > limit):
            return "time_budget", f"{elapsed / 60:.0f} of {self.budget.max_minutes} min used"
        return None

    def go(self, ranked: list[dict[str, Any]], extra_stop: Callable[[], tuple[str, str] | None] | None = None,
           ) -> tuple[str, str]:
        self.t_start = self.clock()
        streak = 0
        for item in ranked:
            if self.c["attempted"] >= self.budget.max_jobs:
                return "budget_reached", f"{self.budget.max_jobs} job(s) done; {len(ranked) - self.c['attempted'] - self.c['locked']} left for later"
            stop = self.stop_before_next() or (extra_stop() if extra_stop else None)
            if stop:
                return stop
            try:
                att = self.attempt(item)
            except locks.LockBusy as e:
                self.c["locked"] += 1
                self.rs.log(self.run["id"], f"skip {item['job_id']}: locked by {e.holder.get('owner')}")
                self.echo(f"    {item['job_id']} locked by {e.holder.get('owner')}; passed over")
                continue
            self.c["attempted"] += 1
            outcome = att["outcome"]
            if outcome == "ok":
                self.c["ok"] += 1
                streak = 0
            else:
                self.c["failed"] += 1
                streak += 1
            if outcome in HARD_STOPS or outcome == "time_budget":
                return outcome, att["detail"]
            if outcome == "timeout" and self.cfg.stop_on_timeout:
                return "timeout", att["detail"]
            if outcome != "ok" and streak >= self.cfg.max_consecutive_failures:
                return "consecutive_failures", f"{streak} failures in a row (last: {outcome}: {att['detail']})"
            locks.refresh(self.rs.runner_lock_path, self.lock_token, self.lock_ttl, now=self.now())
        return "completed", f"{self.c['attempted']} job(s) done, nothing left in the queue"


def execute_run(settings: Settings, kind: str, budget: Budget, *, cfg: RunsConfig | None = None,
                trigger: str = "manual", dry_run: bool = False, invoke: Callable[..., HeadlessResult] | None = None,
                doctor: Callable[[Path], list[str]] | None = None, now: Callable[[], datetime] = _utcnow,
                clock: Callable[[], float] = time.monotonic, cancel: threading.Event | None = None,
                echo: Callable[[str], None] = lambda s: None, retry_ids: set[str] | None = None,
                skip_ids: dict[str, str] | None = None,
                extra_stop: Callable[[], tuple[str, str] | None] | None = None,
                after_attempt: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Run one budgeted batch. Returns run.json (or, for a dry run, the would-be selection). RunBusy when
    another run holds the global lock."""
    cfg = cfg or load_runs_config(settings)
    rs = RunStore(settings)
    t_now = now()
    ranked, excluded = select_candidates(settings, kind, cfg, t_now, retry_ids=retry_ids, skip_ids=skip_ids)
    rs.write_queue(kind, ranked, excluded, t_now)
    if dry_run:
        return {"dry_run": True, "kind": kind, "budget": budget.to_dict(), "candidates": len(ranked),
                "selected": ranked[:budget.max_jobs], "excluded": excluded}
    if invoke is None:
        def invoke(cmd, cwd, env, timeout_s, stream_path):  # noqa: E306
            return default_invoke(cmd, cwd, env, timeout_s, stream_path, cancel=cancel)
    if doctor is None and cfg.preflight_doctor:
        doctor = default_doctor
    rid = f"{t_now.astimezone().strftime('%Y%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:4]}"
    ttl = float(budget.max_minutes) * 60 + float(cfg.job_timeout_minutes[kind]) * 60 + 600
    try:
        glock = locks.acquire(rs.runner_lock_path, owner=f"run:{rid}", ttl_seconds=ttl, pid=os.getpid(), now=t_now,
                              note=f"{kind} ({trigger})")
    except locks.LockBusy as e:
        raise RunBusy(e.holder) from None
    run = rs.new_run(kind, trigger, budget.to_dict(), t_now, run_id=rid, dry_run=False,
                     cmd=build_command(cfg, f"/{SKILLS[kind]} <job_dir>"),
                     counters={"candidates": len(ranked), "attempted": 0, "ok": 0, "failed": 0, "locked": 0},
                     queue=[{k: r[k] for k in ("job_id", "rank", "score", "why")} for r in ranked[:budget.max_jobs]])
    rs.log(rid, f"start {kind} ({trigger}) budget={budget.to_dict()} candidates={len(ranked)}")
    loop = _Loop(settings, kind, budget, cfg, rs, run, invoke, now, clock, cancel, echo, after_attempt)
    loop.lock_token, loop.lock_ttl = glock.token, ttl
    status = "done"
    try:
        pause = rs.pause_state(t_now)
        if pause:
            stop, detail = "paused", f"paused ({pause.get('reason') or 'careeros run pause'})"
        else:
            fails = doctor(settings.root) if doctor else []
            if fails:
                stop, detail = "doctor_failed", "; ".join(fails)[:500]
            else:
                stop, detail = loop.go(ranked, extra_stop)
    except BaseException as e:
        status, stop, detail = "failed", "error", f"{type(e).__name__}: {e}"[:500]
        raise
    finally:
        end = now()
        run.update(status=status, stop_reason=stop, detail=detail, ended_at=iso(end),
                   duration_s=round((end - t_now).total_seconds(), 1))
        rs.save_run(run)
        rs.log(rid, f"stop {stop}" + (f": {detail}" if detail else ""))
        locks.release(rs.runner_lock_path, glock.token)
    return run
