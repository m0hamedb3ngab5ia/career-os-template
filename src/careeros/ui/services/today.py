"""The Today screen's "Needs you" list and the size of the next prepare run ("Prepare queued (N)").

Items are shaped by services/actions.py, the one source behind /api/actions (same `due`, `due_date_only`, `level`
fields); Mark done / Undo go through /api/actions/{id}/done|reopen.
"""
from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Any

from careeros.config import ConfigError

PRIORITY = {"H": 0, "M": 1, "L": 2}


def open_actions(ix: Any, now: datetime, tz: tzinfo, soon_hours: int) -> list[dict[str, Any]]:
    """Every open item, shaped by the Action Items service (same due fields: `due`, `due_date_only`, `level`),
    highest priority first."""
    from careeros.ui.services.actions import _item

    rows = ix.query("SELECT * FROM action_items WHERE done = 0")
    items = [_item(r, now, tz, soon_hours) for r in rows if r.get("id")]
    return sorted(items, key=lambda i: (PRIORITY.get(i["priority"], 3), i["created"] or "", i["id"]))


def prepare_queue(settings: Any, now: datetime) -> dict[str, Any]:
    """How many jobs the next prepare run could pick (the same ranking `careeros run status` uses)."""
    from careeros.runs.config import load_runs_config
    from careeros.runs.runner import select_candidates

    try:
        ranked, _ = select_candidates(settings, "prepare", load_runs_config(settings), now)
    except (ConfigError, OSError, ValueError) as e:
        return {"total": None, "error": str(e)}
    return {"total": len(ranked), "error": None}


def today(settings: Any, ix: Any, now: datetime, *, tz: tzinfo = timezone.utc,
          soon_hours: int = 48) -> dict[str, Any]:
    return {"actions": open_actions(ix, now, tz, soon_hours), "prepare_queue": prepare_queue(settings, now)}
