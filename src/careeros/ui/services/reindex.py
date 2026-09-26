"""After a UI write: re-index what the write touched right away (so the response and the next GET agree) and
tell every open tab with the same `changed` event the file watcher sends. The watcher still sees the files
change, finds them already indexed, and stays quiet, so each write produces one event."""
from __future__ import annotations

from typing import Any, Iterable


def after_write(ctx: Any, *, jobs: Iterable[str] = (), tracker: bool = False, config: bool = False) -> dict[str, Any]:
    ids = sorted({j for j in jobs if j})
    changed_jobs = ctx.index.update_jobs(ids) if ids else []
    actions = ctx.index.update_tracker() if tracker else False
    if config:
        ctx.reload_settings()
    payload = {"jobs": changed_jobs, "runs": [], "actions": actions, "config": config, "status": False}
    if changed_jobs or actions or config:
        ctx.broker.publish("changed", payload)
    return payload
