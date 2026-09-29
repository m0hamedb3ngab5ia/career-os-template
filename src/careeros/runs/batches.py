"""Batches: a named selection of jobs taken up to one stop point, run as a queue of per-job runs.

The model and preview: which jobs can go, from which stage, in which order, and why the others cannot. The
driver (`drive`, `careeros batch run <id>`) works the queue: one `run_batch(kind, job_ids=[id])` per job and
stage, each under the global runner lock, and maps each outcome to a job state. Hard rules, not configurable:
Tier A is never auto-submitted, LinkedIn is never automated (excluded from fill/submit, re-checked before each
apply run), apply is one job per run, and a batch may only narrow `runs.auto_submit` (the verdict is re-run right
before each apply run; a no turns auto-submit off for that run only).
Single writer: batch status and job states are written only by whoever holds `<id>.lock` (the driver while it
runs; pause / cancel / retry only while no driver runs, else they leave a request the driver reads between steps).
Files: `<runs_dir>/batches/<id>.json`, `<id>.lock`, `<id>.request`.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from careeros.config import Settings
from careeros.runs import locks
from careeros.runs.config import Budget, RunsConfig, load_runs_config
from careeros.runs.failures import JOB_FAILURES
from careeros.runs.runner import JobNotRunnable, RunBusy, auto_submit_verdict, new_run_id, select_candidates
from careeros.runs.store import RunStore, _dump, _load, iso, runs_dir_for
from careeros.store import Store

# stop point -> the run kinds it walks through, in order ("fill" = apply with auto-submit forced off)
STOP_POINTS = {"score": ("score",), "prepare": ("score", "prepare"), "fill": ("score", "prepare", "apply"),
               "submit": ("score", "prepare", "apply")}
MAX_JOBS = 500
_ID = re.compile(r"[\w-]{1,80}")
# reasons found after the job-state rules passed: more telling than a later stage's "status found"
# ponytail: these strings mirror the free-text reasons in runner.select_candidates; a rename there silently breaks this
_HARD = ("not found", "pruned", "posting.json unreadable")


def _hard(reason: str) -> bool:
    return reason in _HARD or reason.startswith("filtered:")


def _dir(settings: Settings) -> Path:
    return runs_dir_for(settings) / "batches"


def is_linkedin(posting: dict[str, Any]) -> bool:
    urls = f"{posting.get('url') or ''} {posting.get('apply_url') or ''}".lower()
    return str(posting.get("ats") or "").lower() == "linkedin" or "linkedin.com" in urls


def preview(settings: Settings, job_ids: list[str], stop_at: str, now: datetime | None = None) -> dict[str, Any]:
    """{stop_at, kind, selected, excluded}. Each selected job starts at the first stage it is eligible for and
    runs every later stage up to the stop point (`stages`); excluded jobs carry the reason.

    `auto_submit` is only a provisional verdict, computed for jobs already at the apply stage; earlier-stage jobs
    have no score/safety files yet, so they get False ("decided at apply"). The driver MUST re-run
    `auto_submit_verdict` and the LinkedIn check right before each apply run and never trust the saved flag."""
    if stop_at not in STOP_POINTS:
        raise ValueError(f"stop_at must be one of {', '.join(STOP_POINTS)}")
    ids = list(dict.fromkeys(job_ids or []))
    if not ids:
        raise ValueError("pick at least one job")
    if len(ids) > MAX_JOBS:
        raise ValueError(f"at most {MAX_JOBS} jobs per batch")
    now = now or datetime.now(timezone.utc)
    kinds = STOP_POINTS[stop_at]
    store, cfg = Store(settings), load_runs_config(settings)
    excluded: dict[str, str] = {}
    if "apply" in kinds:  # LinkedIn is never automated: the candidate applies there by hand
        for jid in ids:
            if is_linkedin(store._read(jid, "posting.json") or {}):
                excluded[jid] = "LinkedIn: apply yourself on LinkedIn"
    remaining = [j for j in ids if j not in excluded]
    selected: list[dict[str, Any]] = []
    for i, kind in enumerate(kinds):
        if not remaining:
            break
        ranked, out = select_candidates(settings, kind, cfg, now, job_ids=remaining)
        for r in ranked:
            selected.append({**r, "stage": kind, "stages": list(kinds[i:])})
        for e in out:  # a later stage's reason wins, except one found after the job-state rules passed
            if not _hard(excluded.get(e["job_id"], "")):
                excluded[e["job_id"]] = e["reason"]
        done = {r["job_id"] for r in ranked}
        remaining = [j for j in remaining if j not in done and not _hard(excluded.get(j, ""))]
    # ponytail: stage scores differ in weights (fit counts only for prepare); one merged sort is good enough
    selected.sort(key=lambda r: (-r["score"], r["job_id"]))
    for n, r in enumerate(selected, 1):
        r["rank"] = n
        excluded.pop(r["job_id"], None)
        if stop_at != "submit":
            ok, why = False, f"stop point {stop_at}: never submits"
        elif r["stage"] != "apply":
            ok, why = False, "decided at apply"
        else:
            ok, why = auto_submit_verdict(settings, store, cfg, r)
        r["auto_submit"], r["submit_reason"] = ok, why
    return {"stop_at": stop_at, "kind": kinds[-1], "selected": selected,
            "excluded": [{"job_id": j, "reason": excluded[j]} for j in ids if j in excluded]}


def job_runs(batch: dict[str, Any]) -> list[dict[str, Any]]:
    """The batch as the queue of runs the driver makes: one job per run, stages in order. `auto_submit` is
    true only on an apply run whose job the policy allows (never Tier A, never below stop point `submit`)."""
    return [{"job_id": r["job_id"], "kind": k, "job_ids": [r["job_id"]],
             "auto_submit": bool(r["auto_submit"]) and k == "apply"}
            for r in batch["selected"] for k in r["stages"]]


def create(settings: Settings, job_ids: list[str], stop_at: str, name: str | None = None, dry_run: bool = False,
           now: datetime | None = None) -> dict[str, Any]:
    """The preview (dry run), or a saved batch in status `queued` (ValueError when no job can run).

    The driver must hold the runner lock while working a batch, and be the single writer of batch status."""
    now = now or datetime.now(timezone.utc)
    out = preview(settings, job_ids, stop_at, now)
    if dry_run:
        return {**out, "dry_run": True}
    if not out["selected"]:
        reasons = "; ".join(f"{e['job_id']}: {e['reason']}" for e in out["excluded"][:5])
        raise ValueError(f"no job in this selection can run ({reasons})")
    local = now.astimezone()
    batch = {"id": new_run_id("batch", now), "name": (name or "").strip() or f"Batch — {local:%b} {local.day}",
             "created_at": iso(now), "status": "queued", "dry_run": False, **out}
    for r in batch["selected"]:
        r["state"] = "pending"
    _dump(_dir(settings) / f"{batch['id']}.json", batch)
    return batch


def load(settings: Settings, batch_id: str) -> dict[str, Any] | None:
    if not _ID.fullmatch(batch_id or ""):
        return None
    return _load(_dir(settings) / f"{batch_id}.json")


def list_ids(settings: Settings) -> list[str]:
    d = _dir(settings)
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


# --- driver ------------------------------------------------------------------------------------------------------
# job states: pending, waiting (runner busy), working, done, needs_you, skipped, failed, cancelled
# batch status: queued, running, paused, cancelled, done
PAUSE_OUTCOMES = ("usage_limit", "auth_required", "permission_denied")  # the whole tool, not the job
PAUSE_STOPS = ("paused", "doctor_failed")
REVIEW = ("status needs_review", "qa not passed", "submit already clicked", "application ")
FINISHED = ("already scored", "already prepared")
RESULT = {"score": "scored", "prepare": "prepared"}
OPEN = ("pending", "waiting", "working", None)
LOCK_TTL_S = 24 * 3600  # renewed before each job
MAX_TRIES = 50  # real runs per stage; retries are capped by Failures first


class BatchBusy(RuntimeError):
    pass


def _lock_path(settings: Settings, batch_id: str) -> Path:
    return _dir(settings) / f"{batch_id}.lock"


def _req_path(settings: Settings, batch_id: str) -> Path:
    return _dir(settings) / f"{batch_id}.request"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def bucket(kind: str, outcome: str | None, stop_reason: str | None,
           session: dict[str, Any] | None = None) -> tuple[str, str]:
    """(action, reason) for one per-job run: next (stage done, go on), done, needs_you, failed (the job's own
    failure: retried while `retry.max_attempts` allows), cancelled, skipped, or pause (the whole batch)."""
    if stop_reason in PAUSE_STOPS or outcome in PAUSE_OUTCOMES:
        return "pause", f"{outcome or stop_reason}: batch paused"
    if outcome == "cancelled" or stop_reason == "cancelled":
        return "cancelled", "cancelled"
    if outcome in JOB_FAILURES:
        return "failed", outcome
    if outcome != "ok":
        return "skipped", f"not run ({stop_reason})"
    if kind != "apply":
        return "next", RESULT[kind]
    got = (session or {}).get("outcome")
    if got == "submitted":
        return "done", "submitted"
    if got == "staged":
        return "needs_you", "staged: review and submit it yourself"
    if got == "blocked":
        return "needs_you", "blocked: finish it by hand"
    return "needs_you", "application filled; check it in the browser"


def not_runnable(reason: str) -> tuple[str, str]:
    """(action, reason) for a stage the runner refused (JobNotRunnable)."""
    if reason.startswith(FINISHED):
        return "next", reason
    if reason.startswith(REVIEW):
        return "needs_you", f"needs your review ({reason})"
    if reason.startswith("failed "):
        return "failed", reason  # out of retries: runs.retry left an Action Item
    return "skipped", reason


def _no_submit(cfg: RunsConfig) -> RunsConfig:
    """Narrow only: the same config with auto-submit off (apply-job gets CAREEROS_AUTO_SUBMIT=0)."""
    raw = dict(cfg.raw)
    raw["auto_submit"] = {**(raw.get("auto_submit") or {}), "enabled": False}
    return replace(cfg, raw=raw)


def _take_request(settings: Settings, batch_id: str) -> str | None:
    p = _req_path(settings, batch_id)
    try:
        req = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    p.unlink(missing_ok=True)
    return req


def _job_stages(settings: Settings, b: dict[str, Any], r: dict[str, Any], cfg: RunsConfig, run, *,
                invoke, now, cancel, echo, sleep, poll_s, stop, paused=lambda: False) -> str | None:
    """Work one job's remaining stages; sets r["state"], r["reason"]. Returns "cancel", "pause: <why>" or None."""
    store, jid = Store(settings), r["job_id"]
    stages = r["stages"]
    for kind in stages[stages.index(r["stage"]):]:
        r["stage"] = kind
        budget = Budget("batch", 1, 2 * float(cfg.job_timeout_minutes.get(kind, 20)))  # room for the one job
        tries = 0
        while True:  # a run, a retry (capped by Failures, then MAX_TRIES) or a wait while the runner is busy
            if stop():
                return "cancel"
            c = cfg
            if kind == "apply":  # never trust the saved preview (or an earlier pass): re-check right before the run
                if is_linkedin(store._read(jid, "posting.json") or {}):
                    r["state"], r["reason"] = "needs_you", "LinkedIn: apply yourself on LinkedIn"
                    return None
                ok, why = (auto_submit_verdict(settings, store, cfg, r) if b["stop_at"] == "submit"
                           else (False, f"stop point {b['stop_at']}: never submits"))
                r["auto_submit"], r["submit_reason"] = ok, why
                if not ok:
                    c = _no_submit(cfg)
            try:
                rec = run(settings, kind, budget, cfg=c, trigger="batch", invoke=invoke, now=now, cancel=cancel,
                          echo=echo, job_ids=[jid])
            except JobNotRunnable as e:
                action, why = not_runnable(e.reasons.get(jid, str(e)))
            except RunBusy as e:  # another run (or a JobBusy job lock): wait for it, not counted as a try
                if paused():
                    r["state"], r["reason"] = "pending", "paused by you"
                    return "pause: paused by you"
                r["state"], r["reason"] = "waiting", str(e)[:200]
                sleep(poll_s)
                continue
            else:
                tries += 1
                atts = RunStore(settings).load_attempts(rec["id"]) if rec.get("id") else []
                outcome = atts[-1]["outcome"] if atts else None
                session = store._read(jid, "apply_session.json") if kind == "apply" else None
                action, why = bucket(kind, outcome, rec.get("stop_reason"), session)
                r["run_ids"] = [*r.get("run_ids", []), rec.get("id")]
            r["state"], r["reason"] = "working", why
            if action == "failed" and not why.startswith("failed "):
                if tries < MAX_TRIES:
                    continue  # attempts left: run it again (the runner refuses it once out of retries)
                action, why = "failed", f"gave up after {MAX_TRIES} tries"
            break
        if action == "next":
            r["result"] = RESULT.get(kind, why)
            continue
        if action == "pause":
            r["state"], r["reason"] = "pending", why
            return f"pause: {why}"
        r["state"], r["reason"] = action, why
        return "cancel" if action == "cancelled" else None
    if stages[-1] == "prepare" and store.get_status(jid) == "needs_review":
        r["state"], r["reason"] = "needs_you", "needs your review"
    else:
        r["state"], r["reason"] = "done", r.get("result") or "done"
    return None


