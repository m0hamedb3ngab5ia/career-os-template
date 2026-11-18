"""The Today screen's "Needs you" list and the size of the next prepare run ("Prepare queued (N)").

Items are shaped by services/actions.py, the one source behind /api/actions (same `due`, `due_date_only`, `level`
fields); Mark done / Undo go through /api/actions/{id}/done|reopen.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, tzinfo
from typing import Any, Collection

from typing_extensions import TypedDict

from careeros.config import ConfigError
from careeros.ui.services.actions import ActionItem
from careeros.ui.services.jobs import JobListItem

PRIORITY = {"H": 0, "M": 1, "L": 2}


# Response shapes (OpenAPI -> ui/src/api/schema.gen.ts).
class PrepareQueue(TypedDict):
    total: int | None
    error: str | None


class OutreachItem(TypedDict):
    """One job with people to contact (contacts.json) and/or drafted messages (outreach.json). Nothing is sent."""
    job_id: str
    company: str
    title: str
    contact_name: str | None
    contact_role: str | None
    email: str | None
    email_confidence: str | None
    draft_ready: bool
    followup_due: str | None


class Season(TypedDict):
    """REQ-160: the named season window today falls in (targets.yaml volume.season_multiplier list form)."""
    name: str
    level: str
    advice: str
    multiplier: float
    daily_cap: int
    weekly_target: int


class Today(TypedDict):
    actions: list[ActionItem]
    prepare_queue: PrepareQueue
    top_picks: list[JobListItem]
    outreach: list[OutreachItem]
    season: Season | None


# Tasks that only matter before applying; once the job is applied or skipped they are stale (never closed by hand).
PRE_APPLY = ("review", "question", "salary", "qa_fail")
PAST_APPLY = ("applied", "screening", "interview", "offer", "rejected", "withdrawn", "ghosted", "skipped")
# Shared by Today's list and the sidebar count so they always agree.
OPEN_FROM = ("FROM action_items a LEFT JOIN jobs j ON j.job_id = a.job_id WHERE a.done = 0 AND NOT ("
             f"a.type IN ({','.join('?' * len(PRE_APPLY))}) AND COALESCE(j.status, '') IN ({','.join('?' * len(PAST_APPLY))}))")
OPEN_PARAMS = (*PRE_APPLY, *PAST_APPLY)


def open_actions(ix: Any, now: datetime, tz: tzinfo, soon_hours: int) -> list[ActionItem]:
    """Every open item, shaped by the Action Items service (same due fields: `due`, `due_date_only`, `level`),
    highest priority first."""
    from careeros.ui.services.actions import _item

    rows = ix.query(f"SELECT a.* {OPEN_FROM}", OPEN_PARAMS)
    items = [_item(r, now, tz, soon_hours) for r in rows if r.get("id")]
    return sorted(items, key=lambda i: (PRIORITY.get(i["priority"], 3), i["created"] or "", i["id"]))


def ranked_from_index(settings: Any, ix: Any, kind: str, cfg: Any, now: datetime,
                      ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """runner.select_candidates, read from the index's `candidates` table instead of every job folder."""
    import json

    from careeros.runs.runner import CandidateRecord, rank_records

    rows = ix.query("SELECT * FROM candidates ORDER BY job_id")
    bad = next((r for r in rows if r["error"]), None)
    if bad:   # select_candidates raises on the same file, so the next run would fail too
        raise ValueError(f"job {bad['job_id']}: {bad['error']}")
    records = (CandidateRecord(job_id=r["job_id"], status=r["status"], score=json.loads(r["score"] or "{}"),
                               has_score=bool(r["has_score"]), prepared_ok=bool(r["prepared_ok"]),
                               posting=json.loads(r["posting"] or "{}")) for r in rows)
    return rank_records(settings, kind, cfg, now, records)


def prepare_queue(settings: Any, ix: Any, now: datetime) -> PrepareQueue:
    """How many jobs the next prepare run could pick (the ranking `careeros run status` uses, over the index)."""
    from careeros.runs.config import load_runs_config

    try:
        ranked, _ = ranked_from_index(settings, ix, "prepare", load_runs_config(settings), now)
    except (ConfigError, OSError, ValueError, sqlite3.Error) as e:
        return {"total": None, "error": str(e)}
    return {"total": len(ranked), "error": None}


TOP_PICKS = 5
TOP_PICK_DAYS = 14


