from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
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


def _column_filters(*, company: list[str], location_in: list[str], ats: list[str], qa_passed: list[str],
                    fit_min: float | None, fit_max: float | None, qa_score_min: float | None,
                    qa_score_max: float | None, found_from: str | None, found_to: str | None,
                    applied_from: str | None, applied_to: str | None, closes_from: str | None,
                    closes_to: str | None) -> dict[str, Any]:
    """The Excel-style column filters as the service's `values` / `ranges` (status, tier, safety, category keep
    their own params). `location_in` is exact values; `location` stays the substring search."""
    return {"values": {"company": company, "location": location_in, "ats": ats, "qa_passed": qa_passed},
            "ranges": {"fit": (fit_min, fit_max), "qa_score": (qa_score_min, qa_score_max),
                       "found_at": (found_from, found_to), "applied_at": (applied_from, applied_to),
                       "closes_at": (closes_from, closes_to)}}


_ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


def column_filters(company: list[str] = Query(default=[]), location_in: list[str] = Query(default=[]),
                   ats: list[str] = Query(default=[]), qa_passed: list[str] = Query(default=[]),
                   fit_min: float | None = None, fit_max: float | None = None, qa_score_min: float | None = None,
                   qa_score_max: float | None = None,
                   found_from: str | None = Query(default=None, pattern=_ISO_DATE_PATTERN),
                   found_to: str | None = Query(default=None, pattern=_ISO_DATE_PATTERN),
                   applied_from: str | None = Query(default=None, pattern=_ISO_DATE_PATTERN),
                   applied_to: str | None = Query(default=None, pattern=_ISO_DATE_PATTERN),
                   closes_from: str | None = Query(default=None, pattern=_ISO_DATE_PATTERN),
                   closes_to: str | None = Query(default=None, pattern=_ISO_DATE_PATTERN)) -> dict[str, Any]:
    return _column_filters(company=company, location_in=location_in, ats=ats, qa_passed=qa_passed, fit_min=fit_min,
                           fit_max=fit_max, qa_score_min=qa_score_min, qa_score_max=qa_score_max,
                           found_from=found_from, found_to=found_to, applied_from=applied_from,
                           applied_to=applied_to, closes_from=closes_from, closes_to=closes_to)


@router.get("/jobs")
def list_jobs(status: list[str] = Query(default=[]), tier: list[str] = Query(default=[]),
              safety: list[str] = Query(default=[]), category: list[str] = Query(default=[]), q: str | None = None,
              location: str | None = None, sort: str = svc.DEFAULT_SORT, cursor: str | None = None,
              tab: str | None = None,
              limit: int | None = Query(default=None, ge=1, le=svc.MAX_LIMIT), c=Depends(ctx),
              cols: dict[str, Any] = Depends(column_filters)) -> svc.JobsPage:
    from careeros.ui.config import load_ui_config

    return svc.list_jobs(c.index, status=status, tier=tier, safety=safety, category=category, q=q,
                         location=location, sort=sort, cursor=cursor, limit=limit or load_ui_config(c.settings).page_size, tab=tab,
                         closed=_closed(c), **cols)


@router.get("/jobs/tabs")
def job_tabs(status: list[str] = Query(default=[]), tier: list[str] = Query(default=[]),
             safety: list[str] = Query(default=[]), category: list[str] = Query(default=[]), q: str | None = None,
             location: str | None = None, c=Depends(ctx), cols: dict[str, Any] = Depends(column_filters)) -> svc.JobsTabs:
    return {"tabs": svc.tabs(c.index, _closed(c), q=q, location=location, status=status, tier=tier, safety=safety,
                             category=category, **cols)}


@router.get("/jobs/facets")
def job_facets(field: str, status: list[str] = Query(default=[]), tier: list[str] = Query(default=[]),
               safety: list[str] = Query(default=[]), category: list[str] = Query(default=[]), q: str | None = None,
               location: str | None = None, tab: str | None = None, c=Depends(ctx),
               cols: dict[str, Any] = Depends(column_filters)) -> svc.JobFacets:
    """Distinct values of one column with counts under every other active filter (the header filter menu)."""
    return svc.facets(c.index, field, closed=_closed(c), q=q, location=location, tab=tab, status=status, tier=tier,
                      safety=safety, category=category, **cols)


class Export(BaseModel):
    job_ids: list[str] | None = Field(default=None, max_length=svc.MAX_EXPORT)
    tab: str | None = None
    q: str | None = None
    location: str | None = None
    status: list[str] = []
    tier: list[str] = []
    safety: list[str] = []
    category: list[str] = []
    company: list[str] = []
    location_in: list[str] = []
    ats: list[str] = []
    qa_passed: list[str] = []
    fit_min: float | None = None
    fit_max: float | None = None
    qa_score_min: float | None = None
    qa_score_max: float | None = None
    found_from: str | None = None
    found_to: str | None = None
    applied_from: str | None = None
    applied_to: str | None = None
    closes_from: str | None = None
    closes_to: str | None = None
    sort: str = svc.DEFAULT_SORT
    columns: list[str] | None = None


