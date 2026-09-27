from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from careeros.ui.routers import ctx
from careeros.ui.services import contacts as svc

router = APIRouter(tags=["contacts"])


class MarkBody(BaseModel):
    degree: int | None = Field(default=None, ge=1, le=3)
    mutuals: int | None = Field(default=None, ge=0)


@router.get("/contacts")
def list_contacts(c=Depends(ctx)) -> dict[str, Any]:
    return svc.list_contacts(c.settings, c.index)


@router.post("/contacts/{job_id}/{name}/mark")
def mark_contact(job_id: str, name: str, body: MarkBody, c=Depends(ctx)) -> dict[str, Any]:
    try:
        return svc.mark(c.settings, job_id, name, degree=body.degree, mutuals=body.mutuals)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
