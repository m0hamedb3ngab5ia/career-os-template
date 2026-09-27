"""`pipeline.yaml: ui` (`careeros ui`): server bind, look, list sizes and the Pipeline board's columns.

Every default here is the "(Recommended)" value documented in examples/config/pipeline.yaml; a test keeps the
two in step. Malformed values raise ConfigError, like the rest of the config.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from careeros.config import ConfigError
from careeros.models import STATUSES

UI_KEYS = ("port", "host", "open_browser", "theme", "undo_seconds", "page_size", "watch_debounce_ms", "index_path",
           "pipeline")
THEMES = ("system", "light", "dark")
# The mockup's board: one column per stage; statuses left out (skipped, rejected, withdrawn, ghosted) are
# counted in the "Closed" summary line under the board.
DEFAULT_COLUMNS: list[dict[str, Any]] = [
    {"name": "Found", "statuses": ["found", "scored"]},
    {"name": "Queued", "statuses": ["queued", "prepared"]},
    {"name": "Needs review", "statuses": ["needs_review"]},
    {"name": "Applied", "statuses": ["applied"]},
    {"name": "Screening · Interview", "statuses": ["screening", "interview"]},
    {"name": "Offer", "statuses": ["offer"]},
]


@dataclass
class UiConfig:
    port: int = 8765
    host: str = "127.0.0.1"
    open_browser: bool = True
    theme: str = "system"
    undo_seconds: int = 8
    page_size: int = 100
    watch_debounce_ms: int = 300
    index_path: str | None = None          # None: data/careeros.db next to data/jobs
    columns: list[dict[str, Any]] = field(default_factory=lambda: deepcopy(DEFAULT_COLUMNS))

    @property
    def closed(self) -> list[str]:
        used = {s for c in self.columns for s in c["statuses"]}
        return [s for s in STATUSES if s not in used]


def _err(msg: str) -> ConfigError:
    return ConfigError(f"config/pipeline.yaml: ui.{msg} (see examples/config/pipeline.yaml)")


def _int(v: Any, where: str, lo: int, hi: int) -> int:
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise _err(f"{where} must be a whole number from {lo} to {hi}, got {v!r}")
    return v


def _columns(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise _err("pipeline.columns must be a non-empty list of {name, statuses}")
    seen: set[str] = set()
    out = []
    for i, col in enumerate(raw):
        where = f"pipeline.columns[{i}]"
        if not isinstance(col, dict) or set(col) - {"name", "statuses"}:
            raise _err(f"{where} must be a mapping with only name and statuses")
        name, statuses = col.get("name"), col.get("statuses")
        if not isinstance(name, str) or not name.strip():
            raise _err(f"{where}.name must be a non-empty string")
        if not isinstance(statuses, list) or not statuses:
            raise _err(f"{where}.statuses must be a non-empty list")
        for st in statuses:
            if st not in STATUSES:
                raise _err(f"{where}.statuses: unknown status {st!r}; valid: {', '.join(STATUSES)}")
            if st in seen:
                raise _err(f"{where}.statuses: {st!r} is already in another column")
            seen.add(st)
        out.append({"name": name, "statuses": list(statuses)})
    return out


def load_ui_config(settings: Any) -> UiConfig:
    pipeline = getattr(settings, "pipeline", None) or {}
    raw = pipeline.get("ui")
    raw = {} if raw is None else raw
    if not isinstance(raw, dict):
        raise _err("ui must be a mapping")
    for k in raw:
        if k not in UI_KEYS:
            raise _err(f"unknown key {k!r}; valid: {', '.join(UI_KEYS)}")
    cfg = UiConfig()
    if "port" in raw:
        cfg.port = _int(raw["port"], "port", 1, 65535)
    if "host" in raw:
        if not isinstance(raw["host"], str) or not raw["host"].strip():
            raise _err(f"host must be a host name or address, got {raw['host']!r}")
        cfg.host = raw["host"].strip()
    if "open_browser" in raw:
        if not isinstance(raw["open_browser"], bool):
            raise _err(f"open_browser must be true or false, got {raw['open_browser']!r}")
        cfg.open_browser = raw["open_browser"]
    if "theme" in raw:
        if raw["theme"] not in THEMES:
            raise _err(f"theme must be one of {', '.join(THEMES)}, got {raw['theme']!r}")
        cfg.theme = raw["theme"]
    if "undo_seconds" in raw:
        cfg.undo_seconds = _int(raw["undo_seconds"], "undo_seconds", 1, 60)
    if "page_size" in raw:
        cfg.page_size = _int(raw["page_size"], "page_size", 20, 1000)
    if "watch_debounce_ms" in raw:
        cfg.watch_debounce_ms = _int(raw["watch_debounce_ms"], "watch_debounce_ms", 50, 10000)
    if raw.get("index_path") is not None:
        if not isinstance(raw["index_path"], str) or not raw["index_path"].strip():
            raise _err(f"index_path must be a file path or null, got {raw['index_path']!r}")
        cfg.index_path = raw["index_path"]
    pl = raw.get("pipeline")
    if pl is not None:
        if not isinstance(pl, dict) or set(pl) - {"columns"}:
            raise _err("pipeline must be a mapping with only columns")
        if "columns" in pl:
            cfg.columns = _columns(pl["columns"])
    return cfg
