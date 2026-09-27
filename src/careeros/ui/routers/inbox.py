from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from careeros.ui.routers import ctx
from careeros.ui.services import inbox as svc

router = APIRouter(tags=["inbox"])


@router.get("/inbox")
def list_inbox(c=Depends(ctx)) -> svc.InboxPage:
    return svc.list_inbox(c.settings, c.index, c.now())


@router.get("/inbox/{job_id}")
def inbox_detail(job_id: str, c=Depends(ctx)) -> svc.InboxDetail:
    d = svc.inbox_detail(c.settings, c.index, job_id, c.now())
    if d is None:
        raise HTTPException(404, f"no job {job_id!r}")
    return d
