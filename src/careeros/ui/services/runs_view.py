"""What the Runs screen shows, built only on RunControl's public methods and the run files it reads.

RunControl (services/runs.py) owns starting, cancelling, pausing and reading runs. This module shapes its
answers for the screen: the running batch as job rows with step pills, the queue's `why` text as chips, the
schedule panel (cadence, next time, LaunchAgent state, quiet hours), job names on attempts, and the Pause all
`until` value. It never writes anything.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from typing_extensions import NotRequired, TypedDict

from careeros.store import Store
from careeros.ui.services.runs import BATCH_KINDS, RunControl, _parse_dt

PREPARE_STEPS = (  # (pill, files in the job folder that mean the step is done)
    ("Score", ("score.json",)),
    ("Tailor", ("resume.pdf", "resume.json")),
    ("Cover", ("cover_letter.md",)),
    ("QA", ("qa.json",)),
)
EXCLUDED_SHOWN = 200  # the "Not in queue" group names at most this many jobs; the total is always given
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
_POINTS = re.compile(r"^(.*?)\s*\(([+-]?\d+(?:\.\d+)?)\)$")
_REASON_CODES = (("posted", "fresh"), ("posting date", "fresh"), ("dream", "dream"), ("closes", "deadline"),
                 ("fit-first", "other"), ("fit", "fit"), ("retry", "retry"))
_RELATIVE = re.compile(r"^\+(\d+)([mhd])$")



# Response shapes: FastAPI turns these into the OpenAPI schema that ui/src/api/schema.gen.ts is generated from. A run
# record is the RunStore JSON (runs/store.py new_run + the runner's updates) plus the view keys added here; every key
# the store can write is listed, since a TypedDict response drops unlisted keys.
class RunBudget(TypedDict):
    preset: NotRequired[str | None]
    max_jobs: NotRequired[int | None]
    max_minutes: NotRequired[int | float | None]


class RunBase(TypedDict):
    id: str
    kind: str
    trigger: str
    # budget/detail/duration_s/counters are optional: an old or hand-edited run.json may lack one and must not 500
    budget: NotRequired[RunBudget]
    status: str
    # running | done | failed | interrupted (a running run whose process no longer holds its lock)
    state: str
    stop_reason: str | None
    detail: NotRequired[str]
    started_at: str | None
    ended_at: str | None
    duration_s: NotRequired[int | float | None]
    pid: NotRequired[int | None]
    counters: NotRequired[dict[str, int]]
    warnings: NotRequired[list[str]]
    dry_run: NotRequired[bool]
    step: NotRequired[bool]
    cmd: NotRequired[list[str]]


class RunRecord(RunBase):
    attempts: NotRequired[list[int]]  # the attempt numbers (the detail views carry the attempts themselves)


class HistoryPage(TypedDict):
    runs: list[RunRecord]
    next_cursor: str | None


class Attempt(TypedDict):
    n: int
    run_id: NotRequired[str]
    job_id: str | None
    company: NotRequired[str | None]
    title: NotRequired[str | None]
    stage: NotRequired[str]
    rank: NotRequired[int | None]
    why: NotRequired[str | None]
    session_id: NotRequired[str | None]
    outcome: str
    detail: NotRequired[str]
    result: NotRequired[dict[str, Any] | None]
    started_at: NotRequired[str | None]
    ended_at: NotRequired[str | None]
    duration_s: NotRequired[int | float | None]
    stream: NotRequired[str]
    headless: NotRequired[dict[str, Any]]


class RunDetail(RunBase):
    attempts: list[Attempt]
    log: str


class JobStep(TypedDict):
    name: str
    # skipped: a later step has output but this one has none (e.g. a cover letter the tier rule left out)
    state: Literal["done", "active", "pending", "skipped"]


class RunJobRow(TypedDict):
    job_id: str
    company: str | None
    title: str | None
    state: Literal["done", "failed", "active", "queued"]
    outcome: str | None
    duration_s: int | float | None
    detail: str
    steps: list[JobStep]


class RunUsed(TypedDict):
    jobs: int
    max_jobs: int | None
    minutes: int | float | None
    max_minutes: int | float | None


class RunCap(TypedDict):
    date: str
    cap: int
    applied: int
    remaining: int
    multiplier: int | float
    base: int
    reached: bool


class CurrentRun(RunBase):
    attempts: list[Attempt]
    holder: dict[str, Any] | None
    current_job: str | None
    used: RunUsed
    scheduled: bool
    jobs: list[RunJobRow]
    cap: RunCap | None


class RunPause(TypedDict):
    paused_at: str
    until: str | None
    reason: str


class CatchUpKind(TypedDict):
    first_missed: str | None
    slots: int
    last_missed: NotRequired[str | None]


class CatchUp(TypedDict):
    created_at: str
    updated_at: NotRequired[str]
    kinds: dict[str, CatchUpKind]


class QuietHours(TypedDict):
    start: str
    end: str


class ScheduleJob(TypedDict):
    kind: str
    enabled: bool
    every_minutes: int | float | None
    at: list[str]
    preset: str | None
    claude: bool
    next: str | None
    last_run: str | None
    last_status: str | None


class Schedule(TypedDict):
    label: str | None
    installed: bool
    loaded: bool
    last_tick: str | None
    tick_minutes: int | float
    quiet_hours: QuietHours | None
    jobs: list[ScheduleJob]
    catch_up: CatchUp | None
    paused: RunPause | None
    inbox_ready: bool

def check_run_id(run_id: str) -> str:
    if not _RUN_ID.match(run_id or ""):
        raise ValueError(f"not a run id: {run_id!r}")
    return run_id


def reasons(why: str | None) -> list[dict[str, Any]]:
    """`ranking.rank`'s why text ("posted 20h ago (+60); dream company (+25)") -> [{code, text, points}]."""
    out = []
    for part in (why or "").split(";"):
        part = part.strip()
        if not part:
            continue
        m = _POINTS.match(part)
        text, points = (m.group(1), float(m.group(2))) if m else (part, None)
        code = next((c for prefix, c in _REASON_CODES if text.startswith(prefix)), "other")
        out.append({"code": code, "text": text, "points": points})
    return out


