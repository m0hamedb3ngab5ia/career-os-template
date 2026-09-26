"""Writes on one job: POST /api/jobs/{id}/status (status.json + tracker via set_status_both)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from careeros.ui.routers import ctx
from careeros.ui.services import job_actions as svc
from careeros.ui.services.reindex import after_write

router = APIRouter(tags=["jobs"])


class StatusBody(BaseModel):
    status: str
    note: str | None = None


@router.post("/jobs/{job_id}/status")
def set_status(job_id: str, body: StatusBody, c=Depends(ctx)) -> dict[str, Any]:
    try:
        out = svc.set_status(c.settings, job_id, body.status, body.note)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    after_write(c, jobs=[job_id], tracker=True)
    return out
