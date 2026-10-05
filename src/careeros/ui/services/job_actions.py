"""Job detail and Jobs writes, each through the code the CLI already uses:

- status (Set status, Withdraw + undo, Mark submitted): `tracker.set_status_both` (status.json + tracker)
- Status override: the tracker's Override column (`Tracker.upsert_job`); `queued` when Excel holds the file, since
  apply-job reads the column (`careeros tracker show`) and sees the old value until `careeros tracker flush`
- Safety Verify / Flag / Clear: `careeros.safety.registry` (same as `careeros safety verify|flag|clear`)
- Re-run QA: `careeros.qa.run_deterministic` (same as `python -m careeros.qa data/jobs/<id>`)
- Sync tracker: `tracker.sync_all` (same as `careeros tracker sync`)
- Open folder / Open JobTracker.xlsx: macOS `open`, only on the job's own folder or the configured tracker
- Files: a job's own documents and screenshots, never a path outside its folder

Unknown job or file: LookupError (404). Bad input: ValueError (400). Can't run here: desktop.Unsupported (409).
Status writes while a run or skill holds the job's lock: JobLocked (409).
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from careeros.readiness import require_ready
from careeros.ui.services import desktop
from careeros.ui.services.jobs import job_dir_for

OVERRIDES = ("", "A", "B", "C", "skip", "manual")      # the tracker's Override list validation
SUBMITTED_NOTE = "submitted by you (marked in careeros ui)"
_URL = re.compile(r"^https?://\S+$", re.I)


def _job(settings: Any, job_id: str) -> Path:
    d = job_dir_for(settings, job_id)
    if d is None:
        raise LookupError(f"no job {job_id!r}")
    return d


def _posting(settings: Any, job_id: str) -> dict[str, Any]:
    from careeros.store import Store

    _job(settings, job_id)
    return Store(settings)._read(job_id, "posting.json") or {}


def _urls(values: list[str] | None) -> list[str]:
    out = []
    for v in values or []:
        v = str(v).strip()
        if not v:
            continue
        if not _URL.match(v):
            raise ValueError(f"evidence must be http(s) links, got {v!r}")
        out.append(v)
    return out


# --- files -------------------------------------------------------------------------------------------------------

def resolve_file(settings: Any, job_id: str, name: str) -> Path:
    """`name` (e.g. resume.pdf, screenshots/01_form.png) inside the job folder. Refuses absolute paths, `..`,
    hidden names and anything that resolves (through a symlink) outside the folder."""
    d = _job(settings, job_id)
    parts = Path(name or "").parts
    if not parts or Path(name).is_absolute() or any(p in ("..", ".") or p.startswith(".") for p in parts):
        raise LookupError(f"no file {name!r}")
    root = d.resolve()
    f = d.joinpath(*parts).resolve()
    if not f.is_relative_to(root) or not f.is_file() or any(p.startswith(".") for p in f.relative_to(root).parts):
        raise LookupError(f"no file {name!r}")  # a symlink into a hidden file or folder is hidden too
    return f


# --- status ------------------------------------------------------------------------------------------------------

class JobLocked(Exception):
    """A run or a skill holds the job's lock (`careeros job lock`); the UI answers 409 and changes nothing."""


def ensure_unlocked(settings: Any, job_id: str) -> None:
    """Mirror of cli._job_lock_guard for the UI: refuse while the lock is held (a stale lock lets it through)."""
    from careeros.runs import locks
    from careeros.runs.store import RunStore

    st = locks.status(RunStore(settings).job_lock_path(job_id))
    if st["state"] == "held":
        raise JobLocked(f"job {job_id} is locked by {st.get('owner')} until {st.get('expires_at')} "
                        f"({st.get('note') or '-'}); not changed. Try again when it finishes.")


def _is_applied_undo(store: Any, job_id: str) -> bool:
    """True when the latest change moved the job from "applied" to its current status (a withdraw or a Set status):
    restoring "applied" is that change's Undo toast. Never true for a job that was not applied right before."""
    hist = (store._read(job_id, "status.json") or {}).get("history") or []
    return (len(hist) >= 2 and hist[-1].get("status") == store.get_status(job_id) != "applied"
            and hist[-2].get("status") == "applied")


def set_status(settings: Any, job_id: str, status: str, note: str | None = None) -> dict[str, Any]:
    """Set status: "applied" only through the confirmed Mark submitted (or undoing the change that left "applied")."""
    from careeros.store import Store

    _job(settings, job_id)
    if status == "applied" and not _is_applied_undo(Store(settings), job_id):
        raise ValueError("use Mark submitted to mark a job applied")
    return _write_status(settings, job_id, status, note)