def top_picks(ix: Any, now: datetime, *, closed: list[str], n: int = TOP_PICKS,
              keep: Collection[str] = ()) -> list[JobListItem]:
    """REQ-127: the first `n` of the Jobs Recommended tab (same clause, fit first), new (found in the last
    TOP_PICK_DAYS days) and tier A/B. Fewer qualify → fewer cards (Q-025). Prepare ticks a job (selected=1), which
    takes it off Recommended: jobs in `keep` (started_ids) stay while not yet prepared (status found/scored), so
    their card can show progress, the failure and Retry."""
    from datetime import timedelta

    from careeros.ui.services import jobs

    since = (now - timedelta(days=TOP_PICK_DAYS)).date().isoformat()
    kw: dict[str, Any] = dict(closed=closed, sort="-fit", limit=n, tier=["A", "B"], ranges={"found_at": (since, None)})
    kept = jobs.list_jobs(ix, tab="saved", status=["found", "scored"], job_ids=list(keep), **kw)["items"] \
        if keep else []
    rec = jobs.list_jobs(ix, tab="recommended", **kw)["items"]
    return sorted([*kept, *rec][:n], key=lambda r: -(r["fit"] or 0))


def started_ids(settings: Any, rc: Any) -> set[str]:
    """Jobs whose prepare run is in flight or queued, or whose last prepare failed (runs/failures.py)."""
    from careeros.runs.failures import Failures
    from careeros.runs.store import RunStore

    pre = "prepare:"
    ids = {k[len(pre):] for k, e in Failures(RunStore(settings))._load().items()
           if k.startswith(pre) and e.get("count")}
    run = rc.current() or {}
    if run.get("state") == "running" and run.get("kind") == "prepare":
        ids |= {j for j in (run.get("current_job"), *(q.get("job_id") for q in run.get("queue") or [])) if j}
    return ids


NO_OUTREACH = ("skipped", "rejected", "withdrawn", "ghosted")
ROLE_ORDER = {"recruiter": 0, "hiring_manager": 1, "team_lead": 2}


def _json(path: Any) -> dict[str, Any]:
    import json

    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def outreach(settings: Any, ix: Any, *, closed: list[str]) -> list[OutreachItem]:
    """Jobs with contacts.json and/or outreach.json (find-contacts, draft-outreach), open jobs only. The main
    contact is the first recruiter, else hiring manager, else team lead, else the first listed."""
    from careeros.ui.services.jobs import job_dir_for

    skip = {*closed, *NO_OUTREACH}
    out: list[OutreachItem] = []
    for r in ix.query("SELECT job_id, company, title, status FROM jobs ORDER BY found_at DESC, job_id"):
        if r["status"] in skip:
            continue
        d = job_dir_for(settings, r["job_id"])
        if d is None or not (d / "contacts.json").is_file() and not (d / "outreach.json").is_file():
            continue
        contacts = [c for c in _json(d / "contacts.json").get("contacts") or [] if isinstance(c, dict) and c.get("name")]
        ou = _json(d / "outreach.json")
        drafts = [x for x in ou.get("drafts") or [] if isinstance(x, dict)]
        if not contacts and not drafts:
            continue
        main = min(contacts, key=lambda c: ROLE_ORDER.get(c.get("role"), 3), default=None)
        cands = (main or {}).get("email_candidates") or []
        due = ou.get("followup_due") or next((x["followup_due"] for x in drafts if x.get("followup_due")), None)
        out.append({
            "job_id": r["job_id"], "company": r["company"] or "", "title": r["title"] or "",
            "contact_name": (main or {}).get("name"), "contact_role": (main or {}).get("role"),
            "email": (main or {}).get("email") or (cands[0] if cands else None),
            "email_confidence": (main or {}).get("email_confidence"),
            "draft_ready": any(x.get("email") or x.get("linkedin_note") or x.get("linkedin_message") for x in drafts),
            "followup_due": due if isinstance(due, str) else None})
    return out


def today(settings: Any, ix: Any, now: datetime, *, tz: tzinfo = timezone.utc,
          soon_hours: int = 48, closed: list[str] | None = None, keep: Collection[str] = ()) -> Today:
    from careeros.ui.services.jobs import with_reasons

    picks = with_reasons(settings, top_picks(ix, now, closed=closed or [], keep=keep))
    return {"actions": open_actions(ix, now, tz, soon_hours), "prepare_queue": prepare_queue(settings, ix, now),
            "top_picks": picks, "outreach": outreach(settings, ix, closed=closed or []), "season": _season(settings, now)}


def _season(settings: Any, now: datetime) -> Season | None:
    from careeros.runs.policy import season_on

    try:
        return season_on(settings.targets or {}, now.date())  # type: ignore[return-value]
    except ConfigError:
        return None
