"""Settings API: the section list, one section's schema + values, a diff preview, a save (all keys at once, rolled
back on any error), "Reset to recommended" proposals and the Runs page's ranking preview. Logic lives in
careeros.ui.services.settings_io / settings_page."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from careeros.ui.routers import ctx
from careeros.ui.services import settings_io
from careeros.ui.services import settings_page as page

router = APIRouter(tags=["settings"])


class Changes(BaseModel):
    changes: dict[str, Any] = Field(default_factory=dict)
    version: str | None = None


class Preview(BaseModel):
    kind: str = "score"
    weights: dict[str, Any] = Field(default_factory=dict)


def _invalid(e: settings_io.SettingsInvalid) -> JSONResponse:
    return JSONResponse(page.invalid_body(e), status_code=422)


@router.get("/settings")
def sections() -> dict[str, Any]:
    return {"sections": page.section_list()}


@router.get("/settings/{section}")
def read(section: str, c=Depends(ctx)) -> dict[str, Any]:
    try:
        out = settings_io.read_section(c.settings, section)
    except KeyError:
        raise HTTPException(404, f"no settings section {section!r}") from None
    return {**out, "files": page.relative_files(out["files"], c.settings.root)}


@router.post("/settings/runs/ranking-preview")
def ranking_preview(body: Preview, c=Depends(ctx)) -> dict[str, Any]:
    return page.ranking_preview(c.settings, body.kind, body.weights, c.now())


@router.post("/settings/{section}/diff", response_model=None)
def diff(section: str, body: Changes, c=Depends(ctx)) -> dict[str, Any] | JSONResponse:
    try:
        return settings_io.diff_section(c.settings, section, body.changes)
    except KeyError:
        raise HTTPException(404, f"no settings section {section!r}") from None
    except settings_io.SettingsInvalid as e:
        return _invalid(e)


@router.put("/settings/{section}", response_model=None)
def save(section: str, body: Changes, c=Depends(ctx)) -> dict[str, Any] | JSONResponse:
    try:
        out = settings_io.save_section(c.settings, section, body.changes, version=body.version)
    except KeyError:
        raise HTTPException(404, f"no settings section {section!r}") from None
    except settings_io.SettingsInvalid as e:
        return _invalid(e)
    except settings_io.SettingsConflict as e:
        raise HTTPException(409, str(e)) from None
    c.reload_settings()
    return out


@router.post("/settings/{section}/reset/{group}")
def reset(section: str, group: str) -> dict[str, Any]:
    try:
        return {"changes": settings_io.reset_changes(section, group)}
    except KeyError:
        raise HTTPException(404, f"no settings group {section}/{group}") from None