@router.post("/jobs/export")
def export(body: Export, c=Depends(ctx)) -> Response:
    b = body.model_dump()
    cols = _column_filters(**{k: b[k] for k in ("company", "location_in", "ats", "qa_passed", "fit_min", "fit_max",
                                                "qa_score_min", "qa_score_max", "found_from", "found_to",
                                                "applied_from", "applied_to", "closes_from", "closes_to")})
    raw = svc.export_xlsx(c.index, job_ids=body.job_ids, columns=body.columns, sort=body.sort, closed=_closed(c),
                          **({} if body.job_ids is not None else
                             {"tab": body.tab, "q": body.q, "location": body.location, "status": body.status,
                              "tier": body.tier, "safety": body.safety, "category": body.category, **cols}))
    name = f"careeros-jobs-{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(raw, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, c=Depends(ctx)) -> svc.JobDetail:
    d = svc.job_detail(c.settings, c.index, job_id)
    if d is None:
        raise HTTPException(404, f"no job {job_id!r}")
    return d


class MatchRow(BaseModel):
    rid: str
    name: str
    type: str
    version: int
    score: int
    missing: list[str]
    groups: dict[str, dict[str, list[str]]]


class Matches(BaseModel):
    job_id: str
    threshold: int
    scored: bool  # False: score.json has no skills yet -> no rows, `hint` says to run score
    best: str | None
    resumes: list[MatchRow]
    hint: str | None = None


@router.get("/jobs/{job_id}/matches")
def job_matches(job_id: str, threshold: int | None = Query(default=None, ge=0, le=100), c=Depends(ctx)) -> Matches:
    """Every résumé's match score for this job, best first, with missing skills (REQ-111/115, DEC-003)."""
    from careeros.match import matches

    d = svc.job_dir_for(c.settings, job_id)
    if d is None:
        raise HTTPException(404, f"no job {job_id!r}")
    return Matches(**matches(c.settings, d, threshold))


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


class SelectBody(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=svc.MAX_EXPORT)
    selected: bool


@router.post("/jobs/select")
def select_jobs(body: SelectBody, c=Depends(ctx)) -> dict[str, Any]:
    """REQ-104: tick/untick jobs for prepare/apply runs (flags.json `selected`). Any unknown id -> 404, none set."""
    from careeros.store import Store

    store = Store(c.settings)
    missing = [j for j in body.ids if not store.exists(j)]
    if missing:
        raise HTTPException(404, f"job(s) not found: {', '.join(missing[:20])}")
    store.set_selected(body.ids, body.selected)
    after_write(c, jobs=body.ids)
    return {"ids": body.ids, "selected": body.selected}


class PipelineStarted(BaseModel):
    run_id: str
    kind: str


class CheckCreated(BaseModel):
    job_id: str
    flagged: bool  # REQ-109 scan hit: badge + Action Item; scoring continues, prepare waits for a clear
    reasons: list[str]
    score_run: str | None  # the `run score --job` started for it
    score_error: str | None = None  # why scoring could not start now (busy, paused, not set up)


class CheckState(Matches):
    stage: Literal["scoring", "ready", "not_tailorable", "offer_tailor", "tailoring", "tailor_failed",
                   "ready_tailored", "confirm", "below_threshold", "discarded"]
    tailor_run: str | None
    decision: Literal["keep", "discard"] | None
    attempt: dict[str, Any] | None  # {score, missing} of the tailored résumé
    notice: str | None  # "threshold not met: best X, needed Y (X/Y); missing: ..." (REQ-116)


class CheckDecision(BaseModel):
    keep: bool


@contextmanager
def _check_refusals() -> Iterator[None]:
    from careeros import check, resumes

    with refusals():
        try:
            yield
        except resumes.TooLarge as e:
            raise HTTPException(413, str(e)) from None
        except resumes.BadType as e:
            raise HTTPException(415, str(e)) from None
        except check.BadInput as e:
            raise HTTPException(422, str(e)) from None
        except check.Refused as e:
            raise HTTPException(409, str(e)) from None


