from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from careeros.ui.routers import ctx
from careeros.ui.routers._errors import refusals
from careeros.ui.services import job_actions as svc

router = APIRouter(tags=["tracker"])


@router.post("/tracker/sync")
def sync(c=Depends(ctx)) -> dict[str, Any]:
    return svc.sync_tracker(c.settings)


@router.post("/tracker/open")
def open_tracker(c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return svc.open_tracker(c.settings)
