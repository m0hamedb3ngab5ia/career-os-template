from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from careeros.ui.routers import ctx
from careeros.ui.routers._errors import refusals
from careeros.ui.services import job_actions as acts
from careeros.ui.services import job_pipeline as pipe
from careeros.ui.services import jobs as svc
from careeros.ui.services.runs import RunControl
from careeros.ui.services.reindex import after_write

router = APIRouter(tags=["jobs"])

# Served inline with these types; anything else downloads. HTML and SVG never render (text/plain, sandboxed).
INLINE_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif", ".json": "application/json",
                ".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8",
                ".tex": "text/plain; charset=utf-8", ".html": "text/plain; charset=utf-8",
                ".yaml": "text/plain; charset=utf-8", ".yml": "text/plain; charset=utf-8"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _closed(c: Any) -> list[str]:
    from careeros.ui.config import load_ui_config

    return load_ui_config(c.settings).closed


@router.get("/jobs")
def list_jobs(status: list[str] = Query(default=[]), tier: list[str] = Query(default=[]),
              safety: list[str] = Query(default=[]), category: list[str] = Query(default=[]), q: str | None = None,
              location: str | None = None, sort: str = svc.DEFAULT_SORT, cursor: str | None = None,
              tab: str | None = None,
              limit: int | None = Query(default=None, ge=1, le=svc.MAX_LIMIT), c=Depends(ctx)) -> svc.JobsPage:
    from careeros.ui.config import load_ui_config

    return svc.list_jobs(c.index, status=status, tier=tier, safety=safety, category=category, q=q,
                         location=location, sort=sort, cursor=cursor, limit=limit or load_ui_config(c.settings).page_size, tab=tab,
                         closed=_closed(c))


@router.get("/jobs/tabs")
def job_tabs(q: str | None = None, location: str | None = None, c=Depends(ctx)) -> svc.JobsTabs:
    return {"tabs": svc.tabs(c.index, _closed(c), q=q, location=location)}


class Export(BaseModel):
    job_ids: list[str] | None = Field(default=None, max_length=svc.MAX_EXPORT)
    tab: str | None = None
    q: str | None = None
    location: str | None = None
    status: list[str] = []
    tier: list[str] = []
    sort: str = svc.DEFAULT_SORT
    columns: list[str] | None = None


@router.post("/jobs/export")
def export(body: Export, c=Depends(ctx)) -> Response:
    raw = svc.export_xlsx(c.index, job_ids=body.job_ids, columns=body.columns, sort=body.sort, closed=_closed(c),
                          **({} if body.job_ids is not None else
                             {"tab": body.tab, "q": body.q, "location": body.location, "status": body.status,
                              "tier": body.tier}))
    name = f"careeros-jobs-{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(raw, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, c=Depends(ctx)) -> svc.JobDetail:
    d = svc.job_detail(c.settings, c.index, job_id)
    if d is None:
        raise HTTPException(404, f"no job {job_id!r}")
    return d


@router.get("/jobs/{job_id}/files/{name:path}")
def job_file(job_id: str, name: str, c=Depends(ctx)) -> FileResponse:
    with refusals():
        f = acts.resolve_file(c.settings, job_id, name)
    kind = INLINE_TYPES.get(f.suffix.lower())
    headers = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'",
               "Cache-Control": "no-cache"}
    if kind:
        return FileResponse(f, media_type=kind, headers=headers, content_disposition_type="inline", filename=f.name)
    return FileResponse(f, media_type="application/octet-stream", headers=headers, filename=f.name)


class StatusBody(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=200)


class NoteBody(BaseModel):
    note: str | None = Field(default=None, max_length=200)


class OverrideBody(BaseModel):
    value: str


class VerifyBody(BaseModel):
    risk: Literal["low", "medium", "high"]
    signals: list[str] = []
    evidence: list[str] = []
    domain: str = ""


class FlagBody(BaseModel):
    reason: str = ""
    confidence: Literal["high", "medium"] = "high"
    evidence: list[str] = []
    notes: str = ""


class ClearBody(BaseModel):
    note: str = ""


@router.post("/jobs/{job_id}/status")
def set_status(job_id: str, body: StatusBody, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        out = acts.set_status(c.settings, job_id, body.status, body.note)
    after_write(c, jobs=[job_id], tracker=True)
    return out


@router.post("/jobs/{job_id}/withdraw")
def withdraw(job_id: str, body: NoteBody | None = None, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        out = acts.withdraw(c.settings, job_id, body.note if body else None)
    after_write(c, jobs=[job_id], tracker=True)
    return out


@router.post("/jobs/{job_id}/submitted")
def mark_submitted(job_id: str, body: NoteBody | None = None, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        out = acts.mark_submitted(c.settings, job_id, body.note if body else None)
    after_write(c, jobs=[job_id], tracker=True)
    return out


@router.post("/jobs/{job_id}/override")
def set_override(job_id: str, body: OverrideBody, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        out = acts.set_override(c.settings, job_id, body.value)
    after_write(c, jobs=[job_id], tracker=True)
    return out


class PipelineBody(BaseModel):
    action: Literal["start", "continue", "approve_continue"]
    force: bool = False


class PipelineStarted(BaseModel):
    run_id: str
    kind: str


def _rc(request: Request, c: Any) -> RunControl:
    factory = getattr(request.app.state, "run_control", None) or RunControl
    return factory(c.settings)


@router.get("/jobs/{job_id}/pipeline")
def job_pipeline(job_id: str, request: Request, c=Depends(ctx)) -> pipe.PipelineState:
    """The job's stage, the one next action (Start / Continue / Approve & continue), why it is blocked, what a
    needs_review job waits on, and the running run that names it."""
    with refusals():
        return pipe.pipeline_state(c.settings, job_id, _rc(request, c))


@router.post("/jobs/{job_id}/pipeline")
def start_job_pipeline(job_id: str, body: PipelineBody, request: Request, c=Depends(ctx)) -> PipelineStarted:
    """Run the job's next stage as a detached `careeros run <kind> --job <id>`; approve_continue first moves
    needs_review -> queued. 409 when a run is active or paused, or the job is not runnable (Tier A never applies)."""
    with refusals():
        out = pipe.start_pipeline(c.settings, job_id, body.action, _rc(request, c), force=body.force)
    if body.action == "approve_continue":
        after_write(c, jobs=[job_id], tracker=True)
    return PipelineStarted(**out)


@router.post("/jobs/{job_id}/qa")
def rerun_qa(job_id: str, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.rerun_qa(c.settings, job_id)


@router.post("/jobs/{job_id}/open-folder")
def open_folder(job_id: str, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.open_folder(c.settings, job_id)


@router.post("/jobs/{job_id}/safety/verify")
def safety_verify(job_id: str, body: VerifyBody, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.safety_verify(c.settings, job_id, risk=body.risk, signals=body.signals, evidence=body.evidence,
                                  domain=body.domain)


@router.post("/jobs/{job_id}/safety/flag")
def safety_flag(job_id: str, body: FlagBody, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.safety_flag(c.settings, job_id, reason=body.reason, confidence=body.confidence,
                                evidence=body.evidence, notes=body.notes)


@router.post("/jobs/{job_id}/safety/clear")
def safety_clear(job_id: str, body: ClearBody | None = None, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.safety_clear(c.settings, job_id, note=body.note if body else "")
