"""Server-Sent Events for the UI: one broker, one asyncio queue per open /api/events stream.

The file watcher publishes from its own thread; each subscriber's queue lives on the server's event loop, so
publish() hands the event over with call_soon_threadsafe. A client that falls behind loses its oldest events
(the frontend refetches on the next one anyway), never blocks the watcher.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import threading
from typing import Any

Event = tuple[str, Any, int]


def format_sse(event: str, data: Any, id: str | None = None) -> str:
    """One SSE frame. `data` is JSON-encoded on a single line (json.dumps escapes newlines)."""
    head = f"id: {id}\n" if id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class Broker:
    def __init__(self, maxsize: int = 100):
        self.maxsize = maxsize
        self._subs: dict[asyncio.Queue[Event], asyncio.AbstractEventLoop] = {}
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    def subscribe(self) -> asyncio.Queue[Event]:
        """Call from the event loop that will read the queue."""
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=self.maxsize)
        with self._lock:
            self._subs[q] = asyncio.get_running_loop()
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        with self._lock:
            self._subs.pop(q, None)

    @property
    def subscribers(self) -> int:
        with self._lock:
            return len(self._subs)

    def publish(self, event: str, data: Any) -> int:
        """Send to every subscriber; safe from any thread. Returns the event id."""
        eid = next(self._ids)
        with self._lock:
            subs = list(self._subs.items())
        for q, loop in subs:
            try:
                loop.call_soon_threadsafe(_put, q, (event, data, eid))
            except RuntimeError:  # loop closed: the stream went away
                self.unsubscribe(q)
        return eid


def _put(q: asyncio.Queue[Event], item: Event) -> None:
    if q.full():
        q.get_nowait()
    q.put_nowait(item)
