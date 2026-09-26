"""The macOS LaunchAgent that calls `careeros tick` (a per-user agent in ~/Library/LaunchAgents, not a daemon:
it runs as the candidate, with their Claude Code login and keychain, only while they are logged in).

`launchctl` is injected (tests pass a fake; nothing here ever runs the real one in tests). Every path in the plist is
absolute: launchd starts the job with a bare environment, no shell profile and `/` as the working directory.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path
from typing import Any, Callable

Launchctl = Callable[[list[str]], tuple[int, str, str]]
SYSTEM_PATH = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]


def default_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def real_launchctl(args: list[str]) -> tuple[int, str, str]:
    try:
        p = subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return 127, "", "launchctl not found (the scheduler needs macOS)"
    return p.returncode, p.stdout, p.stderr


def build_plist(*, label: str, python: str, root: Path, runs_dir: Path, tick_minutes: float,
                path_dirs: list[str]) -> dict[str, Any]:
    dirs = list(dict.fromkeys([*path_dirs, *SYSTEM_PATH]))
    root, runs_dir = Path(root).absolute(), Path(runs_dir).absolute()
    return {
        "Label": label,
        "ProgramArguments": [str(python), "-m", "careeros.cli", "--root", str(root), "tick"],
        "WorkingDirectory": str(root),
        "StartInterval": int(round(tick_minutes * 60)),
        "RunAtLoad": True,
        "ProcessType": "Background",
        "StandardOutPath": str(runs_dir / "launchd.out.log"),
        "StandardErrorPath": str(runs_dir / "launchd.err.log"),
        "EnvironmentVariables": {"PATH": ":".join(dirs), "CAREEROS_ROOT": str(root)},
    }


def plist_path(label: str, agents_dir: Path | None = None) -> Path:
    return (agents_dir or default_agents_dir()) / f"{label}.plist"


def install(plist: dict[str, Any], *, agents_dir: Path | None = None, launchctl: Launchctl = real_launchctl,
            uid: int | None = None) -> dict[str, Any]:
    """Write the plist (replacing an older one) and (re)load it into the user's GUI domain."""
    uid = os.getuid() if uid is None else uid
    path = plist_path(plist["Label"], agents_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    Path(plist["StandardOutPath"]).parent.mkdir(parents=True, exist_ok=True)
    launchctl(["bootout", f"gui/{uid}/{plist['Label']}"])  # not loaded yet is fine
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(plistlib.dumps(plist))
    tmp.replace(path)
    rc, out, err = launchctl(["bootstrap", f"gui/{uid}", str(path)])
    if rc != 0:
        raise RuntimeError(f"launchctl bootstrap failed ({rc}): {(err or out).strip()}")
    return {"plist": str(path), "label": plist["Label"], "loaded": True}


def uninstall(label: str, *, agents_dir: Path | None = None, launchctl: Launchctl = real_launchctl,
              uid: int | None = None) -> dict[str, Any]:
    uid = os.getuid() if uid is None else uid
    path = plist_path(label, agents_dir)
    launchctl(["bootout", f"gui/{uid}/{label}"])
    existed = path.exists()
    if existed:
        path.unlink()
    return {"plist": str(path), "label": label, "removed": existed}


def status(label: str, *, agents_dir: Path | None = None, launchctl: Launchctl = real_launchctl,
           uid: int | None = None) -> dict[str, Any]:
    uid = os.getuid() if uid is None else uid
    path = plist_path(label, agents_dir)
    rc, _, _ = launchctl(["print", f"gui/{uid}/{label}"])
    return {"label": label, "installed": path.exists(), "loaded": rc == 0, "plist": str(path)}
