from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from careeros.ui.routers import ctx
from careeros.ui.routers._errors import refusals
from careeros.ui.services import today as svc

router = APIRouter(tags=["today"])


@router.get("/today")
def today(c=Depends(ctx)) -> dict[str, Any]:
    return svc.today(c.settings, c.index, c.now())


@router.post("/today/actions/{item_id}/done")
def mark_done(item_id: str, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return svc.mark_done(c.settings, item_id)


@router.post("/today/actions/{item_id}/reopen")
def reopen(item_id: str, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return svc.reopen(c.settings, item_id)
