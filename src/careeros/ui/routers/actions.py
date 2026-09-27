"""Action Items: GET /api/actions (tabs, grouping, sorting) and the writes (add, done, reopen, due date, and the
possible-scam item's Block company / Mark posting safe with their undos). Writes go through Tracker."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from careeros.runs.locks import LockBusy
from careeros.ui.routers import ctx
from careeros.ui.services import actions as svc
from careeros.ui.services.reindex import after_write

router = APIRouter(tags=["actions"])


class NewItem(BaseModel):
    what: str
    type: str = "other"
    needs: str = "anytime"
    priority: str = "M"
    job_id: str = ""
    company: str = ""
    role: str = ""
    link: str = ""
    due: str | None = None
    due_reason: str | None = None


class Ids(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


class Due(BaseModel):
    due: str | None = None
    due_reason: str | None = None


class Unblock(BaseModel):
    company: str
    remove: bool = True  # False when the Block found it already blocked (added: False)


class UndoSafe(BaseModel):
    previous_status: str | None = None
    registry_before: dict[str, Any] | None = None


def _run(fn, *args: Any) -> Any:  # noqa: ANN001
    try:
        return fn(*args)
    except LookupError as e:
        raise HTTPException(404, str(e).strip("'\"")) from None
    except LockBusy:
        raise HTTPException(409, "Another settings save is in progress; try again in a moment.") from None


@router.get("/actions")
def list_actions(tab: str = "open", group: str = "due", sort: str = "soonest", tz: str | None = None,
                 c=Depends(ctx)) -> dict[str, Any]:
    from careeros.ui.config import load_ui_config

    ui = load_ui_config(c.settings)
    return svc.list_actions(c.index, tab=tab, group=group, sort=sort, now=c.now(), tz=svc.resolve_tz(tz),
                            soon_hours=ui.due_soon_hours, done_limit=ui.page_size)


@router.post("/actions")
def add_action(body: NewItem, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.add_item, c.settings, body.model_dump())
    after_write(c, tracker=True)
    return out


@router.post("/actions/bulk-done")
def bulk_done(body: Ids, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.mark_done, c.settings, body.ids)
    after_write(c, tracker=True)
    return out


@router.post("/actions/bulk-reopen")
def bulk_reopen(body: Ids, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.reopen, c.settings, body.ids)
    after_write(c, tracker=True)
    return out


@router.post("/actions/{aid}/done")
def done(aid: str, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.mark_done, c.settings, [aid])
    after_write(c, tracker=True)
    return out


@router.post("/actions/{aid}/reopen")
def reopen(aid: str, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.reopen, c.settings, [aid])
    after_write(c, tracker=True)
    return out


@router.post("/actions/{aid}/due")
def set_due(aid: str, body: Due, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.set_due, c.settings, aid, body.due, body.due_reason)
    after_write(c, tracker=True)
    return out


@router.post("/actions/{aid}/block-company")
def block_company(aid: str, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.block_company, c.settings, c.index, aid)
    after_write(c, tracker=True, config=True)
    return out


@router.post("/actions/{aid}/unblock-company")
def unblock_company(aid: str, body: Unblock, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.unblock_company, c.settings, c.index, aid, body.company, body.remove)
    after_write(c, tracker=True, config=True)
    return out


@router.post("/actions/{aid}/mark-safe")
def mark_safe(aid: str, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.mark_safe, c.settings, c.index, aid)
    after_write(c, jobs=[out["job_id"]], tracker=True)
    return out


@router.post("/actions/{aid}/mark-safe/undo")
def undo_mark_safe(aid: str, body: UndoSafe, c=Depends(ctx)) -> dict[str, Any]:
    out = _run(svc.undo_mark_safe, c.settings, c.index, aid, body.previous_status, body.registry_before)
    after_write(c, jobs=[out["job_id"]], tracker=True)
    return out
