"""Atomic file writes for everything under the runs dir.

Readers (the UI, `careeros run status`, the scheduler) poll these files while a detached runner rewrites them,
so a write must never be observable half-done. Each write goes to a temp file in the same directory, unique per
process *and* call (the UI serves requests on a thread pool, so a pid alone is not unique), then `os.replace`
swaps it in. A reader sees the old file or the new one, never a mix.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


def write_text(path: Path, text: str, *, fsync: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            if fsync:
                fh.flush()
                os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_json(path: Path, data: Any, *, indent: int | None = 2, fsync: bool = False, **dumps: Any) -> None:
    write_text(path, json.dumps(data, indent=indent, **dumps), fsync=fsync)
