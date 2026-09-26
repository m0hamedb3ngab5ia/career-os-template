"""GET /api/events: Server-Sent Events. A `hello` frame on connect, then `changed` frames from the file watcher
({jobs, runs, actions, config, status}); a comment line every HEARTBEAT_S keeps proxies and the browser from
timing the stream out."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from careeros.ui.events import format_sse
from careeros.ui.routers import ctx

router = APIRouter(tags=["events"])
HEARTBEAT_S = 15.0


@router.get("/events")
async def events(request: Request, c=Depends(ctx)) -> StreamingResponse:
    q = c.broker.subscribe()

    async def stream() -> AsyncIterator[str]:
        try:
            yield "retry: 3000\n" + format_sse("hello", {"indexed_at": c.index.get_meta("indexed_at")})
            while not await request.is_disconnected():
                try:
                    event, data, eid = await asyncio.wait_for(q.get(), HEARTBEAT_S)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield format_sse(event, data, id=str(eid))
        finally:
            c.broker.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
