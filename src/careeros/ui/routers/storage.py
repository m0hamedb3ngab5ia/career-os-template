"""Storage & efficiency API: what career-os stores (`careeros storage --json` + its config), the advisor
(`careeros advise --json`, `advise apply <id>`) and Prune (the dry-run list first, then `careeros prune --yes` as
a recorded step run). Everything goes through RunControl, the same code as the CLI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from careeros.config import ConfigError
from careeros.runs.locks import LockBusy
from careeros.ui.routers import ctx
from careeros.ui.services.runs import Busy, RunControl
from careeros.ui.services.storage_view import Advice, StorageView

router = APIRouter(tags=["storage"])


class PruneBody(BaseModel):
    dry_run: bool = True


def relative_path(p: str, root: Path) -> str:
    """A path shown to the browser: relative to the repo root (never the absolute home path)."""
    try:
        return Path(p).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(p).name


def _rc(c: Any) -> Any:
    return RunControl(c.settings, now=c.now)


@router.get("/storage")
def storage(c=Depends(ctx)) -> StorageView:
    from careeros.runs.advisor import load_advisor_config

    return cast(StorageView, {**_rc(c).storage(), "config": load_advisor_config(c.settings.pipeline)})


@router.get("/advise")
def advise(c=Depends(ctx)) -> Advice:
    return cast(Advice, _rc(c).advise())


@router.post("/advise/{rec_id}/apply")
def advise_apply(rec_id: str, c=Depends(ctx)) -> dict[str, Any]:
    try:
        out = _rc(c).advise_apply(rec_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except ConfigError as e:  # before ValueError: ConfigError subclasses it
        raise HTTPException(422, str(e)) from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    except LockBusy:
        raise HTTPException(409, "Another settings save is in progress; try again in a moment.") from None
    c.reload_settings()
    return out


@router.post("/prune")
def prune(body: PruneBody, c=Depends(ctx)) -> dict[str, Any]:
    rc = _rc(c)
    if body.dry_run:
        plan = rc.prune_plan()
        root = c.settings.root
        for item in plan["items"]:
            item["paths"] = [relative_path(p, root) for p in item.get("paths") or []]
        return plan
    try:
        return rc.start_step("prune")
    except Busy as e:
        raise HTTPException(409, str(e)) from None
