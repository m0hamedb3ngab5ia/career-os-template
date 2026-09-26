from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from careeros.ui.routers import ctx
from careeros.ui.services import meta as svc

router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(c=Depends(ctx)) -> dict[str, Any]:
    return svc.meta(c.settings)
