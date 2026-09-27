"""API routers, one per area; each reads `request.app.state.ctx` and calls careeros.ui.services."""
from __future__ import annotations

from fastapi import Request


def ctx(request: Request):
    return request.app.state.ctx