_RAW = {"requestBody": {"required": True, "content": {
    "text/plain": {"schema": {"type": "string"}},
    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}}


@router.post("/jobs/check", status_code=201, openapi_extra=_RAW)
async def check_job(request: Request, filename: str | None = None, title: str = "", company: str = "",
                    url: str = "", c=Depends(ctx)) -> CheckCreated:
    """REQ-114 Check a job: raw body (DEC-006) = pasted JD text, or a pdf/docx/txt/md file when `filename` is
    given (<= 5 MB). Stores a `source: manual` job, scans it, starts its score run; poll GET .../check."""
    import anyio

    from careeros import check

    cap = f"{filename or 'pasted text'}: larger than {check.MAX_BYTES // (1024 * 1024)} MB"
    if int(request.headers.get("content-length") or 0) > check.MAX_BYTES:
        raise HTTPException(413, cap)
    data = bytearray()
    async for chunk in request.stream():  # streamed cap: never buffer more than MAX_BYTES + one chunk
        data += chunk
        if len(data) > check.MAX_BYTES:
            raise HTTPException(413, cap)
    with _check_refusals():
        out = await anyio.to_thread.run_sync(lambda: check.create(
            c.settings, check.text_from(filename, bytes(data)), title=title, company=company, url=url))
    after_write(c, jobs=[out["job_id"]])
    run, err = None, None
    try:
        with _check_refusals():
            run = _rc(request, c).start("score", job_id=out["job_id"])["run_id"]
    except HTTPException as e:  # stored either way; the check page offers scoring again
        err = str(e.detail)
    return CheckCreated(**out, score_run=run, score_error=err)


@router.get("/jobs/{job_id}/check")
def check_state(job_id: str, c=Depends(ctx)) -> CheckState:
    """Where the check stands: match table (REQ-115), tailor offer, below-threshold notice (REQ-116)."""
    from careeros import check

    with _check_refusals():
        return CheckState(**check.state(c.settings, job_id))


@router.post("/jobs/{job_id}/check/tailor")
def check_tailor(job_id: str, request: Request, c=Depends(ctx)) -> PipelineStarted:
    """The one "Tailor from master" run per check (`run prepare --job`: résumé pick tweak/tailor). 409 otherwise."""
    from careeros import check

    with _check_refusals():
        run = check.tailor(c.settings, job_id,
                           lambda: _rc(request, c).start("prepare", job_id=job_id, force=True)["run_id"])
    return PipelineStarted(run_id=run, kind="prepare")


@router.post("/jobs/{job_id}/check/decision")
def check_decision(job_id: str, body: CheckDecision, c=Depends(ctx)) -> CheckState:
    """"Create closest match anyway?": keep = attempt kept, flagged below_threshold; no = attempt discarded."""
    from careeros import check

    with _check_refusals():
        out = check.decide(c.settings, job_id, body.keep)
    after_write(c, jobs=[job_id])
    return CheckState(**out)

@router.post("/jobs/{job_id}/injection/clear")
def clear_injection(job_id: str, c=Depends(ctx)) -> dict[str, Any]:
    """REQ-109 "I checked it": the user read a flagged posting; prepare/apply are allowed again."""
    from careeros import untrusted
    from careeros.store import Store

    store = Store(c.settings)
    if not store.exists(job_id):
        raise HTTPException(404, f"no job {job_id!r}")
    if not untrusted.blocked(store.load_flags(job_id)):
        raise HTTPException(409, "job is not flagged as a possible injection")
    store.clear_injection(job_id)
    after_write(c, jobs=[job_id])
    return {"job_id": job_id, "cleared": True}


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


class ResetFailuresBody(BaseModel):
    kind: Literal["score", "prepare", "apply"] | None = None


@router.post("/jobs/{job_id}/failures/reset")
def reset_job_failures(job_id: str, body: ResetFailuresBody | None = None, c=Depends(ctx)) -> dict[str, Any]:
    """Clear the job's run failure count (`careeros run reset-failures`): a job out of retries runs again. Its
    out-of-retries Action Items are marked done."""
    with refusals():
        out = pipe.reset_failures(c.settings, job_id, body.kind if body else None)
    after_write(c, jobs=[job_id], tracker=True)
    return out


@router.post("/jobs/{job_id}/qa")
def rerun_qa(job_id: str, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.rerun_qa(c.settings, job_id)


@router.post("/jobs/{job_id}/open-folder")
def open_folder(job_id: str, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.open_folder(c.settings, job_id)


@router.get("/jobs/{job_id}/application")
def application_status(job_id: str, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        out = acts.application_status(c.settings, job_id)
    if out.get("marked_applied"):
        after_write(c, jobs=[job_id], tracker=True)
    return out


@router.post("/jobs/{job_id}/application/open")
def open_application(job_id: str, refill: bool = Body(False, embed=True), c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.open_application(c.settings, job_id, refill=refill)


class FillFieldBody(BaseModel):
    value: str | None = None
    skip: bool = False
    save: bool = True


@router.get("/jobs/{job_id}/fill-plan")
def fill_plan(job_id: str, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.fill_plan(c.settings, job_id)


@router.post("/jobs/{job_id}/fill-plan")
def make_fill_plan(job_id: str, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        out = acts.make_fill_plan(c.settings, job_id)
    after_write(c, jobs=[job_id])
    return out


@router.post("/jobs/{job_id}/fill-plan/fields/{field_id}")
def edit_fill_field(job_id: str, field_id: str, body: FillFieldBody, c=Depends(ctx)) -> dict[str, Any]:
    with refusals():
        return acts.edit_fill_field(c.settings, job_id, field_id, value=body.value, skip=body.skip, save=body.save)


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