def _write_status(settings: Any, job_id: str, status: str, note: str | None) -> dict[str, Any]:
    from careeros.store import Store
    from careeros.tracker import set_status_both

    _job(settings, job_id)
    if status not in settings.lifecycle_statuses:
        raise ValueError(f"status must be one of {', '.join(settings.lifecycle_statuses)}, got {status!r}")
    ensure_unlocked(settings, job_id)
    previous = Store(settings).get_status(job_id)
    set_status_both(settings, job_id, status, (note or "set in careeros ui").strip()[:200])
    return {"job_id": job_id, "status": status, "previous": previous}


def withdraw(settings: Any, job_id: str, note: str | None = None) -> dict[str, Any]:
    return _write_status(settings, job_id, "withdrawn", note or "withdrawn in careeros ui")


def mark_submitted(settings: Any, job_id: str, note: str | None = None) -> dict[str, Any]:
    return _write_status(settings, job_id, "applied", note or SUBMITTED_NOTE)


def set_override(settings: Any, job_id: str, value: str) -> dict[str, Any]:
    from careeros.models import TrackerRow
    from careeros.store import Store
    from careeros.tracker import Tracker

    _job(settings, job_id)
    if value not in OVERRIDES:
        raise ValueError(f"override must be one of {', '.join(repr(o) for o in OVERRIDES)}, got {value!r}")
    tr = Tracker(settings=settings)
    tr.init()
    if tr.get_job(job_id) is not None:
        got = tr.upsert_job({"job_id": job_id, "override": value})
    else:  # no Jobs row yet: write the whole row, as `careeros tracker sync` would
        store = Store(settings)
        p = store.load_posting(job_id)
        if p is None:
            raise LookupError(f"no job {job_id!r}")
        row = TrackerRow.from_posting(p, store.load_score(job_id), folder=str(store.job_dir(job_id)))
        st = store.get_status(job_id)
        if st:
            row.status = st  # type: ignore[assignment]
        row.override = value
        got = tr.upsert_job(row)
    return {"override": value, "queued": got == "queued"}


# --- QA ----------------------------------------------------------------------------------------------------------

def rerun_qa(settings: Any, job_id: str) -> dict[str, Any]:
    from careeros.qa import run_deterministic
    from careeros.store import Store

    d = _job(settings, job_id)
    result = run_deterministic(d, settings.root)
    s = result.get("summary") or {}
    Store(settings).append_log(job_id, f"qa (deterministic) {'pass' if result.get('pass') else 'fail'}: "
                                       f"{s.get('hard_fail', 0)} hard, {s.get('soft_fail', 0)} soft", component="ui")
    return result


# --- safety ------------------------------------------------------------------------------------------------------

def safety_verify(settings: Any, job_id: str, *, risk: str, signals: list[str] | None = None,
                  evidence: list[str] | None = None, domain: str = "") -> dict[str, Any]:
    from careeros.safety import registry

    p = _posting(settings, job_id)
    return registry.add_verified(registry.verified_path(settings), str(p.get("company") or ""), risk=risk,
                                 domain=domain or "", signals=[str(x).strip() for x in signals or [] if str(x).strip()],
                                 evidence=_urls(evidence))


def safety_flag(settings: Any, job_id: str, *, reason: str = "", confidence: str = "high",
                evidence: list[str] | None = None, notes: str = "") -> dict[str, Any]:
    from careeros.safety import registry

    if confidence not in ("high", "medium"):
        raise ValueError(f"confidence must be high or medium, got {confidence!r}")
    p = _posting(settings, job_id)
    return registry.add_or_bump(registry.default_path(settings), str(p.get("company") or ""),
                                domain=str(p.get("apply_url") or p.get("url") or ""), reason=reason or "manual",
                                job_id=job_id, notes=notes, confidence=confidence, evidence=_urls(evidence))


def safety_clear(settings: Any, job_id: str, note: str = "") -> dict[str, Any]:
    from careeros.safety import registry

    p = _posting(settings, job_id)
    e = registry.clear(registry.default_path(settings), str(p.get("company") or ""), note=note)
    if e is None:
        raise LookupError(f"{p.get('company')} is not in the flagged registry")
    return e


# --- tracker and desktop -----------------------------------------------------------------------------------------

def sync_tracker(settings: Any) -> dict[str, Any]:
    from careeros.tracker import sync_all

    return sync_all(settings)


