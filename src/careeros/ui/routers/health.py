from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from careeros import __version__
from careeros.ui.routers import ctx

router = APIRouter(tags=["health"])


@router.get("/readiness")
def get_readiness(c=Depends(ctx)) -> dict[str, Any]:
    """REQ-102: `{ready, items: [{id, label, must, done, fix_link}]}` (same list as `careeros doctor`)."""
    from careeros.readiness import status
    return status(c.settings.root)


@router.get("/health")
def health(c=Depends(ctx)) -> dict[str, Any]:
    return {"ok": True, "version": __version__, "indexed_at": c.index.get_meta("indexed_at"),
            "config_error": c.config_error}
