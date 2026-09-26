"""Settings forms <-> config YAML. Read a section's effective values, preview a change as a diff, save it.

A save checks every change against the schema (plain-language error per field), then the section's cross-field
checks, then writes all keys (across files) at once with runs/yamledit (comments, key order and layout kept;
writes go through symlinks to the real file), then re-loads the whole config with the same loaders the CLI uses.
Any loader error restores every file and is mapped to the field it names when it names one.

Pure Python (no FastAPI): the UI's settings routes call these; errors are exceptions the routes turn into 409/422.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from careeros.config import ConfigError, Settings
from careeros.runs import yamledit
from careeros.ui.settings_schema import Section, get_section, reset_group, validate_value

_MISSING = object()


class SettingsInvalid(ValueError):
    """`fields` = {field id: message}; `general` = messages that name no field."""

    def __init__(self, fields: dict[str, str], general: list[str] | None = None):
        self.fields, self.general = fields, general or []
        super().__init__("; ".join([*(f"{k}: {v}" for k, v in fields.items()), *self.general]))


class SettingsConflict(RuntimeError):
    """The files changed on disk since the form was opened (someone edited the YAML, or another tab saved)."""


def _section(section_id: str) -> Section:
    sec = get_section(section_id)
    if sec is None:
        raise KeyError(section_id)
    return sec


def config_path(settings: Settings, file: str) -> Path:
    return settings.root / "config" / f"{file}.yaml"


def _plain(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str)) if v is not None else None


def _load(path: Path) -> dict[str, Any]:
    data = yamledit._yaml().load(path.read_text(encoding="utf-8"))
    return _plain(data) or {}


def _lookup(data: Any, dotted: str) -> Any:
    cur = data
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return _MISSING
        cur = cur[k]
    return cur


def effective_values(sec: Section, docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """{field id: value in the file, else the field's default}. An explicit null stays null."""
    out: dict[str, Any] = {}
    for f in sec.fields():
        v = _lookup(docs.get(f.file) or {}, f.key)
        out[f.id] = f.default if v is _MISSING else v
    return out


def changes_by_file(sec: Section, changes: dict[str, Any]) -> dict[str, list[tuple[str, Any]]]:
    out: dict[str, list[tuple[str, Any]]] = {}
    for fid, v in changes.items():
        f = sec.field(fid)
        if f is not None:
            out.setdefault(f.file, []).append((f.key, v))
    return out


def _version(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(str(p).encode())
        h.update(Path(p).read_bytes() if Path(p).exists() else b"")
    return h.hexdigest()[:16]


def _paths(settings: Settings, sec: Section) -> dict[str, Path]:
    return {file: config_path(settings, file) for file in sec.files()}


def read_section(settings: Settings, section_id: str) -> dict[str, Any]:
    """{section: schema, values: effective, defaults, files: {file: path}, version}."""
    sec = _section(section_id)
    paths = _paths(settings, sec)
    docs = {file: _load(p) for file, p in paths.items()}
    return {"section": sec.to_dict(), "values": effective_values(sec, docs),
            "defaults": {f.id: f.default for f in sec.fields()},
            "files": {file: str(p) for file, p in paths.items()}, "version": _version(list(paths.values()))}


def _check_changes(settings: Settings, sec: Section, changes: dict[str, Any]) -> None:
    errors: dict[str, str] = {}
    for fid, v in changes.items():
        f = sec.field(fid)
        if f is None:
            errors[fid] = "Not a setting on this page."
        elif not f.editable:
            errors[fid] = f"This can't be changed here. {f.note}".strip()
        else:
            err = validate_value(f, v)
            if err:
                errors[fid] = err
    if not errors:
        docs = {file: _load(p) for file, p in _paths(settings, sec).items()}
        merged = {**effective_values(sec, docs), **changes}
        for fid, msg in sec.check(merged):
            errors.setdefault(fid, msg)
    if errors:
        raise SettingsInvalid(errors)


def diff_section(settings: Settings, section_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """{diffs: {file: unified diff}} for "Show diff". Raises SettingsInvalid like a save would; writes nothing."""
    sec = _section(section_id)
    _check_changes(settings, sec, changes)
    paths = _paths(settings, sec)
    return {"diffs": {file: yamledit.preview_changes(paths[file], ch)
                      for file, ch in changes_by_file(sec, changes).items()}}


def validate_root(root: Path) -> None:
    """Every config check the CLI runs (the same set `careeros advise apply` uses, plus the volume, ghost and
    outreach readers). Raises ConfigError."""
    from careeros import retention
    from careeros.outreach import OutreachPolicy
    from careeros.runs.advisor import load_advisor_config
    from careeros.runs.config import load_runs_config
    from careeros.runs.policy import daily_cap
    from careeros.runs.schedule import load_schedule
    from careeros.safety.ghost import ghost_settings

    s = Settings.load(root)
    load_runs_config(s)
    load_schedule(s)
    retention.retention_config(s)
    load_advisor_config(s.pipeline)
    daily_cap(s.targets, date.today())
    try:
        ghost_settings(s)
    except (TypeError, ValueError) as e:
        raise ConfigError(f"config/targets.yaml: safety.ghost: every value must be a whole number ({e})") from None
    OutreachPolicy.from_settings(s)


def field_for_error(sec: Section, message: str) -> str | None:
    """The field a loader error names: its key appears in the message and the message is about its file (or names
    no file). Longest key wins, so runs.job_timeout_minutes.score beats runs."""
    best = None
    for f in sec.fields():
        other_file = any(f"{o}.yaml" in message for o in ("targets", "companies", "qa", "pipeline", "categories")
                         if o != f.file)
        if other_file and f"{f.file}.yaml" not in message:
            continue
        if f.key in message and (best is None or len(f.key) > len(best.key)):
            best = f
    return best.id if best else None


def save_section(settings: Settings, section_id: str, changes: dict[str, Any],
                 version: str | None = None) -> dict[str, Any]:
    """Validate, write every change at once, re-validate the whole config; roll back on any error.
    Returns {old: {field id: previous value}, version}. Raises SettingsInvalid or SettingsConflict."""
    sec = _section(section_id)
    paths = _paths(settings, sec)
    if version is not None and version != _version(list(paths.values())):
        raise SettingsConflict("The settings files changed since this page was opened; reload to see them.")
    _check_changes(settings, sec, changes)
    grouped = changes_by_file(sec, changes)
    root = settings.root
    try:
        olds = yamledit.apply_changes_many({paths[file]: ch for file, ch in grouped.items()},
                                           validate=lambda reals: validate_root(root))
    except ConfigError as e:
        fid = field_for_error(sec, str(e))
        raise SettingsInvalid({fid: str(e)} if fid else {}, [] if fid else [str(e)]) from None
    old: dict[str, Any] = {}
    for file, ch in grouped.items():
        for key, _ in ch:
            old[f"{file}:{key}"] = olds[paths[file]][key]
    return {"old": old, "version": _version(list(paths.values()))}


def reset_changes(section_id: str, group_id: str) -> dict[str, Any]:
    """The changes "Reset to recommended" proposes for one group (the UI shows them as unsaved edits)."""
    return reset_group(section_id, group_id)
