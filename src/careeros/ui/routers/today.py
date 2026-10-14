"""GET /api/today. Mark done / Undo on Today go through /api/actions/{id}/done|reopen (one Action Items API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from careeros.ui.routers import ctx
from careeros.ui.services import today as svc

router = APIRouter(tags=["today"])


@router.get("/today")
def today(request: Request, tz: str | None = None, c=Depends(ctx)) -> svc.Today:
    from careeros.ui.config import load_ui_config
    from careeros.ui.routers.jobs import _rc
    from careeros.ui.services.actions import resolve_tz

    cfg = load_ui_config(c.settings)
    return svc.today(c.settings, c.index, c.now(), tz=resolve_tz(tz), soon_hours=cfg.due_soon_hours,
                     closed=cfg.closed,
                     keep=svc.started_ids(c.settings, _rc(request, c)))
