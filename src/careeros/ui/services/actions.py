"""Action Items screen: the list (tabs, due-date buckets, grouping, sorting) read from the index, and the writes
(add, mark done / reopen, set a due date, and the scam item's Block company / Mark posting safe), which go through
Tracker and the existing safety / settings code. Action Items live in the tracker's Action Items tab until they move
to data/action_items.json (TODO.md).

Time: buckets (Overdue, Today, Tomorrow, Next 7 days, Later, No date) are computed in the viewer's time zone (the
browser sends its IANA name; the server's own zone otherwise). A due date without a time means the end of that day.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from careeros.models import ACTION_NEEDS, ACTION_TYPES, parse_due

TABS = ("open", "today", "done")
GROUPS = ("due", "priority", "needs")
SORTS = ("soonest", "priority", "newest")
BUCKETS = ("overdue", "today", "tomorrow", "week", "later", "nodate")
TODAY_TAB = ("overdue", "today", "tomorrow")
PRIORITIES = ("H", "M", "L")
_PRIO_RANK = {p: i for i, p in enumerate(PRIORITIES)}
_HTTP = re.compile(r"^https?://[^\s]+$", re.I)
MAX_WHAT = 500


# --- time -------------------------------------------------------------------------------------------------------

def resolve_tz(name: str | None) -> tzinfo:
    if not name:
        return datetime.now().astimezone().tzinfo  # type: ignore[return-value]
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown time zone {name!r}") from None


def is_date_only(due: str | None) -> bool:
    """A date with no time: "YYYY-MM-DD", or a naive 00:00 (how Excel stores a typed date)."""
    s = str(due or "").strip()
    return len(s) == 10 or re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]00:00(:00)?", s) is not None


def due_at(due: str | None, tz: tzinfo) -> datetime | None:
    """The moment an item is due, or None. A date alone is the end of that day in `tz`; a naive time is in `tz`."""
    if not due:
        return None
    s = str(due).strip()
    try:
        if is_date_only(s):
            d = date.fromisoformat(s[:10])
            return datetime.combine(d, time(23, 59, 59), tz)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def due_bucket(due: str | None, now: datetime, tz: tzinfo) -> str:
    at = due_at(due, tz)
    if at is None:
        return "nodate"
    if at < now:
        return "overdue"
    days = (at.astimezone(tz).date() - now.astimezone(tz).date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return "week" if days <= 7 else "later"


def due_level(due: str | None, now: datetime, tz: tzinfo, soon_hours: int) -> str:
    """overdue (red) · soon (orange: within `soon_hours`) · later (secondary) · none (no date)."""
    at = due_at(due, tz)
    if at is None:
        return "none"
    if at < now:
        return "overdue"
    return "soon" if at - now <= timedelta(hours=soon_hours) else "later"


# --- the list ---------------------------------------------------------------------------------------------------

def _item(r: dict[str, Any], now: datetime, tz: tzinfo, soon_hours: int) -> dict[str, Any]:
    at = due_at(r.get("due"), tz)
    return {
        "id": r["id"], "created": r.get("created"), "job_id": r.get("job_id") or None,
        "company": r.get("company") or "", "role": r.get("role") or "", "type": r.get("type") or "other",
        "what": r.get("what") or "", "link": r.get("link") or "", "priority": r.get("priority") or "",
        "needs": r.get("needs") or "", "done": bool(r.get("done")), "done_date": r.get("done_date"),
        "due": at.isoformat() if at else None, "due_date_only": bool(at and is_date_only(r.get("due"))),
        "due_reason": r.get("due_reason") if at else None,
        "bucket": due_bucket(r.get("due"), now, tz), "level": due_level(r.get("due"), now, tz, soon_hours),
        # Block company / Mark posting safe act on the item's job, so they need one
        "scam_actions": r.get("type") == "scam_suspected" and bool(r.get("job_id")),
    }


def _sort_key(sort: str):  # noqa: ANN202
    def due_k(i: dict[str, Any]) -> tuple[int, float]:
        return (0, datetime.fromisoformat(i["due"]).timestamp()) if i["due"] else (1, 0.0)

    def prio_k(i: dict[str, Any]) -> int:
        return _PRIO_RANK.get(i["priority"], len(PRIORITIES))

    if sort == "priority":
        return lambda i: (prio_k(i), *due_k(i), i["created"] or "", i["id"])
    if sort == "newest":
        return None
    return lambda i: (*due_k(i), prio_k(i), i["created"] or "", i["id"])


def _ordered(items: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    key = _sort_key(sort)
    if key is None:
        return sorted(items, key=lambda i: (i["created"] or "", i["id"]), reverse=True)
    return sorted(items, key=key)


def _group_order(group: str, present: Iterable[str]) -> list[str]:
    base = {"due": BUCKETS, "priority": PRIORITIES, "needs": ACTION_NEEDS}[group]
    extra = sorted({p for p in present if p not in base})
    return [*base, *extra]


def build_view(rows: list[dict[str, Any]], *, tab: str, group: str, sort: str, now: datetime, tz: tzinfo,
               soon_hours: int, done_limit: int | None = None) -> dict[str, Any]:
    if tab not in TABS:
        raise ValueError(f"tab must be one of {', '.join(TABS)}, got {tab!r}")
    if group not in GROUPS:
        raise ValueError(f"group must be one of {', '.join(GROUPS)}, got {group!r}")
    if sort not in SORTS:
        raise ValueError(f"sort must be one of {', '.join(SORTS)}, got {sort!r}")
    items = [_item(r, now, tz, soon_hours) for r in rows if r.get("id")]
    open_items = [i for i in items if not i["done"]]
    done_items = [i for i in items if i["done"]]
    counts = {"open": len(open_items), "today": sum(1 for i in open_items if i["bucket"] in TODAY_TAB),
              "done": len(done_items)}
    head = {"overdue": sum(1 for i in open_items if i["level"] == "overdue"),
            "soon": sum(1 for i in open_items if i["level"] == "soon")}
    more = 0
    if tab == "done":
        done_items.sort(key=lambda i: (i["done_date"] or "", i["id"]), reverse=True)
        if done_limit is not None and len(done_items) > done_limit:
            more = len(done_items) - done_limit
            done_items = done_items[:done_limit]
        groups = [{"key": "done", "count": counts["done"], "items": done_items}] if done_items else []
    else:
        shown = open_items if tab == "open" else [i for i in open_items if i["bucket"] in TODAY_TAB]
        field = {"due": "bucket", "priority": "priority", "needs": "needs"}[group]
        groups = []
        for k in _group_order(group, (i[field] for i in shown)):
            members = [i for i in shown if i[field] == k]
            if members:
                groups.append({"key": k, "count": len(members), "items": _ordered(members, sort)})
    return {"tab": tab, "group": group, "sort": sort, "counts": counts, "head": head, "groups": groups,
            "more_done": more, "now": now.isoformat()}


def list_actions(ix: Any, *, tab: str, group: str, sort: str, now: datetime, tz: tzinfo, soon_hours: int,
                 done_limit: int) -> dict[str, Any]:
    rows = ix.query("SELECT * FROM action_items")
    return build_view(rows, tab=tab, group=group, sort=sort, now=now, tz=tz, soon_hours=soon_hours,
                      done_limit=done_limit)


# --- writes -----------------------------------------------------------------------------------------------------

def validate_new_item(body: dict[str, Any]) -> dict[str, Any]:
    what = str(body.get("what") or "").strip()
    if not what:
        raise ValueError("what: say what needs doing")
    if len(what) > MAX_WHAT:
        raise ValueError(f"what: keep it under {MAX_WHAT} characters")
    typ = body.get("type") or "other"
    if typ not in ACTION_TYPES:
        raise ValueError(f"type must be one of {', '.join(ACTION_TYPES)}, got {typ!r}")
    needs = body.get("needs") or "anytime"
    if needs not in ACTION_NEEDS:
        raise ValueError(f"needs must be one of {', '.join(ACTION_NEEDS)}, got {needs!r}")
    prio = body.get("priority") or "M"
    if prio not in PRIORITIES:
        raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}, got {prio!r}")
    link = str(body.get("link") or "").strip()
    if link and not _HTTP.match(link):
        raise ValueError("link must start with http:// or https://")
    due = parse_due(body.get("due"))
    reason = str(body.get("due_reason") or "").strip() if due else ""
    return {"what": what, "type": typ, "needs": needs, "priority": prio, "link": link,
            "job_id": str(body.get("job_id") or "").strip(), "company": str(body.get("company") or "").strip(),
            "role": str(body.get("role") or "").strip(), "due": due, "due_reason": reason or None}


def _tracker(settings: Any):  # noqa: ANN202
    from careeros.tracker import Tracker

    return Tracker(settings=settings)


def add_item(settings: Any, body: dict[str, Any]) -> dict[str, Any]:
    from careeros.store import Store

    v = validate_new_item(body)
    if v["job_id"]:
        from careeros.ui.services.jobs import job_dir_for

        if job_dir_for(settings, v["job_id"]) is None:
            raise LookupError(f"no job {v['job_id']!r}")
        p = Store(settings).load_posting(v["job_id"])
        if p:
            v["company"], v["role"] = v["company"] or p.company, v["role"] or p.title
    aid = _tracker(settings).add_action_item(**v)
    return {"id": aid}


def mark_done(settings: Any, ids: list[str]) -> dict[str, Any]:
    tr = _tracker(settings)
    results = {i: tr.mark_action_done(i) for i in dict.fromkeys(ids)}
    return _outcome(results)


def reopen(settings: Any, ids: list[str]) -> dict[str, Any]:
    tr = _tracker(settings)
    return _outcome({i: tr.reopen_action(i) for i in dict.fromkeys(ids)})


def set_due(settings: Any, aid: str, due: str | None, reason: str | None) -> dict[str, Any]:
    return _outcome({aid: _tracker(settings).set_action_due(aid, due, reason)})


def _outcome(results: dict[str, bool | None]) -> dict[str, Any]:
    missing = [i for i, r in results.items() if r is False]
    if missing and len(missing) == len(results):
        raise LookupError(f"no action item {missing[0]!r}" if len(missing) == 1
                          else f"no action items {', '.join(missing)}")
    return {"ok": [i for i, r in results.items() if r], "queued": [i for i, r in results.items() if r is None],
            "missing": missing}


def get_item(ix: Any, aid: str) -> dict[str, Any]:
    rows = ix.query("SELECT * FROM action_items WHERE id = ?", (aid,))
    if not rows:
        raise LookupError(f"no action item {aid!r}")
    return rows[0]


def _scam_item(ix: Any, aid: str) -> dict[str, Any]:
    it = get_item(ix, aid)
    if it.get("type") != "scam_suspected" or not it.get("job_id"):
        raise ValueError("only a possible-scam item with a job can block its company or mark its posting safe")
    return it


def _company(settings: Any, it: dict[str, Any]) -> str:
    from careeros.store import Store

    p = Store(settings).load_posting(it["job_id"])
    company = (p.company if p else "") or it.get("company") or ""
    if not company.strip():
        raise ValueError("this item's job has no company name to block")
    return company.strip()


def _blocklist_path(settings: Any):  # noqa: ANN202
    from careeros.ui.services.settings_io import config_path

    return config_path(settings, "companies")


def _set_blocklist(settings: Any, companies: list[str]) -> None:
    from careeros.runs import yamledit
    from careeros.ui.services.settings_io import validate_root

    root = settings.root
    yamledit.apply_changes(_blocklist_path(settings), [("blocklist.companies", companies)],
                           validate=lambda _p: validate_root(root))


def _current_blocklist(settings: Any) -> list[str]:
    import yaml

    data = yaml.safe_load(_blocklist_path(settings).read_text(encoding="utf-8")) or {}
    return [str(c) for c in ((data.get("blocklist") or {}).get("companies") or [])]


def block_company(settings: Any, ix: Any, aid: str) -> dict[str, Any]:
    """Add the item's company to companies.yaml blocklist.companies (comment-preserving, validated, rolled back
    on error) and mark the item done. `added` is False when it was already blocked (undo then leaves it)."""
    from careeros.config import _fuzzy_eq, normalize_company

    it = _scam_item(ix, aid)
    company = _company(settings, it)
    current = _current_blocklist(settings)
    key = normalize_company(company)
    added = not any(_fuzzy_eq(key, normalize_company(c)) for c in current)
    if added:
        _set_blocklist(settings, [*current, company])
    done = _tracker(settings).mark_action_done(aid)
    return {"company": company, "added": added, "queued": done is None, "job_id": it["job_id"]}


def unblock_company(settings: Any, ix: Any, aid: str, company: str, remove: bool = True) -> dict[str, Any]:
    """Undo Block company: remove exactly that name from the blocklist and reopen the item. `remove=False` (the
    Block found it already blocked, `added: False`) only reopens the item and leaves the user's entry alone."""
    it = _scam_item(ix, aid)
    if company.strip().lower() != _company(settings, it).lower():
        raise ValueError("that company isn't this item's company")
    current = _current_blocklist(settings)
    kept = [c for c in current if c.strip().lower() != company.strip().lower()] if remove else current
    if kept != current:
        _set_blocklist(settings, kept)
    done = _tracker(settings).reopen_action(aid)
    return {"company": company, "removed": kept != current, "queued": done is None}


