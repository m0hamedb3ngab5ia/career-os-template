"""One job's pipeline for Job detail: the stage it is at, the single next action the UI offers (Start, Continue,
Approve & continue), why nothing can run, and what a needs_review job is waiting on.

The rules are the runner's (careeros.runs.runner.eligibility, policy.is_tier_a): this module reads the job files
and names the button; `careeros run <kind> --job <id>` decides again before anything is called, so a Tier A job
is refused twice and never applied by a run.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from careeros.runs.policy import is_tier_a
from careeros.runs.runner import eligibility

STAGES = ("score", "prepare", "qa", "review", "apply")
Action = Literal["start", "continue", "approve_continue"]
LABELS: dict[str, str] = {"start": "Start pipeline", "continue": "Continue pipeline",
                          "approve_continue": "Approve & continue"}
TIER_A_BLOCKED = "Tier A: never auto-applied; apply manually"
APPLY_STAGED = "Application staged in the browser: review and submit it manually (see Apply session)"
# apply_session.json outcomes after which the browser holds the application: nothing runs again, a human finishes.
HANDS_OFF_OUTCOMES = ("staged", "submitted", "blocked")
APPROVE_NOTE = "Approved for apply from the UI"
# Statuses after which the pipeline has nothing left to run (the job is done, dropped or in the human's hands).
DONE_STATUSES = ("applied", "skipped", "withdrawn", "screening", "interview", "offer", "rejected", "ghosted")
STAGE_OF_STATUS = {"found": "score", "scored": "prepare", "prepared": "qa", "queued": "apply", "needs_review": "review"}


class PipelineState(TypedDict):
    stage: str
    next_action: Action | None
    next_label: str | None
    next_kind: str | None
    force: bool  # the next run needs `--force` (a stage that already finished is rerun)
    blocked_reason: str | None
    review_reasons: list[str]
    active_run_id: str | None
    queued_in_run: str | None  # a batch run that will get to this job later (no Cancel: it would kill the batch)


class NotRunnable(RuntimeError):
    """The requested action does not fit the job's state (the message says why)."""


