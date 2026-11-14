"""Master proposal routes: GET/approve/reject for the pending `profile/master.yaml` update (REQ-099).

Kept because /extract-master tells the candidate to approve through `POST /api/profile/master/proposal/approve`
and no CLI approves or rejects yet. Every other résumé route went with the Profile pages (DEC-024); use
`careeros resume ...` and the skills instead (docs/CHAT.md)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from careeros import master_sync
from careeros.ui.routers import ctx

router = APIRouter(tags=["resumes"])


class MasterProposal(BaseModel):
    state: Literal["synced", "pending", "rejected", "stale"]
    diff: str


@router.get("/profile/master/proposal")
def get_master_proposal(c=Depends(ctx)) -> MasterProposal:
    return MasterProposal(**master_sync.state(c.settings.root))


@router.post("/profile/master/proposal/approve")
def approve_master_proposal(c=Depends(ctx)) -> MasterProposal:
    try:
        return MasterProposal(**master_sync.approve(c.settings.root))
    except (master_sync.Invalid, ValueError) as e:
        raise HTTPException(422, str(e)) from None


@router.post("/profile/master/proposal/reject")
def reject_master_proposal(c=Depends(ctx)) -> MasterProposal:
    try:
        return MasterProposal(**master_sync.reject(c.settings.root))
    except (master_sync.Invalid, ValueError) as e:
        raise HTTPException(422, str(e)) from None