def open_folder(settings: Any, job_id: str) -> dict[str, Any]:
    d = _job(settings, job_id).resolve()
    desktop.open_path(d)
    return {"opened": True}


def application_status(settings: Any, job_id: str) -> dict[str, Any]:
    """Is the staged form's tab alive? Never claims ready for a dead tab. A live tab on the Greenhouse
    confirmation page marks the job applied."""
    from careeros.apply import browser
    from careeros.store import Store

    st = browser.status(_job(settings, job_id), browser.cdp_url(settings))
    if st["submitted"] and Store(settings).get_status(job_id) != "applied":
        mark_submitted(settings, job_id, "submitted: Greenhouse confirmation page seen in the apply tab")
        st["marked_applied"] = True
    return st


def open_application(settings: Any, job_id: str, popen: Any = None, refill: bool = False) -> dict[str, Any]:
    """Focus the live filled tab (unless `refill`); otherwise fill the form again in a visible tab from the previewed
    fill plan, detached from this server so a rebuild never kills it. Never submits."""
    from careeros.apply import browser, gh_fill

    d = _job(settings, job_id)
    if not refill and browser.activate(d, browser.cdp_url(settings)):
        return {"action": "focused"}
    if browser.fill_running(d):  # double click / refill mid-fill: one fill, one tab, one application.json
        return {"action": "filling", "log": "application.log"}
    ensure_unlocked(settings, job_id)
    require_ready(settings.root)  # REQ-103: NotReady -> 409 before plan/fill spawn
    if (plan := _read_plan(d)) is None:  # REQ-105: preview before fill
        raise ValueError("preview the fill first: this job has no fill plan yet (Fill preview)")
    if problems := gh_fill.plan_problems(plan):  # REQ-106: answer first, then fill
        raise ValueError("answer the fill plan first: " + "; ".join(problems))
    gh_fill.preflight()
    cdp = browser.cdp_url(settings)
    if cdp != browser.DEFAULT_CDP and browser.tabs(cdp) is None:  # the default browser starts itself; yours can't
        raise browser.NotConnected(f"Chrome not connected on {cdp}: open Chrome with its extension/remote debugging "
                                   "on, then retry")
    if refill:
        browser.close(d, cdp)
    (d / "fill_summary.json").unlink(missing_ok=True)  # else status() shows the last fill's fields_left
    cmd = shlex.join([sys.executable, "-m", "careeros.cli", "apply", "fill", job_id])
    cmd = f"{cmd}; echo {shlex.quote(browser.FILL_EXIT)}$?"
    root = str(settings.root)
    with (d / "application.log").open("ab") as fh:
        p = (popen or subprocess.Popen)(["/bin/sh", "-c", cmd], cwd=root, env={**os.environ, "CAREEROS_ROOT": root},
                                        stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
        fh.write(f"{browser.FILL_PID}{p.pid}\n".encode())  # before the reply: the UI's refetch already sees `filling`
    return {"action": "filling", "log": "application.log"}


# --- fill plan preview (REQ-105/106) -------------------------------------------------------------------------------

def _read_plan(d: Path) -> dict[str, Any] | None:
    import json

    p = d / "fill_plan.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def fill_plan(settings: Any, job_id: str) -> dict[str, Any]:
    """The job's fill_plan.json (or None) and why it can't be filled yet."""
    from careeros.apply import gh_fill

    from careeros.apply.gh_schema import field_kind

    plan = _read_plan(_job(settings, job_id))
    if plan:  # `kind` (eeo/salary/legal...) from the field itself, for the UI; not stored
        plan["fields"] = [{**f, "kind": field_kind(f)} for f in plan["fields"]]
    return {"plan": plan, "problems": gh_fill.plan_problems(plan) if plan else []}


def make_fill_plan(settings: Any, job_id: str) -> dict[str, Any]:
    """Preview fill: `careeros apply plan <id>` (same code as the CLI, Action Item included), then the plan."""
    _job(settings, job_id)
    ensure_unlocked(settings, job_id)
    r = subprocess.run([sys.executable, "-m", "careeros.cli", "apply", "plan", job_id], cwd=str(settings.root),
                       env={**os.environ, "CAREEROS_ROOT": str(settings.root)}, capture_output=True, text=True,
                       timeout=120)
    if r.returncode not in (0, 3):  # 3 = sensitive field: the plan is written (blocked) and shown
        raise ValueError((r.stderr or r.stdout).strip()[-500:] or f"apply plan exited {r.returncode}")
    return fill_plan(settings, job_id)


def edit_fill_field(settings: Any, job_id: str, field_id: str, *, value: Any = None, skip: bool = False,
                    save: bool = True) -> dict[str, Any]:
    """Set one plan value (this job only) or skip an optional field; `save` also learns it as a standard answer
    (REQ-053) so the next plan fills it. Legal/salary/EEO are only ever the user's own answer, never guessed; EEO
    (judged from the field, not its source) never leaves this job."""
    from careeros.apply import gh_fill
    from careeros.apply.gh_schema import _SELECTS, field_kind, pick_option
    from careeros.runs.locks import _guard
    from careeros.store import Store

    d = _job(settings, job_id)
    with _guard(d / "fill_plan.json"):  # one read-modify-write at a time (threads + the CLI's rebuild)
        plan = _read_plan(d)
        if plan is None:
            raise LookupError(f"job {job_id} has no fill plan yet")
        f = next((x for x in plan["fields"] if x["field_id"] == field_id), None)
        if f is None:
            raise LookupError(f"no field {field_id!r} in the fill plan")
        ensure_unlocked(settings, job_id)
        if f.get("source") == "pause:sensitive" or f["type"] in ("file", "hidden"):
            raise ValueError(f"{f['label']}: not editable here")
        kind, saved = field_kind(f), False
        if skip:
            if f.get("required"):
                raise ValueError(f"{f['label']} is required: answer it to fill")
            f.update(value=None, skipped=True, needs_review=False)
        else:
            text = str(value if value is not None else "").strip()
            if not text:
                raise ValueError("value is empty")
            v: Any = pick_option(f["options"], text) if f.get("options") and f["type"] in _SELECTS else text
            if v is None:
                raise ValueError(f"{text!r} is not an option for {f['label']}")
            src = str(f.get("source") or "")
            f.update(value=[v] if f["type"] in ("multiselect", "checkbox_group") else v, source="user",
                     needs_review=False)
            f.pop("skipped", None)
            if save and kind != "eeo":
                _save_answer(settings, job_id, src, f["label"], text)
                saved = True
        Store(settings)._write(job_id, "fill_plan.json", plan)
    return {"field": {**f, "kind": kind}, "saved": saved, "problems": gh_fill.plan_problems(plan)}


def approve_fill_field(settings: Any, job_id: str, field_id: str) -> dict[str, Any]:
    """Approve an AI draft as is (REQ-105): reviewed, this job only; never written to the profile."""
    from careeros.apply import gh_fill
    from careeros.apply.gh_schema import field_kind
    from careeros.runs.locks import _guard
    from careeros.store import Store

    d = _job(settings, job_id)
    with _guard(d / "fill_plan.json"):
        plan = _read_plan(d)
        if plan is None:
            raise LookupError(f"job {job_id} has no fill plan yet")
        f = next((x for x in plan["fields"] if x["field_id"] == field_id), None)
        if f is None:
            raise LookupError(f"no field {field_id!r} in the fill plan")
        ensure_unlocked(settings, job_id)
        if f.get("source") != "ai_draft" or f.get("value") in (None, ""):
            raise ValueError(f"{f['label']}: not an AI draft")
        f.update(reviewed=True, needs_review=False)
        Store(settings)._write(job_id, "fill_plan.json", plan)
    return {"field": {**f, "kind": field_kind(f)}, "problems": gh_fill.plan_problems(plan)}


def _save_answer(settings: Any, job_id: str, src: str, label: str, text: str) -> None:
    """Update the saved answer this row came from (or the one learned from this label before); else learn it."""
    from careeros.learning import edit_answer, learn_answer, normalize, slug
    from careeros.store import Store

    key = src.removeprefix("standard:") if src.startswith("standard:") else slug(normalize(label))
    posting = Store(settings).load_posting(job_id) if src.startswith("standard:") else None
    for co in dict.fromkeys([None, getattr(posting, "company", None) or None]):  # general, then company-scoped
        try:
            return edit_answer(settings, key=key, answer=text, company=co)
        except KeyError:
            pass
    learn_answer(settings, question=label, answer=text, job_id=job_id)


def open_tracker(settings: Any) -> dict[str, Any]:
    from careeros.tracker import Tracker

    path = Tracker(settings=settings).path.resolve()
    if not path.is_file():
        raise desktop.Unsupported("JobTracker.xlsx doesn't exist yet: run Sync tracker first")
    desktop.open_path(path)
    return {"opened": True, "path": str(path)}
