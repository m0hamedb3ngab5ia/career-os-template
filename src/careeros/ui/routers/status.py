from __future__ import annotations

from fastapi import APIRouter, Depends

from careeros.ui.routers import ctx
from careeros.ui.services import status as svc

router = APIRouter(tags=["status"])


@router.get("/status")
def status(c=Depends(ctx)) -> svc.Status:
    return svc.status(c.settings, c.index, c.now())
