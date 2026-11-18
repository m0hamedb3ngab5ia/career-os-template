from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from careeros.ui.routers import ctx
from careeros.ui.services import catalogue as svc

router = APIRouter(tags=["catalogue"])


@router.get("/catalogue")
def catalogue(c=Depends(ctx)) -> svc.Catalogue:
    """REQ-165: docs/CATALOGUE.md parsed into sections and rows."""
    path = c.settings.root / "docs" / "CATALOGUE.md"
    if not path.is_file():
        raise HTTPException(404, "docs/CATALOGUE.md not found")
    return svc.parse_catalogue(path.read_text(encoding="utf-8"))
