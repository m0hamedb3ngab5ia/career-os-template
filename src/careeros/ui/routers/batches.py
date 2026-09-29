"""Batches: preview (dry run), create and read a batch (runs/batches.py). Nothing runs from here yet: the driver
that works a batch's queue is the next slice. Bad input (unknown stop point, no runnable job) -> 422."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from careeros.runs import batches
from careeros.ui.routers import ctx

router = APIRouter(tags=["batches"])


class CreateBody(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=batches.MAX_JOBS)
    stop_at: Literal["score", "prepare", "fill", "submit"]
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
    auto_submit: bool
    submit_reason: str
    state: str | None = None


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
    kind: str
    selected: list[BatchJob]
    excluded: list[Excluded]


@router.post("/batches")
def create(body: CreateBody, c=Depends(ctx)) -> Batch:
    try:
        return Batch.model_validate(batches.create(c.settings, body.job_ids, body.stop_at, name=body.name,
                                                   dry_run=body.dry_run, now=c.now()))
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/batches/{batch_id}")
def detail(batch_id: str, c=Depends(ctx)) -> Batch:
    b = batches.load(c.settings, batch_id)
    if b is None:
        raise HTTPException(404, f"batch {batch_id} not found")
    return Batch.model_validate(b)