def drive(settings: Settings, batch_id: str, *, invoke=None, now=_utcnow, cancel=None,
          echo=lambda s: None, sleep=time.sleep, poll_s: float = 10.0, run=None) -> dict[str, Any]:
    """Work the batch's queue, one job at a time, each stage its own per-job run (`run_batch`, which takes the
    global runner lock). Pause (a request, `careeros run pause`, or a usage/auth/permission stop) takes effect
    after the current job; cancel after the current step. BatchBusy when a driver already holds the batch."""
    from careeros.runs.service import run_batch

    run = run or run_batch
    if load(settings, batch_id) is None:
        raise ValueError(f"batch {batch_id} not found")
    try:
        lk = locks.acquire(_lock_path(settings, batch_id), owner=f"batch:{batch_id}", ttl_seconds=LOCK_TTL_S,
                           pid=os.getpid(), note="batch driver")
    except locks.LockBusy as e:
        raise BatchBusy(f"batch {batch_id} is already running (pid {e.holder.get('pid')})") from None
    # load under the lock (a control / retry may have written it meanwhile); a request left from an earlier
    # driver or control is stale now: only requests made while this driver runs count
    _req_path(settings, batch_id).unlink(missing_ok=True)
    b = load(settings, batch_id)
    if b is None:
        locks.release(_lock_path(settings, batch_id), lk.token)
        raise ValueError(f"batch {batch_id} not found")
    rs, path, reqs = RunStore(settings), _dir(settings) / f"{batch_id}.json", []

    def stop() -> bool:
        req = _take_request(settings, batch_id)
        if req:
            reqs.append(req)
        return (cancel is not None and cancel.is_set()) or "cancel" in reqs

    def paused() -> bool:
        return "pause" in reqs

    def save() -> None:
        b["updated_at"] = iso(now())
        _dump(path, b)

    try:
        if b["status"] in ("done", "cancelled"):
            return b
        cfg = load_runs_config(settings)
        b["status"], b["reason"] = "running", None
        save()
        for r in b["selected"]:
            if r.get("state") not in OPEN:
                continue
            halt = "cancel" if stop() else None
            pause = rs.pause_state(now())
            if not halt and ("pause" in reqs or pause):
                halt = "pause: " + ("paused by you" if "pause" in reqs else
                                    f"runs paused ({(pause or {}).get('reason') or 'careeros run pause'})")
            if not halt:
                locks.refresh(_lock_path(settings, batch_id), lk.token, LOCK_TTL_S)
                r["state"] = "working"
                save()
                echo(f"batch {batch_id}: {r['job_id']} {'>'.join(r['stages'])}")
                halt = _job_stages(settings, b, r, cfg, run, invoke=invoke, now=now, cancel=cancel, echo=echo,
                                   sleep=sleep, poll_s=poll_s, stop=stop, paused=paused)
            if halt == "cancel":
                _cancel_rest(b)
                break
            if halt:
                b["status"], b["reason"] = "paused", halt.removeprefix("pause: ")
                break
            save()
        else:
            b["status"] = "done"
    finally:
        if b["status"] == "running":  # crashed mid-job: resumable with `careeros batch run`
            b["status"], b["reason"] = "paused", "driver stopped"
        save()
        locks.release(_lock_path(settings, batch_id), lk.token)
    return b


