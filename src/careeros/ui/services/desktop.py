"""Open a file or folder in the Mac's own app (Finder, Excel) with `open`. The caller decides which paths are
allowed (a job's own folder, the configured tracker); this module only runs the command."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class Unsupported(RuntimeError):
    """The action can't run here (not macOS, or the file doesn't exist yet): shown as a plain-language 409."""


def _platform() -> str:
    return sys.platform


def _run(argv: list[str]) -> None:
    subprocess.run(argv, check=True, timeout=15, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def open_path(path: Path) -> None:
    if _platform() != "darwin":
        raise Unsupported("Opening files from the app works on macOS only; open the path yourself: " + str(path))
    if not path.exists():
        raise Unsupported(f"{path.name} doesn't exist yet")
    _run(["open", str(path)])
