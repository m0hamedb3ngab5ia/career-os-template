"""One job's pipeline for Job detail: the stage it is at, the single next action the UI offers (Start, Continue,
Approve & continue), why nothing can run, and what a needs_review job is waiting on.

The rules are the runner's (careeros.runs.runner.eligibility, policy.is_tier_a): this module reads the job files
and names the button; `careeros run <kind> --job <id>` decides again before anything is called. A Tier A job is
never refused: its apply stage runs assisted (the runner passes CAREEROS_AUTO_SUBMIT=0), so the run fills and
stages the form and the candidate reviews and submits; a run never submits Tier A.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from careeros.runs.policy import is_tier_a
from careeros.runs.runner import HANDS_OFF_OUTCOMES, eligibility

STAGES = ("score", "prepare", "qa", "review", "apply")
Action = Literal["start", "continue", "approve_continue"]
ACTIONS: tuple[Action, ...] = ("start", "continue", "approve_continue")
LABELS: dict[str, str] = {"start": "Start pipeline", "continue": "Continue pipeline",
                          "approve_continue": "Approve & continue",
                          "stage_review": "Prepare & stage for review"}  # Tier A apply (assisted)
TIER_A_NOTE = "Tier A: the run fills and stages the form; you review and submit."
STAGE_NOTE = "auto_submit is off: the run fills and stages the form; you review and submit."
APPLY_STAGED = "Application staged in the browser: review and submit it manually (see Apply session)"
# HANDS_OFF_OUTCOMES (runner): apply_session.json outcomes after which nothing runs again, a human finishes.
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
    note: str | None  # what the next action does differently for this job (Tier A: assisted apply)
    auto_submit: bool  # runs.auto_submit.enabled: false -> every apply run only fills and stages the form
    review_reasons: list[Reason]
    active_run_id: str | None
    queued_in_run: str | None  # a batch run that will get to this job later (no Cancel: it would kill the batch)
    failures: FailureInfo | None  # the next kind's failure count (runs/failures.py); excluded -> blocked until reset


class Reason(TypedDict):
    """Why a job needs a human. `code`: stable id the UI may map; `text`: a human sentence (no commands, no internal
    ids); `detail`: the raw technical text behind it (file values, CLI hints), for a Details disclosure."""
    code: str
    text: str
    detail: str | None


# QA check ids -> what they mean for the human (docs/design/ui-redesign.md §2.4)
QA_CHECK_TEXT = {
    "keyword_coverage": "Resume misses key skills from this role",
    "numbers_consistent": "Resume and cover letter disagree on a detail",
    "employer_title_consistent": "Resume and cover letter disagree on a detail",
    "confidential_terms": "A private term appeared in a document",
}
SESSION_TEXT = {
    "staged": "The application is filled in: review it and submit",
    "needs_review": "The application needs your review",
    "failed": "The application couldn't be filled in",
    "blocked": "The application was blocked before it was sent",
    "submitted": "The application was submitted",
}
ACTION_TEXT = {  # open Action Item type -> the next step
    "captcha": "Solve a verification check", "bot_detection": "Solve a verification check",
    "question": "Answer the application questions", "salary": "Decide a salary answer",
    "profile_gap": "Add missing experience to your profile", "laptop_required": "Finish on your laptop",
    "qa_fail": "Review the tailored resume", "scam_suspected": "Check this company is real",
    "ghost_job": "The posting may be stale", "review": "Review and submit the application",
    "send_linkedin": "Send a LinkedIn message", "send_email": "Send an email",
}


def _reason(code: str, text: str, detail: Any = None) -> Reason:
    return {"code": code, "text": text, "detail": str(detail).strip() if detail else None}


class FailureInfo(TypedDict):
    kind: str
    count: int
    max_attempts: int
    last_outcome: str | None
    last_detail: str | None
    last_run: str | None
    excluded: bool


class NotRunnable(RuntimeError):
    """The requested action does not fit the job's state (the message says why)."""


