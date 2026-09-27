"""GET /api/today. Mark done / Undo on Today go through /api/actions/{id}/done|reopen (one Action Items API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from careeros.ui.routers import ctx
from careeros.ui.services import today as svc

router = APIRouter(tags=["today"])


@router.get("/today")
def today(tz: str | None = None, c=Depends(ctx)) -> svc.Today:
    from careeros.ui.config import load_ui_config
    from careeros.ui.services.actions import resolve_tz

    return svc.today(c.settings, c.index, c.now(), tz=resolve_tz(tz),
                     soon_hours=load_ui_config(c.settings).due_soon_hours)
