"""The run controls the Today screen needs: catch up / skip missed runs, resume, Run scout and Prepare queued.
All through RunControl (services/runs.py), the same code as `careeros run ...`. Minimal on purpose: the Runs
screen's router can absorb these routes (same paths, same bodies)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from careeros.ui.routers import ctx
from careeros.ui.routers._errors import refusals

router = APIRouter(tags=["runs"])


class CatchUp(BaseModel):
    dismiss: bool = False


class Batch(BaseModel):
    preset: str | None = None


def run_control(c: Any) -> Any:
    """Tests put their own RunControl (fake popen) on the context."""
    from careeros.ui.services.runs import RunControl

    return getattr(c, "run_control", None) or RunControl(c.settings, now=c.now)


@router.post("/runs/catch-up")
def catch_up(body: CatchUp, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return run_control(c).catch_up(dismiss=body.dismiss)


@router.post("/runs/resume")
def resume(c=Depends(ctx)) -> dict[str, Any]:
    return {"resumed": bool(run_control(c).resume())}


@router.post("/runs/steps/scout")
def start_scout(c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return run_control(c).start_step("scout")


@router.post("/runs/batches/prepare")
def start_prepare(body: Batch, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return run_control(c).start("prepare", preset=body.preset or None)
