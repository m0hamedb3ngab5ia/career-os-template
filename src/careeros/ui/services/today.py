"""The Today screen's "Needs you" list (every open Action Item, from the index) with Mark done / Undo through
the Tracker, and the size of the next prepare run ("Prepare queued (N)").

Action Items live in the tracker's Action Items tab until data/action_items.json exists (TODO.md), so writes go
through `Tracker` and inherit its lock + pending-queue handling. `due` / `due_reason` are served as null until
`ActionItem` gains them (docs/UI.md, Action Items); the UI never invents a deadline.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from careeros.config import ConfigError

PRIORITY_ORDER = "CASE priority WHEN 'H' THEN 0 WHEN 'M' THEN 1 WHEN 'L' THEN 2 ELSE 3 END"
FIELDS = ("id", "job_id", "company", "role", "what", "type", "priority", "needs", "link", "created")


def open_actions(ix: Any) -> list[dict[str, Any]]:
    rows = ix.query(f"SELECT {', '.join(FIELDS)} FROM action_items WHERE done = 0 "
                    f"ORDER BY {PRIORITY_ORDER}, created, id")
    return [{**r, "due": None, "due_reason": None} for r in rows]


def _write(settings: Any, method: str, item_id: str) -> dict[str, Any]:
    from careeros.tracker import Tracker

    if not isinstance(item_id, str) or not item_id.strip():
        raise LookupError("no such action item")
    got = getattr(Tracker(settings=settings), method)(item_id)
    if got is False:
        raise LookupError(f"no action item {item_id!r}")
    return {"ok": True, "queued": got is None}


def mark_done(settings: Any, item_id: str) -> dict[str, Any]:
    return _write(settings, "mark_action_done", item_id)


def reopen(settings: Any, item_id: str) -> dict[str, Any]:
    return _write(settings, "reopen_action", item_id)


def prepare_queue(settings: Any, now: datetime) -> dict[str, Any]:
    """How many jobs the next prepare run could pick (the same ranking `careeros run status` uses)."""
    from careeros.runs.config import load_runs_config
    from careeros.runs.runner import select_candidates

    try:
        ranked, _ = select_candidates(settings, "prepare", load_runs_config(settings), now)
    except (ConfigError, OSError, ValueError) as e:
        return {"total": None, "error": str(e)}
    return {"total": len(ranked), "error": None}


def today(settings: Any, ix: Any, now: datetime) -> dict[str, Any]:
    return {"actions": open_actions(ix), "prepare_queue": prepare_queue(settings, now)}
