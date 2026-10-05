"""Batches: preview (dry run), create, read, start (spawns `careeros batch run <id>` detached), pause, cancel, retry
(runs/batches.py). Bad input (unknown stop point, no runnable job) -> 422; a running driver -> 409."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from careeros.runs import batches
from careeros.ui.routers import ctx
from careeros.ui.routers.runs import run_control
from careeros.ui.services.reindex import after_write
from careeros.ui.services.runs import RunControl

router = APIRouter(tags=["batches"])


class CreateBody(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=batches.MAX_JOBS)
    stop_at: Literal["score", "prepare", "fill", "submit"]
    stops: dict[str, Literal["score", "prepare", "fill", "submit"]] | None = None  # per job; server caps them
    name: str | None = Field(default=None, max_length=120)
    dry_run: bool = False


class BatchJob(BaseModel):
    job_id: str
    company: str
    title: str
    status: str
    fit: int | None = None
    score: float
    why: str
    rank: int
    stage: str
    stages: list[str]
    stop_at: str | None = None  # this job's stop point after the caps (absent in batches made before REQ-118)
    cap: str | None = None  # why the requested stop point was lowered
    auto_submit: bool
    submit_reason: str
    state: str | None = None
    reason: str | None = None
    result: str | None = None


class Excluded(BaseModel):
    job_id: str
    reason: str


class Batch(BaseModel):
    id: str | None = None
    name: str | None = None
    created_at: str | None = None
    status: str | None = None
    dry_run: bool
    stop_at: str
    stops: dict[str, str] | None = None
    kind: str
    selected: list[BatchJob]
    excluded: list[Excluded]
    reason: str | None = None
    updated_at: str | None = None
    requested: str | None = None
    retried: int | None = None  # POST retry only: jobs put back in the queue (0 = nothing to start)


class RetryBody(BaseModel):
    job_ids: list[str] | None = None


@router.post("/batches")
def create(body: CreateBody, c=Depends(ctx)) -> Batch:
    try:
        b = batches.create(c.settings, body.job_ids, body.stop_at, name=body.name, dry_run=body.dry_run,
                           now=c.now(), stops=body.stops)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    if not body.dry_run:
        after_write(c, jobs=[r["job_id"] for r in b["selected"]])  # create ticked them (REQ-104)
    return Batch.model_validate(b)


@router.get("/batches/{batch_id}")
def detail(batch_id: str, c=Depends(ctx)) -> Batch:
    b = batches.load(c.settings, batch_id)
    if b is None:
        raise HTTPException(404, f"batch {batch_id} not found")
    return Batch.model_validate(b)


def _do(fn, *a):
    try:
        return Batch.model_validate(fn(*a))
    except batches.BatchBusy as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e) else 422, str(e)) from None


@router.post("/batches/{batch_id}/start")
def start(batch_id: str, c=Depends(ctx), rc: RunControl = Depends(run_control)) -> Batch:
    """Start (or resume) the driver as a detached process; the batch file then shows its progress."""
    b = batches.load(c.settings, batch_id)
    if b is None:
        raise HTTPException(404, f"batch {batch_id} not found")
    if b["status"] in ("done", "cancelled"):
        raise HTTPException(422, f"batch {batch_id} is {b['status']}")
    if batches.running(c.settings, batch_id):
        raise HTTPException(409, f"batch {batch_id} is already running")
    rc.spawn(f"batch-{batch_id}", ["careeros.cli", "batch", "run", batch_id, "--json",
                                     "--since", c.now().isoformat()])
    return Batch.model_validate(b)


@router.post("/batches/{batch_id}/pause")
def pause(batch_id: str, c=Depends(ctx)) -> Batch:
    return _do(batches.control, c.settings, batch_id, "pause", c.now())


@router.post("/batches/{batch_id}/cancel")
def cancel(batch_id: str, c=Depends(ctx)) -> Batch:
    return _do(batches.control, c.settings, batch_id, "cancel", c.now())


@router.post("/batches/{batch_id}/retry")
def retry(batch_id: str, body: RetryBody | None = None, c=Depends(ctx)) -> Batch:
    return _do(batches.retry, c.settings, batch_id, (body or RetryBody()).job_ids, c.now())