def _cancel_rest(b: dict[str, Any]) -> None:
    for r in b["selected"]:
        if r.get("state") in OPEN:
            r["state"], r["reason"] = "cancelled", "batch cancelled"
    b["status"], b["reason"] = "cancelled", None


def _locked(settings: Settings, batch_id: str):
    """(batch, lock) when no driver runs, else (batch, None)."""
    b = load(settings, batch_id)
    if b is None:
        raise ValueError(f"batch {batch_id} not found")
    try:
        return b, locks.acquire(_lock_path(settings, batch_id), owner="batch:control", ttl_seconds=60,
                                pid=os.getpid())
    except locks.LockBusy:
        return b, None


def running(settings: Settings, batch_id: str) -> bool:
    """A live driver holds the batch lock (a stale lock, e.g. a crashed driver, does not count)."""
    info = locks.read(_lock_path(settings, batch_id))
    return bool(info) and not locks.is_stale(info, _utcnow())


def control(settings: Settings, batch_id: str, action: str, now: datetime | None = None) -> dict[str, Any]:
    """pause | cancel. With a driver running: a request it acts on (pause after the current job, cancel after
    the current step). Without one: applied here, under the batch lock."""
    if action not in ("pause", "cancel"):
        raise ValueError("action must be pause or cancel")
    b, lk = _locked(settings, batch_id)
    if lk is None:
        _req_path(settings, batch_id).write_text(action, encoding="utf-8")
        return {**b, "requested": action}
    try:
        if b["status"] not in ("done", "cancelled"):
            if action == "cancel":
                _cancel_rest(b)
            else:
                b["status"], b["reason"] = "paused", "paused by you"
            b["updated_at"] = iso(now or _utcnow())
            _dump(_dir(settings) / f"{batch_id}.json", b)
        _req_path(settings, batch_id).unlink(missing_ok=True)
        return b
    finally:
        locks.release(lk.path, lk.token)


