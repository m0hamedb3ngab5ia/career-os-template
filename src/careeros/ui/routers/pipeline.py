"""GET /api/pipeline: funnel counts, applications (applied → offer), the Closed line, filter options."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from careeros.ui.routers import ctx
from careeros.ui.services import pipeline as svc

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline")
def board(tier: list[str] = Query(default=[]), category: list[str] = Query(default=[]),
          safety: list[str] = Query(default=[]), location: list[str] = Query(default=[]),
          c=Depends(ctx)) -> svc.Board:
    return svc.board(c.settings, c.index, tier=tier, category=category, safety=safety, location=location)
