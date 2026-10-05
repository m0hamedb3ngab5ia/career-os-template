"""GET/PUT /api/ui-state (REQ-121): per-install UI flags in data/ui_state.json, so the first-run tour shows once
per install, not per browser. A missing or broken file reads as the defaults."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StrictBool

from careeros.runs.atomic import write_json
from careeros.ui.routers import ctx

router = APIRouter(tags=["ui-state"])


class UiState(BaseModel):
    tour_done: StrictBool = False


def _path(c) -> Path:  # noqa: ANN001
    return c.settings.root / "data" / "ui_state.json"


@router.get("/ui-state")
def get_ui_state(c=Depends(ctx)) -> UiState:
    try:
        return UiState.model_validate(json.loads(_path(c).read_text()))
    except (OSError, ValueError):
        return UiState()


@router.put("/ui-state")
def put_ui_state(body: UiState, c=Depends(ctx)) -> UiState:
    write_json(_path(c), body.model_dump())
    return body