def _strs(v: Any) -> list[str]:
    return [str(x) for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []


def _dicts(v: Any) -> list[dict[str, Any]]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def session_notes(session: dict[str, Any] | None) -> list[Reason]:
    """What the last apply session (apply_session.json) left for the human: its outcome + reason, its action item."""
    session = session or {}
    out: list[Reason] = []
    if outcome := session.get("outcome"):
        out.append(_reason(f"apply_{outcome}", SESSION_TEXT.get(outcome, "The last application attempt needs a look"),
                           f"Apply session {outcome}: {session.get('reason') or 'no reason given'}"))
    item = session.get("action_item")
    if isinstance(item, dict) and str(item.get("what") or "").strip():
        out.append(_reason("apply_action", "The application left a step for you", item["what"]))
    return out


def review_reasons(qa: dict[str, Any] | None, prepare: dict[str, Any] | None,
                   open_actions: list[dict[str, Any]], apply_session: dict[str, Any] | None = None) -> list[Reason]:
    """Why a job needs a human: QA fail reasons, failed (non-skipped) QA checks and warnings, prepare-job's
    action items / flags / notes, the last apply session's notes, then the open Action Items ({type, what}) for the
    job. Deduplicated, in that order."""
    out: list[Reason] = []
    qa, prepare = qa or {}, prepare or {}
    det = qa.get("deterministic") if isinstance(qa.get("deterministic"), dict) else {}
    for r in _strs(qa.get("fail_reasons")):
        out.append(_reason("qa_fail", "The documents need your review", r))
    for c in [*_dicts(qa.get("checks")), *_dicts(det.get("checks"))]:
        if c.get("ok") is False and not c.get("skipped"):
            check = str(c.get("check") or "unknown")
            out.append(_reason(f"qa_{check}", QA_CHECK_TEXT.get(check, "A document check failed"),
                               f"{check}: {c.get('detail') or 'failed'}"))
    for w in [*_strs(qa.get("warnings")), *_strs(det.get("warnings"))]:
        out.append(_reason("qa_warning", "A document check left a warning", w))
    for a in _strs(prepare.get("action_items")):
        out.append(_reason("prepare_action", "Document preparation left a step for you", a))
    for f in _strs(prepare.get("flags")):
        out.append(_reason("prepare_flag", "Document preparation flagged something to check", f))
    if isinstance(prepare.get("notes"), str) and prepare["notes"].strip():
        out.append(_reason("prepare_note", "Document preparation left a note", prepare["notes"]))
    out.extend(session_notes(apply_session))
    for a in open_actions:
        t = str(a.get("type") or "other")
        out.append(_reason(f"action_{t}", ACTION_TEXT.get(t, "A task for this job needs you"),
                            a.get("detail") or a.get("what")))
    return list({(r["code"], r["detail"]): r for r in out}.values())


def compute_state(status: str | None, score: dict[str, Any] | None, prepare: dict[str, Any] | None,
                  qa: dict[str, Any] | None, open_actions: list[dict[str, Any]] | None = None,
                  active_run_id: str | None = None, apply_session: dict[str, Any] | None = None,
                  queued_in_run: str | None = None, auto_submit: bool = False,
                  failures: FailureInfo | None = None) -> PipelineState:
    """Pure: the job's files in, the stage / next action / blocked reason out. `auto_submit` is the config switch
    (runs.auto_submit.enabled); while it is off every apply is labelled as staging for review (the run never submits)
    and the UI chains prepare into a plain `continue` apply, never past the Approve gate."""
    status = status or "found"
    score, prepare, session = score or {}, prepare or {}, apply_session or {}
    has_score, qa_pass, tier_a = bool(score), bool(prepare.get("qa_pass")), is_tier_a(score.get("tier"))
    st: PipelineState = {"stage": STAGE_OF_STATUS.get(status, "apply"), "next_action": None, "next_label": None,
                         "next_kind": None, "force": False, "blocked_reason": None, "note": None,
                         "auto_submit": auto_submit,
                         "review_reasons": review_reasons(qa, prepare, open_actions or [], session),
                         "active_run_id": active_run_id, "queued_in_run": queued_in_run, "failures": None}

    def offer(action: Action, kind: str, force: bool = False) -> PipelineState:
        st.update(next_action=action, next_label=LABELS[action], next_kind=kind, force=force)
        if failures and failures.get("kind") == kind:
            st["failures"] = failures
            if failures.get("excluded"):  # the runner skips it (runs/service.py): Reset failures runs it again
                st["blocked_reason"] = (f"Failed {failures['count']} times (last: {failures.get('last_outcome')}): "
                                        "runs skip this job until you reset its failures")
        if kind == "apply" and (tier_a or not auto_submit):  # the run stages the form, the candidate submits
            st["note"] = TIER_A_NOTE if tier_a else STAGE_NOTE
            if tier_a or action == "continue":  # the Approve gate keeps its label for B/C: the human approves docs
                st["next_label"] = LABELS["stage_review"]
        return st

    def hands_off() -> PipelineState:  # the browser holds the form: running again would refill or re-submit it
        st["blocked_reason"] = APPLY_STAGED if session.get("outcome") == "staged" else \
            "submit already clicked in an earlier session: check the ATS by hand" if session.get("submit_clicked") \
            else f"Application {session['outcome']} in the browser: finish it manually (see Apply session)"
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
    if status in ("needs_review", "queued", "prepared") and \
            (session.get("outcome") in HANDS_OFF_OUTCOMES or session.get("submit_clicked")):
        return hands_off()
    if status == "needs_review":
        return offer("approve_continue", "apply") if qa_pass else offer("continue", "prepare", force=True)
    if status in ("queued", "prepared"):
        why = eligibility("apply", status, has_score, score, qa_pass, apply_session=session)
        if why is None:
            return offer("continue", "apply")
        st["stage"] = "qa"
        return offer("continue", "prepare", force=True)  # qa not passed: re-prepare
    return st


def open_action_items(settings: Any, job_id: str) -> list[dict[str, Any]]:
    """The open Action Items for the job as {type, what, detail}; [] when the tracker cannot be read."""
    from careeros.tracker import Tracker

    try:
        items = Tracker(settings=settings).list_action_items(open_only=True)
    except Exception:  # noqa: BLE001 - a locked or broken workbook must not break Job detail
        return []
    return [{"type": i.get("Type"), "what": str(i.get("What to do") or "").strip(),
             "detail": str(i.get("Detail") or "").strip() or None} for i in items
            if str(i.get("JobID") or "") == job_id and str(i.get("What to do") or "").strip()]


def pipeline_state(settings: Any, job_id: str, rc: Any) -> PipelineState:
    """GET /jobs/{id}/pipeline: compute_state over the job's files, the tracker's open items and the running run."""
    from careeros.runs.config import load_runs_config
    from careeros.runs.policy import AutoSubmitPolicy
    from careeros.store import Store
    from careeros.runs.failures import Failures
    from careeros.runs.policy import load_retry_config
    from careeros.runs.store import RunStore
    from careeros.ui.services.job_actions import _job

    _job(settings, job_id)  # LookupError -> 404
    store = Store(settings)
    raw = load_runs_config(settings).raw
    auto_submit = AutoSubmitPolicy.from_config(raw).enabled
    args = (store.get_status(job_id), store._read(job_id, "score.json"), store._read(job_id, "prepare.json"),
            store._read(job_id, "qa.json"), open_action_items(settings, job_id), rc.active_run_for(job_id))
    kw = dict(apply_session=store._read(job_id, "apply_session.json"), queued_in_run=rc.queued_in_run(job_id),
              auto_submit=auto_submit)
    st = compute_state(*args, **kw)
    fails = Failures(RunStore(settings)).status(st["next_kind"], job_id, load_retry_config(raw)["max_attempts"]) \
        if st["next_kind"] else None
    return compute_state(*args, **kw, failures=fails) if fails else st


def reset_failures(settings: Any, job_id: str, kind: str | None = None) -> dict[str, Any]:
    """POST /jobs/{id}/failures/reset: clear the job's failure count (default: every run kind) and resolve its
    out-of-retries Action Items (runs/service.reset_failures). {job_id, cleared: [kinds], resolved: [ids]}."""
    from careeros.runs.runner import SKILLS
    from careeros.runs.service import reset_failures as reset
    from careeros.ui.services.job_actions import _job

    _job(settings, job_id)  # LookupError -> 404
    outs = [reset(settings, k, job_id) for k in ([kind] if kind else list(SKILLS))]
    return {"job_id": job_id, "cleared": [o["kind"] for o in outs if o["cleared"]],
            "resolved": [i for o in outs for i in o["resolved"]]}


def start_pipeline(settings: Any, job_id: str, action: str, rc: Any, force: bool = False) -> dict[str, Any]:
    """POST /jobs/{id}/pipeline: `approve_continue` moves needs_review -> queued (logged) and applies; `start` /
    `continue` run the next stage. {run_id, kind}. NotRunnable when the action does not fit the state; the
    runner's Busy / Paused / JobNotRunnable pass through (409 in the router)."""
    from careeros.store import Store
    from careeros.ui.services import job_actions

    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}, got {action!r}")
    rc._check_can_start()  # Busy / Paused before any status change
    st = pipeline_state(settings, job_id, rc)
    fits = st["next_action"] is not None and (action == st["next_action"]
                                              or {action, st["next_action"]} <= {"start", "continue"})
    if not fits or (st["failures"] or {}).get("excluded"):
        raise NotRunnable(st["blocked_reason"] or "Nothing to run for a job with status "
                                                  f"{Store(settings).get_status(job_id) or 'found'}")
    if action == "approve_continue":
        job_actions.set_status(settings, job_id, "queued", APPROVE_NOTE)
    kind = st["next_kind"] or "prepare"
    out = rc.start(kind, job_id=job_id, force=force or st["force"])
    return {"run_id": out["run_id"], "kind": kind}
