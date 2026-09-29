"""The Today screen's "Needs you" list and the size of the next prepare run ("Prepare queued (N)").

Items are shaped by services/actions.py, the one source behind /api/actions (same `due`, `due_date_only`, `level`
fields); Mark done / Undo go through /api/actions/{id}/done|reopen.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, tzinfo
from typing import Any

from typing_extensions import TypedDict

from careeros.config import ConfigError
from careeros.ui.services.actions import ActionItem

PRIORITY = {"H": 0, "M": 1, "L": 2}


# Response shapes (OpenAPI -> ui/src/api/schema.gen.ts).
class PrepareQueue(TypedDict):
    total: int | None
    error: str | None


class Today(TypedDict):
    actions: list[ActionItem]
    prepare_queue: PrepareQueue


def open_actions(ix: Any, now: datetime, tz: tzinfo, soon_hours: int) -> list[ActionItem]:
    """Every open item, shaped by the Action Items service (same due fields: `due`, `due_date_only`, `level`),
    highest priority first."""
    from careeros.ui.services.actions import _item

    rows = ix.query("SELECT * FROM action_items WHERE done = 0")
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


def today(settings: Any, ix: Any, now: datetime, *, tz: tzinfo = timezone.utc,
          soon_hours: int = 48) -> Today:
    return {"actions": open_actions(ix, now, tz, soon_hours), "prepare_queue": prepare_queue(settings, ix, now)}