def retry(settings: Settings, batch_id: str, job_ids: list[str] | None = None,
          now: datetime | None = None) -> dict[str, Any]:
    """Put failed and cancelled jobs back in the queue (`careeros batch run` works them again). The driver
    already retried a failed job up to `runs.retry.max_attempts`; this explicit retry resets its count (as
    `careeros run reset-failures`). Never a job whose application the browser holds or submitted
    (HANDS_OFF_OUTCOMES), never a done / needs-you / skipped job. BatchBusy while a driver runs."""
    from careeros.runs.runner import HANDS_OFF_OUTCOMES
    from careeros.runs.service import reset_failures

    b, lk = _locked(settings, batch_id)
    if lk is None:
        raise BatchBusy(f"batch {batch_id} is running; retry once it stops")
    try:
        store, n = Store(settings), 0
        for r in b["selected"]:
            if r.get("state") not in ("failed", "cancelled") or (job_ids and r["job_id"] not in job_ids):
                continue
            session = store._read(r["job_id"], "apply_session.json") or {}
            if session.get("submit_clicked") or session.get("outcome") in HANDS_OFF_OUTCOMES:
                r["reason"] = f"not retried: application {session.get('outcome') or 'submitted'}"
                continue
            if r["state"] == "failed":
                reset_failures(settings, r["stage"], r["job_id"])
            r["state"], r["reason"] = "pending", "retry"
            n += 1
        if n:
            b["status"], b["reason"] = "queued", None
        b["updated_at"] = iso(now or _utcnow())
        _dump(_dir(settings) / f"{batch_id}.json", b)
        return {**b, "retried": n}
    finally:
        locks.release(lk.path, lk.token)
