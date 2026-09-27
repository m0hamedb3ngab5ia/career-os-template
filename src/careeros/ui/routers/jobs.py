from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from careeros.ui.routers import ctx
from careeros.ui.services import jobs as svc

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs(status: list[str] = Query(default=[]), tier: list[str] = Query(default=[]),
              safety: list[str] = Query(default=[]), category: list[str] = Query(default=[]), q: str | None = None,
              sort: str = svc.DEFAULT_SORT, cursor: str | None = None,
              limit: int | None = Query(default=None, ge=1, le=svc.MAX_LIMIT), c=Depends(ctx)) -> dict[str, Any]:
    from careeros.ui.config import load_ui_config

    return svc.list_jobs(c.index, status=status, tier=tier, safety=safety, category=category, q=q, sort=sort,
                         cursor=cursor, limit=limit or load_ui_config(c.settings).page_size)


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, c=Depends(ctx)) -> dict[str, Any]:
    d = svc.job_detail(c.settings, c.index, job_id)
    if d is None:
        raise HTTPException(404, f"no job {job_id!r}")
    return d
