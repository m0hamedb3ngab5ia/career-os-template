"""GET /api/next-step (REQ-122): the one next action for the Today card, from the first rule that holds:
setup open -> Finish setup; no active (non-closed) jobs -> Find jobs (scout); none ticked -> Pick jobs; a batch running -> See progress;
else Start pipeline."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from careeros.ui.routers import ctx

router = APIRouter(tags=["next-step"])


class NextStep(BaseModel):
    key: str
    label: str
    href: str | None = None  # None for find_jobs: the button starts a scout run


def pick(items: list[dict[str, Any]], *, jobs: int, ticked: int, running_batch: str | None) -> NextStep:
    if open_ := [i for i in items if i["must"] and not i["done"]]:
        return NextStep(key="finish_setup", label="Finish setup", href=open_[0]["fix_link"])
    if not jobs:
        return NextStep(key="find_jobs", label="Find jobs")
    if not ticked:
        return NextStep(key="pick_jobs", label="Pick jobs", href="/jobs")
    if running_batch:
        return NextStep(key="see_progress", label="See progress", href=f"/pipeline/batch/{quote(running_batch, safe='')}")
    return NextStep(key="start_pipeline", label="Start pipeline", href="/pipeline/batch/new")


@router.get("/next-step")
def next_step(c=Depends(ctx)) -> NextStep:
    from careeros import readiness
    from careeros.runs import batches
    from careeros.ui.config import load_ui_config
    from careeros.ui.services.jobs import _tab_clause

    where, params = _tab_clause("active", load_ui_config(c.settings).closed)
    row = c.index.query("SELECT COUNT(*) AS n, COALESCE(SUM(selected), 0) AS t FROM jobs"
                        + (f" WHERE {where}" if where else ""), params)[0]
    running = next((b for b in batches.list_ids(c.settings) if batches.running(c.settings, b)), None)
    return pick(readiness.items(c.settings.root), jobs=row["n"], ticked=row["t"], running_batch=running)
