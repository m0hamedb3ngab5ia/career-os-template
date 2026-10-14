"""GET/PUT /api/ui-state (REQ-121): per-install UI flags in data/ui_state.json, so the first-run tour shows once
per install, not per browser. A missing or broken file reads as the defaults."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StrictBool

from careeros.runs.atomic import write_json
from careeros.ui.routers import ctx

router = APIRouter(tags=["ui-state"])


class UiState(BaseModel):
    tour_done: StrictBool = False
    jobs_view: Literal["list", "table", "board"] | None = None   # Jobs page view, last choice (REQ-129)


def _path(c) -> Path:  # noqa: ANN001
    return c.settings.root / "data" / "ui_state.json"


@router.get("/ui-state", response_model_exclude_none=True)
def get_ui_state(c=Depends(ctx)) -> UiState:
    try:
        return UiState.model_validate(json.loads(_path(c).read_text()))
    except (OSError, ValueError):
        return UiState()


@router.put("/ui-state", response_model_exclude_none=True)
def put_ui_state(body: UiState, c=Depends(ctx)) -> UiState:
    """Merge: only the keys sent change, so the tour and the Jobs view never overwrite each other."""
    merged = get_ui_state(c).model_copy(update=body.model_dump(exclude_unset=True))
    write_json(_path(c), merged.model_dump(exclude_none=True))
    return merged
