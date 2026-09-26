"""The `careeros ui` web app: API routers under /api, the built frontend (src/careeros/ui/static/) for every
other path, and a request guard in front of both.

    app = create_app(settings)            # index + broker made here unless passed in (tests pass their own)

`app.state.ctx` holds what the routers share: the current Settings (reloaded when config/ changes; a broken
edit keeps the last good settings and shows the error on /api/health), the Index and the SSE Broker.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from careeros.config import ConfigError, Settings
from careeros.ui.events import Broker
from careeros.ui.index import Index
from careeros.ui.security import LOOPBACK, check_request

STATIC_DIR = Path(__file__).resolve().parent / "static"

PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>career-os</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;margin:48px;color:#1D1D1F">
<h1 style="font-size:22px">careeros ui is running</h1>
<p>The app's frontend is not built into this checkout yet. The API is up: <a href="/api/health">/api/health</a>,
<a href="/api/status">/api/status</a>, <a href="/api/jobs">/api/jobs</a>.</p>
</body></html>
"""


class Context:
    def __init__(self, settings: Settings, index: Index, broker: Broker, now: Callable[[], datetime]):
        self.settings, self.index, self.broker, self.now = settings, index, broker, now
        self.config_error: str | None = None

    def reload_settings(self) -> None:
        """Take the edited config when every block the app reads still validates; otherwise keep the last good
        settings and show why. The index and the watcher were built on the old paths, so a change to `paths` or
        `ui.index_path` also keeps the old settings until `careeros ui` is restarted."""
        from careeros.runs.advisor import load_advisor_config
        from careeros.runs.config import load_runs_config
        from careeros.runs.schedule import load_schedule
        from careeros.ui.config import load_ui_config
        from careeros.ui.index import default_path

        try:
            fresh = Settings.load(self.settings.root)
            load_ui_config(fresh)
            load_runs_config(fresh)
            load_schedule(fresh)
            load_advisor_config(fresh.pipeline)
        except ConfigError as e:
            self.config_error = str(e)
            return
        if fresh.paths != self.settings.paths or default_path(fresh) != default_path(self.settings):
            self.config_error = "paths changed in config/pipeline.yaml: restart careeros ui to use them"
            return
        self.settings, self.config_error = fresh, None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _static_response(static_dir: Path, path: str) -> Response:
    root = static_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        return HTMLResponse(PLACEHOLDER)
    if path:
        f = (root / path).resolve()
        if f.is_relative_to(root) and f.is_file():
            return FileResponse(f)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app(settings: Settings, *, index: Index | None = None, broker: Broker | None = None,
               allowed_hosts: frozenset[str] | set[str] = LOOPBACK, static_dir: Path = STATIC_DIR,
               now: Callable[[], datetime] = _utcnow) -> FastAPI:
    from careeros.ui.routers import events, health, jobs, meta, status

    app = FastAPI(title="career-os", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    app.state.ctx = Context(settings, index or Index(settings), broker or Broker(), now)
    hosts = frozenset(allowed_hosts)

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        refused = check_request(request.method, {k.lower(): v for k, v in request.headers.items()}, hosts)
        if refused:
            return JSONResponse({"detail": refused[1]}, status_code=refused[0])
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def bad_value(_: Request, e: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(ConfigError)
    async def bad_config(_: Request, e: ConfigError) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=503)

    for r in (health, meta, status, jobs, events):
        app.include_router(r.router, prefix="/api")

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def api_404(rest: str) -> JSONResponse:
        return JSONResponse({"detail": f"no such endpoint: /api/{rest}"}, status_code=404)

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> Response:
        return _static_response(static_dir, path)

    return app
