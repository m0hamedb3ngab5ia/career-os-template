"""API routers, one per area; each reads `request.app.state.ctx` and calls careeros.ui.services."""
from __future__ import annotations

from fastapi import Request


def ctx(request: Request):  # noqa: ANN201 - careeros.ui.app.Context (import cycle)
    return request.app.state.ctx
