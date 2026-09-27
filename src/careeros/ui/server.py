"""`careeros ui`: index the data, start the file watcher, serve the app on loopback, open the browser."""
from __future__ import annotations

import sys
import threading
import webbrowser
from typing import Any

from careeros.ui.config import load_ui_config
from careeros.ui.security import is_loopback_host

LAN_REFUSED = ("careeros ui: only 127.0.0.1 / localhost for now. Reaching the app from another device "
               "(LAN mode with a token) comes in a later version; until then use an SSH tunnel or a private VPN "
               "to this Mac's loopback port.")


def serve(settings: Any, *, port: int | None = None, host: str | None = None, reindex: bool = False,
          open_browser: bool | None = None) -> int:
    import uvicorn

    from careeros.ui.app import create_app
    from careeros.ui.index import Index, default_path
    from careeros.ui.watch import Watcher

    cfg = load_ui_config(settings)
    host = host or cfg.host
    port = port or cfg.port
    if not is_loopback_host(host):
        print(LAN_REFUSED, file=sys.stderr)
        return 2
    if reindex:
        Index.remove_files(default_path(settings))
    ix = Index(settings)
    res = ix.sync()
    print(f"careeros ui: indexed {ix.query('SELECT COUNT(*) AS n FROM jobs')[0]['n']} jobs "
          f"({len(res['jobs_changed'])} updated) -> {ix.path}", flush=True)
    app = create_app(settings, index=ix)
    ctx = app.state.ctx
    watcher = Watcher(settings, ix, ctx.broker, debounce_ms=cfg.watch_debounce_ms, on_config=ctx.reload_settings)
    watcher.start()
    url = f"http://{'[::1]' if host == '::1' else host}:{port}"
    print(f"careeros ui: {url}  (Ctrl-C to stop)", flush=True)
    if cfg.open_browser if open_browser is None else open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        watcher.stop()
        ix.close()
    return 0
