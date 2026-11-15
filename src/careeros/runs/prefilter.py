"""Score runs: skip obvious misses in code before spawning a headless claude session.

The deterministic hard filters (`careeros.hard_filters`, same as `careeros job filters`) run first. A fail writes
the skip score.json, sets status `skipped` and records the attempt with outcome `prefiltered`; no session starts,
no run budget slot is used.
"""
from __future__ import annotations

import os
from typing import Any

from careeros.config import Settings
from careeros.hard_filters import hard_filters, write_skip
from careeros.runs import locks
from careeros.runs.store import iso
from careeros.store import Store


def prefilter_fails(settings: Settings, store: Store, job_id: str) -> list[str]:
    posting = store._read(job_id, "posting.json")
    return hard_filters(settings, posting) if posting else []


def dry_run_prefiltered(settings: Settings, store: Store, ranked: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {r["job_id"]: f for r in ranked if (f := prefilter_fails(settings, store, r["job_id"]))}


def prefilter_attempt(loop: Any, item: dict[str, Any]) -> dict[str, Any] | None:
    """The attempt record for a job the hard filters reject (verdict written), else None. `loop` is the run loop."""
    from careeros.tracker import set_status_both

    jid = item["job_id"]
    fails = prefilter_fails(loop.s, loop.store, jid)
    if not fails:
        return None
    lock = locks.acquire(loop.rs.job_lock_path(jid), owner=f"run:{loop.run['id']}", pid=os.getpid(),
                         ttl_seconds=300, note=f"prefilter {jid}")
    try:
        n, _ = loop._next_attempt()  # after the job lock: a locked job never burns a number
        write_skip(loop.s, jid, loop.store._read(jid, "posting.json"), fails, loop.store)
        if (loop.store.get_status(jid) or "found") == "found":
            set_status_both(loop.s, jid, "skipped", f"prefilter: {fails[0]} (run {loop.run['id']})"[:200])
    finally:
        locks.release(loop.rs.job_lock_path(jid), lock.token)
    t = loop.now()
    att = {"n": n, "run_id": loop.run["id"], "job_id": jid, "company": item.get("company"),
           "title": item.get("title"), "stage": "score", "rank": item.get("rank"), "why": item.get("why"),
           "session_id": None, "outcome": "prefiltered", "detail": ", ".join(fails), "result": None,
           "started_at": iso(t), "ended_at": iso(t), "duration_s": 0.0, "stream": None, "headless": None}
    loop.rs.save_attempt(loop.run["id"], att)
    with loop._mu:
        loop.run["attempts"] = sorted([*loop.run["attempts"], n])
    loop.rs.log(loop.run["id"], f"attempt {n} score {jid} -> prefiltered: {att['detail']}")
    loop.echo(f"[{n}] score {jid} prefiltered: {att['detail']}")
    if loop.after_attempt:
        with loop._mu:
            loop.after_attempt(att)
    return att
