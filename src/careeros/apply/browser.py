"""The apply browser: a visible Chromium the app does NOT own, reached over CDP, so a staged form survives app
rebuilds and restarts. The filled tab is never closed by us; `application.json` in the job dir records it.

Liveness and focus use Chrome's DevTools HTTP endpoints (`/json/list`, `/json/activate/<id>`): stdlib only.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_CDP = "http://127.0.0.1:9223"   # dedicated port: not the 9222 a user's own debug Chrome may use
RECORD = "application.json"


def _get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=1.5) as r:  # noqa: S310 (local CDP endpoint only)
        return json.loads(r.read() or b"null")


def cdp_url(settings: Any) -> str:
    return str((getattr(settings, "paths", None) or {}).get("apply_cdp") or DEFAULT_CDP)


def tabs(cdp: str, get: Callable[[str], Any] | None = None) -> list[dict[str, Any]] | None:
    """Open page tabs, or None when no browser answers on `cdp`."""
    try:
        return [t for t in (get or _get)(f"{cdp}/json/list") or [] if t.get("type") == "page"]
    except (OSError, ValueError):
        return None


def record(job_dir: str | Path) -> dict[str, Any] | None:
    p = Path(job_dir) / RECORD
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_record(job_dir: str | Path, *, tab_id: str, url: str, cdp: str) -> None:
    rec = {"tab_id": tab_id, "url": url, "cdp": cdp, "filled_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (Path(job_dir) / RECORD).write_text(json.dumps(rec, indent=2), encoding="utf-8")


def is_confirmation(url: str) -> bool:
    """Greenhouse lands on .../confirmation after a real submit."""
    return "/confirmation" in url.split("?")[0]


def status(job_dir: str | Path, cdp: str, get: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """`tab`: open (the filled tab is alive) | needs_refill (it died: sleep, crash, reboot) | none (never filled).
    `submitted`: the live tab shows the Greenhouse confirmation page. `can_fill`: saved answers exist."""
    rec = record(job_dir)
    out = {"tab": "none", "submitted": False, "can_fill": (Path(job_dir) / "fill_plan.json").is_file()}
    if not rec:
        return out
    live = next((t for t in tabs(rec.get("cdp") or cdp, get) or [] if t.get("id") == rec.get("tab_id")), None)
    out["tab"] = "open" if live else "needs_refill"
    out["submitted"] = bool(live and is_confirmation(str(live.get("url", ""))))
    return out


def activate(job_dir: str | Path, cdp: str, get: Callable[[str], Any] | None = None) -> bool:
    """Focus the exact filled tab. False when it is gone."""
    rec = record(job_dir)
    if not rec or status(job_dir, cdp, get)["tab"] != "open":
        return False
    try:
        (get or _get)(f"{rec.get('cdp') or cdp}/json/activate/{rec['tab_id']}")
    except ValueError:  # activate answers plain text ("Target activated"), not JSON
        pass
    except OSError:
        return False
    return True


def ensure(cdp: str, profile_dir: str | Path, executable: str, get: Callable[[str], Any] | None = None,
           popen: Callable[..., Any] = subprocess.Popen, wait_s: float = 15.0) -> None:
    """Start the apply browser detached (own session: survives the app and its rebuilds) unless one answers."""
    if tabs(cdp, get) is not None:
        return
    port = cdp.rsplit(":", 1)[-1].strip("/")
    popen([executable, f"--remote-debugging-port={port}", f"--user-data-dir={profile_dir}", "--no-first-run",
           "--no-default-browser-check"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL, start_new_session=True)
    end = time.monotonic() + wait_s
    while time.monotonic() < end:
        if tabs(cdp, get) is not None:
            return
        time.sleep(0.25)
    raise RuntimeError(f"apply browser did not start on {cdp}")