def parse_until(value: str | None, now: datetime) -> datetime | None:
    """Pause all's `until`: None (until resumed), "+30m" / "+2h" / "+1d", or a future ISO time with a zone."""
    if value is None:
        return None
    m = _RELATIVE.match(value.strip())
    if m:
        unit = {"m": "minutes", "h": "hours", "d": "days"}[m.group(2)]
        return now + timedelta(**{unit: int(m.group(1))})
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"until must be +30m, +2h, +1d or an ISO date and time, got {value!r}") from None
    if dt.tzinfo is None:
        raise ValueError("until needs a time zone (for example 2026-09-27T09:00:00+02:00)")
    if dt <= now:
        raise ValueError("until is in the past; pick a later time")
    return dt


def _names(store: Store, job_id: str) -> dict[str, Any]:
    p = store.load_posting(job_id)
    return {"company": p.company, "title": p.title} if p else {"company": None, "title": None}


def _steps(store: Store, kind: str, job_id: str, state: str, since: datetime | None = None) -> list[dict[str, str]]:
    """`since`: this attempt's start (the job lock's acquired_at). A job folder can be reused across attempts
    (e.g. a retry), so a file must be at least as new as the current attempt to count as its output; an older
    file is left over from a previous attempt and the step still shows as not done."""
    steps = PREPARE_STEPS if kind == "prepare" else (("Score", ("score.json",)),)
    if state == "done":
        return [{"name": n, "state": "done"} for n, _ in steps]
    if state != "active":
        return [{"name": n, "state": "pending"} for n, _ in steps]
    d = store.job_dir(job_id)

    def _fresh(f: str) -> bool:
        p = d / f
        if not p.exists():
            return False
        return since is None or p.stat().st_mtime >= since.timestamp()

    have = [kind == "prepare" and any(_fresh(f) for f in files) for _, files in steps]
    # A later step's output means every earlier step finished; one with no output of its own was skipped
    # (prepare-job skips the cover letter when the tier rule is `if_required` and the posting doesn't ask).
    last = max((i for i, h in enumerate(have) if h), default=-1)
    out = []
    for i, (name, _) in enumerate(steps):
        if have[i]:
            state = "done"
        elif i < last:
            state = "skipped"
        else:
            state = "active" if i == last + 1 else "pending"
        out.append({"name": name, "state": state})
    return out


def _cap(rc: RunControl) -> dict[str, Any] | None:
    from careeros.runs.policy import current_cap

    try:
        return current_cap(rc.settings)
    except Exception:  # noqa: BLE001 - a locked or broken tracker must not hide the running batch
        return None