def _strs(v: Any) -> list[str]:
    return [str(x) for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []


def _dicts(v: Any) -> list[dict[str, Any]]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def session_notes(session: dict[str, Any] | None) -> list[str]:
    """What the last apply session (apply_session.json) left for the human: its outcome + reason, its action item."""
    session = session or {}
    out: list[str] = []
    if session.get("outcome"):
        out.append(f"Apply session {session['outcome']}: {session.get('reason') or 'no reason given'}")
    item = session.get("action_item")
    if isinstance(item, dict) and str(item.get("what") or "").strip():
        out.append(f"Action item: {str(item['what']).strip()}")
    return out


def review_reasons(qa: dict[str, Any] | None, prepare: dict[str, Any] | None,
                   open_actions: list[str], apply_session: dict[str, Any] | None = None) -> list[str]:
    """Why a job needs a human: QA fail reasons, failed (non-skipped) QA checks and warnings, prepare-job's
    action items / flags / notes, the last apply session's notes, then the open Action Items for the job.
    Deduplicated, in that order."""
    out: list[str] = []
    qa, prepare = qa or {}, prepare or {}
    det = qa.get("deterministic") if isinstance(qa.get("deterministic"), dict) else {}
    for r in _strs(qa.get("fail_reasons")):
        out.append(f"QA: {r}")
    for c in [*_dicts(qa.get("checks")), *_dicts(det.get("checks"))]:
        if c.get("ok") is False and not c.get("skipped"):
            out.append(f"QA check {c.get('check') or '?'}: {c.get('detail') or 'failed'}")
    for w in [*_strs(qa.get("warnings")), *_strs(det.get("warnings"))]:
        out.append(f"QA warning: {w}")
    for a in _strs(prepare.get("action_items")):
        out.append(a)
    for f in _strs(prepare.get("flags")):
        out.append(f"Flag: {f}")
    if isinstance(prepare.get("notes"), str) and prepare["notes"].strip():
        out.append(prepare["notes"].strip())
    out.extend(session_notes(apply_session))
    for a in open_actions:
        out.append(f"Open action item: {a}")
    return list(dict.fromkeys(s for s in out if s))


def compute_state(status: str | None, score: dict[str, Any] | None, prepare: dict[str, Any] | None,
                  qa: dict[str, Any] | None, open_actions: list[str] | None = None,
                  active_run_id: str | None = None, apply_session: dict[str, Any] | None = None,
                  queued_in_run: str | None = None) -> PipelineState:
    """Pure: the job's files in, the stage / next action / blocked reason out."""
    status = status or "found"
    score, prepare, session = score or {}, prepare or {}, apply_session or {}
    has_score, qa_pass, tier_a = bool(score), bool(prepare.get("qa_pass")), is_tier_a(score.get("tier"))
    st: PipelineState = {"stage": STAGE_OF_STATUS.get(status, "apply"), "next_action": None, "next_label": None,
                         "next_kind": None, "force": False, "blocked_reason": None,
                         "review_reasons": review_reasons(qa, prepare, open_actions or [], session),
                         "active_run_id": active_run_id, "queued_in_run": queued_in_run}

    def offer(action: Action, kind: str, force: bool = False) -> PipelineState:
        st.update(next_action=action, next_label=LABELS[action], next_kind=kind, force=force)
        return st

    if active_run_id:
        st["blocked_reason"] = "A run is working on this job"
        return st
    if queued_in_run:
        st["blocked_reason"] = f"Queued in batch run {queued_in_run}"
        return st
    if status in DONE_STATUSES:
        return st
    if status in ("found", "scored"):
        kind = "score" if status == "found" and not has_score else "prepare"  # the runner scores before it prepares
        why = eligibility(kind, status, has_score, score, qa_pass)
        if why is None:
            return offer("start" if kind == "score" or status == "found" else "continue", kind)
        if why == "already prepared":
            return offer("continue", "prepare", force=True)
        st["blocked_reason"] = f"Score decision: skip ({score.get('skip_reason') or 'see score.json'})" \
            if why.startswith("score decision") else why
        return st
    if status == "needs_review":
        if tier_a:
            st["blocked_reason"] = TIER_A_BLOCKED
            return st
        if session.get("outcome") in HANDS_OFF_OUTCOMES:  # the browser holds the form: re-approving would refill it
            st["blocked_reason"] = APPLY_STAGED if session["outcome"] == "staged" else \
                f"Application {session['outcome']} in the browser: finish it manually (see Apply session)"
            return st
        return offer("approve_continue", "apply") if qa_pass else offer("continue", "prepare", force=True)
    if status in ("queued", "prepared"):
        why = eligibility("apply", status, has_score, score, qa_pass)
        if why is None:
            return offer("continue", "apply")
        if tier_a:
            st["stage"] = "apply"
            st["blocked_reason"] = TIER_A_BLOCKED
            return st
        st["stage"] = "qa"
        return offer("continue", "prepare", force=True)  # qa not passed: re-prepare
    return st


def open_action_items(settings: Any, job_id: str) -> list[str]:
    """The open Action Items for the job ("What to do"); [] when the tracker cannot be read."""
    from careeros.tracker import Tracker

    try:
        items = Tracker(settings=settings).list_action_items(open_only=True)
    except Exception:  # noqa: BLE001 - a locked or broken workbook must not break Job detail
        return []
    return [str(i.get("What to do") or "").strip() for i in items if str(i.get("JobID") or "") == job_id
            and str(i.get("What to do") or "").strip()]


def pipeline_state(settings: Any, job_id: str, rc: Any) -> PipelineState:
    """GET /jobs/{id}/pipeline: compute_state over the job's files, the tracker's open items and the running run."""
    from careeros.store import Store
    from careeros.ui.services.job_actions import _job

    _job(settings, job_id)  # LookupError -> 404
    store = Store(settings)
    return compute_state(store.get_status(job_id), store._read(job_id, "score.json"),
                         store._read(job_id, "prepare.json"), store._read(job_id, "qa.json"),
                         open_action_items(settings, job_id), rc.active_run_for(job_id),
                         apply_session=store._read(job_id, "apply_session.json"),
                         queued_in_run=rc.queued_in_run(job_id))


def start_pipeline(settings: Any, job_id: str, action: str, rc: Any, force: bool = False) -> dict[str, Any]:
    """POST /jobs/{id}/pipeline: `approve_continue` moves needs_review -> queued (logged) and applies; `start` /
    `continue` run the next stage. {run_id, kind}. NotRunnable when the action does not fit the state; the
    runner's Busy / Paused / JobNotRunnable pass through (409 in the router)."""
    from careeros.store import Store
    from careeros.ui.services import job_actions

    if action not in LABELS:
        raise ValueError(f"action must be one of {', '.join(LABELS)}, got {action!r}")
    rc._check_can_start()  # Busy / Paused before any status change
    st = pipeline_state(settings, job_id, rc)
    fits = st["next_action"] is not None and (action == st["next_action"]
                                              or {action, st["next_action"]} <= {"start", "continue"})
    if not fits:
        raise NotRunnable(st["blocked_reason"] or "Nothing to run for a job with status "
                                                  f"{Store(settings).get_status(job_id) or 'found'}")
    if action == "approve_continue":
        job_actions.set_status(settings, job_id, "queued", APPROVE_NOTE)
    kind = st["next_kind"] or "prepare"
    out = rc.start(kind, job_id=job_id, force=force or st["force"])
    return {"run_id": out["run_id"], "kind": kind}
