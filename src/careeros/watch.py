"""REQ-159 target watch. Watched companies = `companies.yaml: dream_list` (+ prestige auto-dream) plus any
`boards[]` entry with `watch: true`. After a tick scores jobs, a job at a watched company that is not hard-filtered
gets (a) one line in the next digest ("New at your target companies") and (b) when fit >= `notify.urgent_min_fit`
(default 85) one high-priority Today item (Detail marker `watch`, Dismiss works) plus one urgent email, each once."""
from __future__ import annotations

import hashlib
from typing import Any, Callable

from careeros.config import Settings, normalize_company
from careeros.follow_ups import TYPE
from careeros.store import Store

WATCH = "watch"  # Detail marker; Action Item Type stays `follow_up` (no schema change)
DEFAULT_MIN_FIT = 85


def _extra(s: Settings) -> set[str]:
    return {normalize_company(str(b["company"])) for b in s.companies.get("boards") or []
            if isinstance(b, dict) and b.get("watch") is True and b.get("company")}


def is_watched(s: Settings, company: str) -> bool:
    return s.is_dream(company) or normalize_company(company) in _extra(s)


def min_fit(s: Settings) -> int:
    try:
        return int((s.pipeline.get("notify") or {}).get("urgent_min_fit", DEFAULT_MIN_FIT))
    except (TypeError, ValueError):
        return DEFAULT_MIN_FIT


def scan_watch(s: Settings, *, send: Callable[..., str] | None = None) -> list[str]:
    """Returns the job ids newly surfaced this call. Each job is handled once (state `watch_seen` in notify.json)."""
    from careeros import notify
    from careeros.tracker import add_action

    if not s.merged_dream_list() and not _extra(s):
        return []
    store, st = Store(s), notify._state(s)
    if "watch_seen" not in st:  # first run: baseline existing jobs so rollout doesn't flood urgent emails
        notify._save(s, watch_seen=list(store.iter_job_ids()), watch_pending=[])
        return []
    seen = list(st.get("watch_seen") or [])
    pending = list(st.get("watch_pending") or [])
    new: list[str] = []
    for jid in store.iter_job_ids():
        if jid in seen:
            continue
        sc, p = store.load_score(jid), store.load_posting(jid)
        if not sc or not p or not is_watched(s, p.company):
            continue
        seen.append(jid)
        if sc.hard_filter_fails:
            continue
        new.append(jid)
        pending.append(jid)
        if sc.fit >= min_fit(s):
            add_action(s, f"New high-match job at {p.company}: {p.title} (fit {sc.fit}). Apply as soon as possible.",
                       TYPE, job_id=jid, detail=WATCH, priority="H", link=p.url or "",
                       due_reason="Postings at target companies fill fast", id=hashlib.sha1(f"{jid}|{WATCH}".encode()).hexdigest()[:8])
            (send or notify.send_urgent)(
                s, f"job:{jid}", f"{p.title} at {p.company} (fit {sc.fit})",
                f"{p.title} at {p.company}\nFit: {sc.fit}\n{p.url or ''}\n\nApply as soon as possible.")
    notify._save(s, watch_seen=seen, watch_pending=pending)
    return new