REGISTRY_KEYS = ("company", "domain", "reason", "confidence", "state", "evidence", "first_seen", "last_seen",
                 "expires_at", "count", "job_ids", "review_note")


def mark_safe(settings: Any, ix: Any, aid: str) -> dict[str, Any]:
    """Clear the company in the flagged registry (`careeros safety clear`), set the job back to queued in
    status.json and the tracker, and mark the item done. Returns what undo needs to put back."""
    from careeros.safety import registry
    from careeros.store import Store
    from careeros.tracker import set_status_both

    from careeros.ui.services.job_actions import ensure_unlocked

    it = _scam_item(ix, aid)
    ensure_unlocked(settings, it["job_id"])
    company = _company(settings, it)
    path = registry.default_path(settings)
    before = registry._find(registry.load(path), company)
    if before is not None:
        before = {k: before[k] for k in REGISTRY_KEYS if k in before}
        registry.clear(path, company, note="marked safe in careeros ui")
    previous = Store(settings).get_status(it["job_id"])
    set_status_both(settings, it["job_id"], "queued", "marked safe in careeros ui")
    done = _tracker(settings).mark_action_done(aid)
    return {"company": company, "job_id": it["job_id"], "previous_status": previous, "registry_before": before,
            "queued": done is None}


def undo_mark_safe(settings: Any, ix: Any, aid: str, previous_status: str | None,
                   registry_before: dict[str, Any] | None) -> dict[str, Any]:
    from careeros.models import STATUSES
    from careeros.safety import registry
    from careeros.tracker import set_status_both
    from careeros.ui.services.job_actions import ensure_unlocked

    it = _scam_item(ix, aid)
    ensure_unlocked(settings, it["job_id"])
    company = _company(settings, it)
    if registry_before is not None:
        from careeros.config import _fuzzy_eq, normalize_company

        # mark_safe found the entry with registry._find()'s fuzzy match, so the saved name may differ from the
        # posting's ("Acme Health" for "Acme Health Careers"): accept exactly what that match accepts
        name = str(registry_before.get("company") or "") if isinstance(registry_before, dict) else ""
        if not (name and _fuzzy_eq(normalize_company(name), normalize_company(company))):
            raise ValueError("registry_before must be this company's registry entry")
        registry.restore(registry.default_path(settings), {k: registry_before[k] for k in REGISTRY_KEYS
                                                           if k in registry_before})
    if previous_status:
        if previous_status not in STATUSES:
            raise ValueError(f"unknown status {previous_status!r}")
        set_status_both(settings, it["job_id"], previous_status, "undo: marked safe")
    done = _tracker(settings).reopen_action(aid)
    return {"company": company, "job_id": it["job_id"], "status": previous_status, "queued": done is None}
