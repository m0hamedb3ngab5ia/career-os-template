"""The apply browser: a visible Chromium the app does NOT own, reached over CDP, so a staged form survives app
rebuilds and restarts. The filled tab is only closed by us on a refill; `application.json` in the job dir records it.

Liveness and focus use Chrome's DevTools HTTP endpoints (`/json/list`, `/json/activate/<id>`): stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_CDP = "http://127.0.0.1:9223"   # dedicated port: not the 9222 a user's own debug Chrome may use
RECORD = "application.json"
FILL_EXIT = "careeros-fill-exit: "  # the UI's detached fill appends this + its exit code to application.log
FILL_PID = "careeros-fill-pid: "  # ...and starts with this + its shell's pid
STAGED = "staged, not submitted"  # gh_fill's line once the form is filled and the tab kept open


def _get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=1.5) as r:  # noqa: S310 (local CDP endpoint only)
        return json.loads(r.read() or b"null")


def _put(url: str) -> Any:
    with urllib.request.urlopen(urllib.request.Request(url, method="PUT"), timeout=5) as r:  # noqa: S310 (local CDP)
        return json.loads(r.read() or b"null")


class NotConnected(RuntimeError):
    """Your own Chrome (paths.apply_cdp) doesn't answer: connect it, then retry. The recorded tab is kept."""


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


def fill_failure(job_dir: str | Path) -> dict[str, str] | None:
    """The last detached fill's error (its last output line) + log tail when it exited non-zero; None while it
    runs, after success, or when it never ran."""
    try:
        text = (Path(job_dir) / "application.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[-1].startswith(FILL_EXIT) or lines[-1][len(FILL_EXIT):].strip() == "0":
        return None
    run = lines[:-1]
    for i in range(len(run) - 1, -1, -1):  # this run only: output after the previous run's exit line
        if run[i].startswith(FILL_EXIT):
            run = run[i + 1:]
            break
    if any(ln.startswith(STAGED) for ln in run):
        return None  # form staged; exit 1 only means some fields were left for the user (fill_summary.json)
    return {"error": run[-1] if run else f"the fill exited with code {lines[-1][len(FILL_EXIT):]}",
            "log": "\n".join(run[-20:])}


def fill_running(job_dir: str | Path) -> bool:
    """A detached UI fill is still running: its log has no exit line after its pid line and that pid is alive."""
    try:
        lines = (Path(job_dir) / "application.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for ln in reversed(lines):
        if ln.startswith(FILL_EXIT):
            return False
        if ln.startswith(FILL_PID):
            try:
                os.kill(int(ln[len(FILL_PID):]), 0)
            except PermissionError:
                return True
            except (OSError, ValueError):
                return False
            return True
    return False


def status(job_dir: str | Path, cdp: str, get: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """`tab`: open (the filled tab is alive) | needs_refill (it died: sleep, crash, reboot) | none (never filled).
    `submitted`: the live tab shows the Greenhouse confirmation page. `can_fill`: saved answers exist.
    `fill_error`/`fill_log`: the last UI fill failed (see fill_failure). `fields_left`: labels the last fill
    left for the user (fill_summary.json failed + skipped)."""
    rec = record(job_dir)
    out: dict[str, Any] = {"tab": "none", "submitted": False, "can_fill": (Path(job_dir) / "fill_plan.json").is_file()}
    if fail := fill_failure(job_dir):
        out |= {"fill_error": fail["error"], "fill_log": fail["log"]}
    try:
        s = json.loads((Path(job_dir) / "fill_summary.json").read_text(encoding="utf-8"))
        out["fields_left"] = [f["label"] for f in s.get("failed", [])] + list(s.get("skipped", []))
    except (OSError, ValueError):
        pass
    if not rec:
        return out
    live = next((t for t in tabs(rec.get("cdp") or cdp, get) or [] if t.get("id") == rec.get("tab_id")), None)
    out["tab"] = "open" if live else "needs_refill"
    out["submitted"] = bool(live and is_confirmation(str(live.get("url", ""))))
    return out


def activate(job_dir: str | Path, cdp: str, get: Callable[[str], Any] | None = None) -> bool:
    """Focus the exact filled tab. False when it is gone."""
    return _tab_cmd("activate", job_dir, cdp, get)


def close(job_dir: str | Path, cdp: str, get: Callable[[str], Any] | None = None) -> bool:
    """Close the filled tab (before a refill opens a new one). False when it is gone."""
    return _tab_cmd("close", job_dir, cdp, get)


def _tab_cmd(verb: str, job_dir: str | Path, cdp: str, get: Callable[[str], Any] | None) -> bool:
    rec = record(job_dir)
    if not rec or status(job_dir, cdp, get)["tab"] != "open":
        return False
    try:
        (get or _get)(f"{rec.get('cdp') or cdp}/json/{verb}/{rec['tab_id']}")
    except ValueError:  # answers plain text ("Target activated"/"Target is closing"), not JSON
        pass
    except OSError:
        return False
    return True


def ensure(cdp: str, profile_dir: str | Path, executable: str, get: Callable[[str], Any] | None = None,
           popen: Callable[..., Any] = subprocess.Popen, wait_s: float = 15.0,
           put: Callable[[str], Any] | None = None) -> None:
    """Start the apply browser detached (own session: survives the app and its rebuilds) unless one answers."""
    open_tabs = tabs(cdp, get)
    if open_tabs == []:
        # macOS keeps Chromium alive after its last tab closes; CDP attach fails without a window, so open one.
        (put or _put)(f"{cdp}/json/new?about:blank")
    if open_tabs is not None:
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
