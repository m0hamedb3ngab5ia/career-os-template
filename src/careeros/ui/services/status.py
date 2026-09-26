"""GET /api/status: the Today screen's stat tiles (each with the rows its popover lists), the Pipeline counts,
sidebar counts, recent runs, pause / catch-up state and the next scheduled runs.

Everything is counted from the index; no data means zeros and empty lists, never a made-up number.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from careeros.config import ConfigError
from careeros.ui.config import load_ui_config

POST_APPLY = ("applied", "screening", "interview", "offer")      # the Inbox & follow-ups list
RESPONDED = ("screening", "interview", "offer", "rejected")
RESPONSE_DAYS = 30
ROWS = 10
_PRIO = "CASE priority WHEN 'H' THEN 0 WHEN 'M' THEN 1 WHEN 'L' THEN 2 ELSE 3 END"


def _parse(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.astimezone()


def week_start(now: datetime) -> datetime:
    """Monday 00:00 local time of `now`'s week."""
    local = now.astimezone()
    return (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def _job_row(j: dict[str, Any], detail: str, when: str | None) -> dict[str, Any]:
    return {"job_id": j["job_id"], "company": j["company"], "role": j["title"], "detail": detail, "when": when}


def tiles(ix: Any, settings: Any, now: datetime) -> dict[str, Any]:
    from careeros.runs.policy import daily_cap

    applied = [j for j in ix.query("SELECT * FROM jobs WHERE applied_at IS NOT NULL ORDER BY applied_at DESC")
               if _parse(j["applied_at"])]
    ws = week_start(now)
    this_week = [j for j in applied if _parse(j["applied_at"]) >= ws]
    open_items = ix.query(f"SELECT * FROM action_items WHERE done = 0 ORDER BY {_PRIO}, created")
    interviews = ix.query("SELECT * FROM jobs WHERE status = 'interview' ORDER BY updated_at DESC")
    window = [j for j in applied if _parse(j["applied_at"]) >= now - timedelta(days=RESPONSE_DAYS)]
    responded = [j for j in window if j["status"] in RESPONDED]
    return {
        "applied_week": {"value": len(this_week), "since": ws.isoformat(),
                         "daily_cap": daily_cap(settings.targets or {}, now.astimezone().date()),
                         "rows": [_job_row(j, j["status"], j["applied_at"]) for j in this_week[:ROWS]]},
        "needs_you": {"value": len(open_items), "high": sum(1 for a in open_items if a["priority"] == "H"),
                      "rows": [{"id": a["id"], "job_id": a["job_id"], "company": a["company"], "role": a["role"],
                                "what": a["what"], "type": a["type"], "priority": a["priority"],
                                "needs": a["needs"], "link": a["link"], "created": a["created"]}
                               for a in open_items[:ROWS]]},
        "interviews": {"value": len(interviews),
                       "rows": [_job_row(j, "interview", j["updated_at"]) for j in interviews[:ROWS]]},
        "response_rate": {"rate": (len(responded) / len(window)) if window else None, "responded": len(responded),
                          "applied": len(window), "days": RESPONSE_DAYS,
                          "definition": f"applications in the last {RESPONSE_DAYS} days that reached "
                                        f"{', '.join(RESPONDED[:-1])} or {RESPONDED[-1]}",
                          "rows": [_job_row(j, j["status"], j["applied_at"]) for j in responded[:ROWS]]},
    }


def pipeline(ix: Any, settings: Any) -> dict[str, Any]:
    ui = load_ui_config(settings)
    by = {r["status"]: r["n"] for r in ix.query("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")}
    closed = {s: by[s] for s in ui.closed if by.get(s)}
    return {"columns": [{"name": c["name"], "statuses": c["statuses"], "count": sum(by.get(s, 0) for s in c["statuses"])}
                        for c in ui.columns],
            "closed": {"count": sum(closed.values()), "by_status": closed}}


def run_row(r: dict[str, Any]) -> dict[str, Any]:
    from careeros.runs.locks import pid_alive

    out = {k: r[k] for k in ("id", "kind", "trigger", "status", "stop_reason", "detail", "started_at", "ended_at",
                             "duration_s", "attempted", "ok", "failed")}
    out["interrupted"] = r["status"] == "running" and not (r["pid"] and pid_alive(int(r["pid"])))
    return out


def schedule(settings: Any, now: datetime) -> dict[str, Any]:
    from careeros.runs.tick import schedule_overview

    try:
        ov = schedule_overview(settings, now)
    except ConfigError as e:
        return {"last_tick": None, "next": {}, "error": str(e)}
    return {"last_tick": ov["last_tick"], "next": ov["next"], "error": None}


def status(settings: Any, ix: Any, now: datetime) -> dict[str, Any]:
    from careeros.runs.store import RunStore
    from careeros.runs.tick import load_catch_up

    rs = RunStore(settings)
    one = lambda sql, params=(): ix.query(sql, params)[0]["n"]  # noqa: E731
    return {
        "now": now.isoformat(),
        "tiles": tiles(ix, settings, now),
        "pipeline": pipeline(ix, settings),
        "counts": {"jobs": one("SELECT COUNT(*) AS n FROM jobs"),
                   "action_items_open": one("SELECT COUNT(*) AS n FROM action_items WHERE done = 0"),
                   "inbox": one(f"SELECT COUNT(*) AS n FROM jobs WHERE status IN ({','.join('?' * len(POST_APPLY))})",
                                POST_APPLY),
                   "contacts": one("SELECT COUNT(*) AS n FROM contacts")},
        "recent_runs": [run_row(r) for r in ix.query("SELECT * FROM runs ORDER BY started_at DESC LIMIT 5")],
        "paused": rs.pause_state(now),
        "catch_up": load_catch_up(rs),
        "schedule": schedule(settings, now),
        "index": {"indexed_at": ix.get_meta("indexed_at")},
    }
