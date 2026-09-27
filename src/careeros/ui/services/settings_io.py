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

import yaml

from careeros.config import ConfigError, Settings
from careeros.runs import locks, yamledit
from careeros.ui.settings_schema import Field, Section, get_section, reset_group, validate_value

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
    """The file as the CLI reads it (PyYAML, YAML 1.1): the UI shows what the pipeline actually applies."""
    return _plain(yaml.safe_load(path.read_text(encoding="utf-8"))) or {}


def _load_rt(path: Path) -> Any:
    """The file as written (ruamel, YAML 1.2): unquoted `off` stays the string the author meant."""
    return yamledit._yaml().load(path.read_text(encoding="utf-8")) or {}


def _lookup(data: Any, dotted: str) -> Any:
    cur = data
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return _MISSING
        cur = cur[k]
    return cur


def _as_applied(f: Field, v: Any) -> Any:
    """Display the value the way the pipeline applies it. A check level PyYAML read as a bool (`off` unquoted ->
    False) is ignored by safety.apply_levels, so the check keeps its built-in level: drop it from the map."""
    if f.control == "reason_levels" and isinstance(v, dict):
        return {k: lv for k, lv in v.items() if isinstance(lv, str)}
    return v


def effective_values(sec: Section, docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """{field id: value in the file as the CLI reads it, else the field's default}. An explicit null stays null."""
    out: dict[str, Any] = {}
    for f in sec.fields():
        v = _lookup(docs.get(f.file) or {}, f.key)
        out[f.id] = f.default if v is _MISSING else _as_applied(f, v)
    return out


def _ambiguous_strings(node: Any) -> list[str]:
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in _ambiguous_strings(k) + _ambiguous_strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _ambiguous_strings(v)]
    return [str(node)] if yamledit.has_ambiguous_plain(node) else []


def _rebuild(rt: Any, py: Any, pick: list[bool], at: list[int]) -> Any:
    """The CLI's reading `py` with each ambiguous plain leaf of the as-written `rt` (keys too) replaced by its
    string when pick[i] is true. Both trees come from the same text, so they walk in step."""
    if isinstance(rt, dict) and isinstance(py, dict):
        out = {}
        for (rk, rv), (pk, pv) in zip(rt.items(), py.items()):
            key = pk
            if yamledit.has_ambiguous_plain(rk):
                key = str(rk) if pick[at[0]] else pk
                at[0] += 1
            out[key] = _rebuild(rv, pv, pick, at)
        return out
    if isinstance(rt, list) and isinstance(py, list):
        return [_rebuild(a, b, pick, at) for a, b in zip(rt, py)]
    if yamledit.has_ambiguous_plain(rt):
        use = pick[at[0]]
        at[0] += 1
        return str(rt) if use else py
    return py


def _intended(f: Field, rt: Any, py: Any, n: int) -> Any:
    """Per leaf: the string the author wrote where that makes the field valid, else the CLI's reading. Tries the
    choices with the most strings first (up to 2^10 combinations; beyond that, the CLI's reading)."""
    from itertools import product

    if n <= 10:
        for pick in sorted(product((True, False), repeat=n), key=lambda p: -sum(p)):
            cand = _rebuild(rt, py, list(pick), [0])
            if validate_value(f, cand) is None:
                return cand
    return py


def unquoted_warnings(sec: Section, rt_docs: dict[str, Any],
                      py_docs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{field id: {message, intended}} for values written without quotes that PyYAML (the CLI) reads as something
    else: `off` -> false, 10:30 -> 630, yes -> true, a key ON -> true. `intended` picks, leaf by leaf, what the
    author wrote when it is valid there, else the CLI's reading; saving it rewrites the value quoted."""
    out: dict[str, dict[str, Any]] = {}
    for f in sec.fields():
        node = _lookup(rt_docs.get(f.file) or {}, f.key)
        if node is _MISSING:
            continue
        bad = _ambiguous_strings(node)
        if not bad:
            continue
        py = _lookup(py_docs.get(f.file) or {}, f.key)
        intended = _intended(f, node, py, len(bad))
        reads = ", ".join(f"{s} as {json.dumps(yaml.safe_load(s))}" for s in dict.fromkeys(bad))
        out[f.id] = {"message": f"Written without quotes, so the pipeline reads {reads}. Save this setting to "
                                f"fix it.", "intended": intended}
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
    """{section: schema, values: effective (as the CLI reads them), warnings: unquoted values the CLI misreads,
    defaults, files: {file: path}, version}."""
    sec = _section(section_id)
    paths = _paths(settings, sec)
    docs = {file: _load(p) for file, p in paths.items()}
    rt_docs = {file: _load_rt(p) for file, p in paths.items()}
    py_docs = {file: yaml.safe_load(p.read_text(encoding="utf-8")) or {} for file, p in paths.items()}
    return {"section": _section_dict(settings, sec), "values": effective_values(sec, docs),
            "warnings": unquoted_warnings(sec, rt_docs, py_docs),
            "defaults": {f.id: f.default for f in sec.fields()},
            "files": {file: str(p) for file, p in paths.items()}, "version": _version(list(paths.values()))}


def known_ids(settings: Settings, source: str) -> list[str]:
    """The top-level ids of config/<source>.yaml (e.g. the category ids), read fresh from disk; [] when absent."""
    data = _load(config_path(settings, source))
    return [str(k) for k, v in data.items() if isinstance(v, dict)] if isinstance(data, dict) else []


def _section_dict(settings: Settings, sec: Section) -> dict[str, Any]:
    """The schema with `options_from` fields filled with the ids on disk (as suggestions: strict_options False)."""
    out = sec.to_dict()
    sources = {f.id: f.options_from for f in sec.fields() if f.options_from}
    for g in out["groups"]:
        for item in g["items"]:
            if item.get("id") in sources:
                item["options"], item["strict_options"] = known_ids(settings, sources[item["id"]]), False
    return out


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
            if not err and f.options_from and isinstance(v, list):
                known = known_ids(settings, f.options_from)
                bad = [x for x in v if x not in known]
                if known and bad:
                    err = (f"Unknown {f.options_from} id: {', '.join(map(str, bad))}. "
                           f"Known in {f.options_from}.yaml: {', '.join(known)}.")
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
    try:
        with locks.config_lock(settings.root):  # version check + write as one step (other tabs, advise apply)
            return _save_locked(settings, sec, paths, changes, version)
    except locks.LockBusy:
        raise SettingsConflict("Another save is in progress; try again in a moment.") from None


def _save_locked(settings: Settings, sec: Section, paths: dict[str, Path], changes: dict[str, Any],
                 version: str | None) -> dict[str, Any]:
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