def current_view(rc: RunControl) -> CurrentRun | None:
    """rc.current() plus one row per job of the batch: done / failed (attempted), active (holds its job lock),
    queued (the rest of the run's selection), each with step pills; today's apply cap for prepare runs."""
    cur = rc.current()
    if cur is None:
        return None
    store = Store(rc.settings)
    kind = str(cur.get("kind"))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for att in cur.get("attempts") or []:
        jid = att.get("job_id")
        if not jid:
            continue
        state = "done" if att.get("outcome") == "ok" else "failed"
        names = {"company": att.get("company"), "title": att.get("title")}
        if not names["company"]:
            names = _names(store, jid)
        row = {"job_id": jid, **names, "state": state, "outcome": att.get("outcome"),
               "duration_s": att.get("duration_s"), "detail": att.get("detail") or "",
               "steps": _steps(store, kind, jid, state)}
        if jid in seen:  # a retry inside the same run: keep the latest attempt
            rows = [r for r in rows if r["job_id"] != jid]
        rows.append(row)
        seen.add(jid)
    active = cur.get("current_job")
    if active and active not in seen:
        since = _parse_dt(cur.get("current_job_started_at"))
        rows.append({"job_id": active, **_names(store, active), "state": "active", "outcome": None,
                     "duration_s": None, "detail": "", "steps": _steps(store, kind, active, "active", since)})
        seen.add(active)
    for item in cur.get("queue") or []:
        jid = item.get("job_id")
        if jid and jid not in seen:
            rows.append({"job_id": jid, **_names(store, jid), "state": "queued", "outcome": None,
                         "duration_s": None, "detail": "", "steps": _steps(store, kind, jid, "queued")})
            seen.add(jid)
    return cast(CurrentRun, {**cur, "scheduled": cur.get("trigger") == "schedule", "jobs": rows,
                             "cap": _cap(rc) if kind == "prepare" else None})


def history_view(rc: RunControl, kind: str | None, limit: int, cursor: str | None) -> HistoryPage:
    if cursor:
        check_run_id(cursor)
    return cast(HistoryPage, rc.history(kind=kind or None, limit=limit, cursor=cursor))


def detail_view(rc: RunControl, run_id: str) -> RunDetail | None:
    d = rc.detail(check_run_id(run_id))
    if d is None:
        return None
    store = Store(rc.settings)
    atts = []
    for a in d.get("attempts") or []:
        if a.get("job_id") and not a.get("company"):
            a = {**a, **_names(store, a["job_id"])}
        atts.append(a)
    return cast(RunDetail, {**d, "attempts": atts})


def queue_view(rc: RunControl, kind: str, limit: int) -> dict[str, Any]:
    if kind not in BATCH_KINDS:
        raise ValueError(f"unknown run kind {kind!r}; use {' or '.join(BATCH_KINDS)}")
    q = rc.queue(kind, limit=limit)
    store = Store(rc.settings)
    excluded = q.get("excluded") or []
    return {**q, "items": [{**i, "reasons": reasons(i.get("why"))} for i in q["items"]],
            "excluded": [{**e, **_names(store, e["job_id"])} for e in excluded[:EXCLUDED_SHOWN]],
            "excluded_total": len(excluded)}


def selection_view(dry: dict[str, Any]) -> dict[str, Any]:
    """A dry run's answer with chips on each selected job."""
    return {**dry, "selected": [{**i, "reasons": reasons(i.get("why"))} for i in dry.get("selected") or []]}


def schedule_view(rc: RunControl) -> Schedule:
    """rc.schedule_status() (LaunchAgent, last tick, next times, catch-up, pause) plus each job's cadence from
    `pipeline.yaml: schedule` and the quiet hours."""
    from careeros.runs.schedule import JOB_KINDS, load_schedule

    st = rc.schedule_status()
    cfg = load_schedule(rc.settings)
    nxt = st.get("next") or {}
    state = st.get("jobs") or {}
    jobs = []
    for kind in JOB_KINDS:
        j = cfg.jobs[kind]
        last = state.get(kind) or {}
        jobs.append({"kind": kind, "enabled": j.enabled, "every_minutes": None if j.at else j.every_minutes,
                     "at": [t.strftime("%H:%M") for t in (j.at or [])], "preset": j.preset,
                     "claude": j.claude, "next": nxt.get(kind), "last_run": last.get("last_run"),
                     "last_status": last.get("last_status")})
    quiet = ({"start": cfg.quiet_start.strftime("%H:%M"), "end": cfg.quiet_end.strftime("%H:%M")}
             if cfg.quiet_start and cfg.quiet_end else None)
    return cast(Schedule, {"label": st.get("label"), "installed": bool(st.get("installed")), "loaded": bool(st.get("loaded")),
            "last_tick": st.get("last_tick"), "tick_minutes": cfg.tick_minutes, "quiet_hours": quiet,
            "jobs": jobs, "catch_up": st.get("catch_up"), "paused": st.get("paused"),
            "inbox_ready": cfg.jobs["inbox_sync"].enabled})
