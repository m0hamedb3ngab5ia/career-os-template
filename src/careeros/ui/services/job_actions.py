"""Job detail and Jobs writes, each through the code the CLI already uses:

- status (Set status, Withdraw + undo, Mark submitted): `tracker.set_status_both` (status.json + tracker)
- Status override: the tracker's Override column (`Tracker.upsert_job`)
- Safety Verify / Flag / Clear: `careeros.safety.registry` (same as `careeros safety verify|flag|clear`)
- Re-run QA: `careeros.qa.run_deterministic` (same as `python -m careeros.qa data/jobs/<id>`)
- Sync tracker: `tracker.sync_all` (same as `careeros tracker sync`)
- Open folder / Open JobTracker.xlsx: macOS `open`, only on the job's own folder or the configured tracker
- Files: a job's own documents and screenshots, never a path outside its folder

Unknown job or file: LookupError (404). Bad input: ValueError (400). Can't run here: desktop.Unsupported (409).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

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
    if not f.is_relative_to(root) or not f.is_file():
        raise LookupError(f"no file {name!r}")
    return f


# --- status ------------------------------------------------------------------------------------------------------

def set_status(settings: Any, job_id: str, status: str, note: str | None = None) -> dict[str, Any]:
    from careeros.store import Store
    from careeros.tracker import set_status_both

    _job(settings, job_id)
    if status not in settings.lifecycle_statuses:
        raise ValueError(f"status must be one of {', '.join(settings.lifecycle_statuses)}, got {status!r}")
    previous = Store(settings).get_status(job_id)
    set_status_both(settings, job_id, status, (note or "set in careeros ui").strip()[:200])
    return {"status": status, "previous": previous}


def withdraw(settings: Any, job_id: str, note: str | None = None) -> dict[str, Any]:
    return set_status(settings, job_id, "withdrawn", note or "withdrawn in careeros ui")


def mark_submitted(settings: Any, job_id: str, note: str | None = None) -> dict[str, Any]:
    return set_status(settings, job_id, "applied", note or SUBMITTED_NOTE)


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
        tr.upsert_job({"job_id": job_id, "override": value})
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
        tr.upsert_job(row)
    return {"override": value}


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


def open_tracker(settings: Any) -> dict[str, Any]:
    from careeros.tracker import Tracker

    path = Tracker(settings=settings).path.resolve()
    if not path.is_file():
        raise desktop.Unsupported("JobTracker.xlsx doesn't exist yet: run Sync tracker first")
    desktop.open_path(path)
    return {"opened": True, "path": str(path)}
