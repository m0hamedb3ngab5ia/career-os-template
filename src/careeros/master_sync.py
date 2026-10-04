"""master.yaml diff from the master résumé (REQ-099, UC-003; Q-012).

The extract-master skill writes a full proposed master.yaml via `careeros resume propose-master` ->
profile/master.proposed.yaml. Nothing touches profile/master.yaml until the candidate approves; approve writes the
proposal verbatim (re-validated), reject moves it to profile/master.rejected.yaml. Readiness `master_synced` is
open while either file exists, and `stale` when the master résumé (rid, latest version) is not the one the last
approve recorded in profile/master.synced.json (REQ-102). Validation: the master.yaml schema (doctor) plus a number
guard: every number token in bullet text, bullet variants and summary_variants must already be a number token of the
master résumé's latest text or the current master.yaml (exact token, not substring).
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from careeros.runs.atomic import write_text

MASTER, PROPOSED, REJECTED = "profile/master.yaml", "profile/master.proposed.yaml", "profile/master.rejected.yaml"
SYNCED = "profile/master.synced.json"
NUM = re.compile(r"\d(?:[\d,.]*\d)?%?")


class Invalid(ValueError):
    """The proposal breaks the master.yaml schema or carries a number not in the source -> 422."""


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _master(root: Path) -> dict[str, Any] | None:
    from careeros import resumes

    try:
        return next((r for r in resumes.list_resumes(root) if r["type"] == "master"), None)
    except (OSError, LookupError, ValueError):  # a malformed meta.json must not crash readiness
        return None


def _resume_text(root: Path) -> str:
    from careeros import resumes

    m = _master(root)
    if m is None:
        raise Invalid("no master résumé set: mark one master first")
    try:
        return resumes.version(root, m["rid"], m["latest"])["text"]
    except (OSError, LookupError, ValueError):
        return ""


def problems(root: Path, text: str) -> list[str]:
    from careeros.doctor import schema_problems

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [f"not valid YAML: {e}"]
    if not isinstance(data, dict):
        return ["a proposal must be a master.yaml mapping"]
    try:
        out = [p for p in schema_problems({}, {"master": data}) if p.startswith(MASTER)]
    except (AttributeError, TypeError) as e:  # a wrongly-typed section (e.g. `identity: x`) is a problem, not a crash
        return [f"{MASTER}: malformed ({e})"]
    source = set(NUM.findall(_resume_text(root) + "\n" + _read(root / MASTER)))
    texts = [("summary_variants", _strings(data.get("summary_variants")))]
    for sec in ("experience", "projects", "leadership"):
        for e in data.get(sec) or []:
            for b in (e.get("bullets") or []) if isinstance(e, dict) else []:
                if isinstance(b, dict):
                    texts.append((f"bullet {b.get('id')}", _strings([b.get("text"), b.get("variants")])))
    for where, strs in texts:
        for n in dict.fromkeys(n for t in strs for n in NUM.findall(t)):
            if n not in source:
                out.append(f"{where}: number {n!r} is not in the master résumé")
    return out


def _strings(x: Any) -> list[str]:
    if isinstance(x, str):
        return [x]
    vals = x.values() if isinstance(x, dict) else x if isinstance(x, list) else []
    return [s for v in vals for s in _strings(v)]


def _check(root: Path, text: str) -> None:
    if errs := problems(root, text):
        raise Invalid("; ".join(errs))


def _locked(root: Path):
    from careeros.resumes import _locked

    return _locked(root)


def propose(root: Path, text: str) -> dict[str, Any]:
    root = Path(root)
    with _locked(root):
        _check(root, text)
        write_text(root / PROPOSED, text)
        (root / REJECTED).unlink(missing_ok=True)
    return state(root)


def state(root: Path) -> dict[str, Any]:
    """{state: synced|pending|rejected|stale, diff: unified diff of master.yaml -> proposal ('' unless pending/rejected)}."""
    root = Path(root)
    for name, path in (("pending", PROPOSED), ("rejected", REJECTED)):
        if (root / path).exists():
            diff = difflib.unified_diff(_read(root / MASTER).splitlines(True), _read(root / path).splitlines(True),
                                        MASTER, path)
            return {"state": name, "diff": "".join(diff)}
    m = _master(root)
    if m and _source(m) != _synced_from(root):
        return {"state": "stale", "diff": ""}
    return {"state": "synced", "diff": ""}


def _source(m: dict[str, Any]) -> dict[str, Any]:
    return {"rid": m["rid"], "version": m["latest"]}


def _synced_from(root: Path) -> Any:
    try:
        return json.loads(_read(root / SYNCED) or "null")
    except ValueError:
        return None


def approve(root: Path) -> dict[str, Any]:
    root = Path(root)
    with _locked(root):
        if not (root / PROPOSED).exists():
            raise LookupError("no pending master.yaml proposal")
        text = _read(root / PROPOSED)
        _check(root, text)  # re-validate: the file may have been edited since propose
        write_text(root / MASTER, text)
        if m := _master(root):  # the résumé (rid, version) master.yaml is now synced from
            write_text(root / SYNCED, json.dumps(_source(m)))
        (root / PROPOSED).unlink()
        (root / REJECTED).unlink(missing_ok=True)
    return state(root)


def reject(root: Path) -> dict[str, Any]:
    root = Path(root)
    with _locked(root):
        if not (root / PROPOSED).exists():
            raise LookupError("no pending master.yaml proposal")
        (root / PROPOSED).replace(root / REJECTED)
    return state(root)
