"""Runs: history, the running batch, the queue, starting / cancelling / pausing runs, catch-up, the live stream
and the scheduler. Thin: RunControl (services/runs.py) does the work, services/runs_view.py shapes it.

Refusals become plain-language HTTP errors: Busy, Paused and NotSetUp -> 409, bad input (ValueError) -> 422.
Tests (and nothing else) swap the process edges by setting `app.state.run_control` to a factory
`(settings, **overrides) -> RunControl`.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, AsyncIterator, Iterator, Literal

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from careeros.ui.events import format_sse
from careeros.ui.routers import ctx
from careeros.ui.services import runs_view as view
from careeros.ui.services.runs import Busy, NotSetUp, Paused, RunControl

router = APIRouter(tags=["runs"])
MAX_LIMIT = 1000
QUEUE_LIMIT = 25


def run_control(request: Request, c=Depends(ctx)) -> RunControl:
    factory = getattr(request.app.state, "run_control", None) or RunControl
    return factory(c.settings)


@contextmanager
def refusals() -> Iterator[None]:
    from careeros.readiness import NotReady

    try:
        yield
    except NotReady as e:  # REQ-103
        raise HTTPException(409, {"code": "not_ready", "message": str(e), "items": e.items}) from None
    except Busy as e:
        raise HTTPException(409, f"{str(e)[:1].upper()}{str(e)[1:]}. Wait for it to finish, or cancel it.") from None
    except Paused:
        raise HTTPException(409, "Runs are paused. Resume them first.") from None
    except NotSetUp as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


class StartBody(BaseModel):
    kind: str
    preset: str | None = None
    max_jobs: int | None = None
    max_minutes: float | None = None
    dry_run: bool = False


class CancelBody(BaseModel):
    run_id: str | None = None


class PauseBody(BaseModel):
    until: str | None = None
    reason: str = Field(default="", max_length=200)


class CatchUpBody(BaseModel):
    dismiss: bool = False


# --- reading ---------------------------------------------------------------------------------------------------

@router.get("/runs")
def history(kind: str | None = None, cursor: str | None = None,
            limit: int | None = Query(default=None, ge=1, le=MAX_LIMIT), c=Depends(ctx),
            rc: RunControl = Depends(run_control)) -> view.HistoryPage:
    from careeros.ui.config import load_ui_config

    with refusals():
        return view.history_view(rc, kind, limit or load_ui_config(c.settings).page_size, cursor)


@router.get("/runs/current")
def current(c=Depends(ctx), rc: RunControl = Depends(run_control)) -> view.CurrentRun | None:
    return view.current_view(rc, c.now().astimezone().date())


@router.get("/runs/queue/{kind}")
def queue(kind: str, limit: int = Query(default=QUEUE_LIMIT, ge=1, le=MAX_LIMIT),
          rc: RunControl = Depends(run_control)) -> dict[str, Any]:
    with refusals():
        return view.queue_view(rc, kind, limit)


@router.get("/runs/{run_id}")
def detail(run_id: str, rc: RunControl = Depends(run_control)) -> view.RunDetail:
    with refusals():
        d = view.detail_view(rc, run_id)
    if d is None:
        err = rc.start_error(run_id)  # a job run started here that refused before writing run.json
        raise HTTPException(404, f"Run {run_id} did not start: {err}" if err else f"no run {run_id!r}")
    return d


@router.get("/runs/{run_id}/stream")
async def stream(run_id: str, request: Request, c=Depends(ctx)) -> StreamingResponse:
    """SSE: `event` frames ({type, text, attempt?}) from the attempt streams and run.log, then one `end` frame
    ({state, stop_reason}) when the run is no longer running. A reconnect replays from the start."""
    with refusals():
        view.check_run_id(run_id)
    stop = threading.Event()

    class Stopped(Exception):
        pass

    def sleep(s: float) -> None:
        if stop.wait(s):
            raise Stopped

    factory = getattr(request.app.state, "run_control", None) or RunControl
    rc = factory(c.settings, sleep=sleep)
    if rc.detail(run_id) is None:
        raise HTTPException(404, f"no run {run_id!r}")
    it = rc.tail(run_id)
    done = object()

    def step() -> Any:
        try:
            return next(it, done)
        except Stopped:
            return done

    async def frames() -> AsyncIterator[str]:
        try:
            yield "retry: 3000\n\n"
            while True:
                # abandon_on_cancel: a client that goes away cancels this await at once, so `finally` sets
                # `stop` and the worker, asleep between polls, wakes and returns instead of polling on.
                item = await anyio.to_thread.run_sync(step, abandon_on_cancel=True)
                if item is done:
                    return
                yield format_sse("end" if item.get("type") == "end" else "event", item)
                if await request.is_disconnected():
                    return
        finally:
            stop.set()

    return StreamingResponse(frames(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- starting and stopping -------------------------------------------------------------------------------------

@router.post("/runs")
def start(body: StartBody, rc: RunControl = Depends(run_control)) -> dict[str, Any]:
    """A score or prepare batch; `dry_run` returns the selection and starts nothing."""
    with refusals():
        out = rc.start(body.kind, preset=body.preset, max_jobs=body.max_jobs, max_minutes=body.max_minutes,
                       dry_run=body.dry_run)
    return view.selection_view(out) if body.dry_run else out


@router.post("/runs/steps/{kind}")
def start_step(kind: str, job_id: str | None = None,
               rc: RunControl = Depends(run_control)) -> dict[str, Any]:
    with refusals():
        return rc.start_step(kind, job_id)


@router.post("/runs/cancel")
def cancel(body: CancelBody | None = None, rc: RunControl = Depends(run_control)) -> dict[str, Any]:
    with refusals():
        rid = view.check_run_id(body.run_id) if body and body.run_id else None
        return rc.cancel(rid)


@router.post("/runs/pause")
def pause(body: PauseBody | None = None, c=Depends(ctx), rc: RunControl = Depends(run_control)) -> dict[str, Any]:
    body = body or PauseBody()
    with refusals():
        until = view.parse_until(body.until, c.now())
    return rc.pause(until, body.reason)


@router.post("/runs/resume")
def resume(rc: RunControl = Depends(run_control)) -> dict[str, Any]:
    return {"resumed": rc.resume()}


@router.post("/runs/catch-up")
def catch_up(body: CatchUpBody | None = None, rc: RunControl = Depends(run_control)) -> dict[str, Any]:
    body = body or CatchUpBody()
    with refusals():
        try:
            out = rc.catch_up(dismiss=body.dismiss)
        except RuntimeError as e:
            if isinstance(e, (Busy, Paused, NotSetUp)):
                raise
            raise HTTPException(409, str(e)) from None
    if out.get("status") == "busy":
        raise HTTPException(409, "The scheduler is ticking right now. Try again in a moment.")
    return out


# --- scheduler -------------------------------------------------------------------------------------------------

@router.get("/schedule")
def schedule(rc: RunControl = Depends(run_control)) -> view.Schedule:
    return view.schedule_view(rc)


@router.post("/schedule/{action}")
def schedule_action(action: Literal["install", "uninstall"], rc: RunControl = Depends(run_control)) -> dict[str, Any]:
    try:
        return rc.schedule_install() if action == "install" else rc.schedule_uninstall()
    except (RuntimeError, OSError) as e:
        raise HTTPException(409, f"The scheduler could not be {action}ed: {e}") from None
