"""master.yaml diff from the master résumé (REQ-099, UC-003; Q-012).

The extract-master skill writes a full proposed master.yaml via `careeros resume propose-master` ->
profile/master.proposed.yaml. Nothing touches profile/master.yaml until the candidate approves; approve writes the
proposal verbatim (re-validated), reject moves it to profile/master.rejected.yaml. Readiness `master_synced` is
open while either file exists (REQ-102). Validation: the master.yaml schema (doctor) plus a number guard: every
number in a bullet must already appear in the master résumé's latest text or the current master.yaml (verbatim).
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

import yaml

from careeros.runs.atomic import write_text

MASTER, PROPOSED, REJECTED = "profile/master.yaml", "profile/master.proposed.yaml", "profile/master.rejected.yaml"
NUM = re.compile(r"\d(?:[\d,.]*\d)?")


class Invalid(ValueError):
    """The proposal breaks the master.yaml schema or carries a number not in the source -> 422."""


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _resume_text(root: Path) -> str:
    from careeros import resumes

    m = next((r for r in resumes.list_resumes(root) if r["type"] == "master"), None)
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
    out = [p for p in schema_problems({}, {"master": data}) if p.startswith(MASTER)]
    source = _resume_text(root) + "\n" + _read(root / MASTER)
    for sec in ("experience", "projects", "leadership"):
        for e in data.get(sec) or []:
            for b in (e.get("bullets") or []) if isinstance(e, dict) else []:
                t = b.get("text") if isinstance(b, dict) else None
                for n in NUM.findall(t if isinstance(t, str) else ""):
                    if n not in source:
                        out.append(f"bullet {b.get('id')}: number {n!r} is not in the master résumé")
    return out


def _check(root: Path, text: str) -> None:
    if errs := problems(root, text):
        raise Invalid("; ".join(errs))


def propose(root: Path, text: str) -> dict[str, Any]:
    root = Path(root)
    _check(root, text)
    write_text(root / PROPOSED, text)
    (root / REJECTED).unlink(missing_ok=True)
    return state(root)


def state(root: Path) -> dict[str, Any]:
    """{state: synced|pending|rejected, diff: unified diff of master.yaml -> proposal ('' when synced)}."""
    root = Path(root)
    for name, path in (("pending", PROPOSED), ("rejected", REJECTED)):
        if (root / path).exists():
            diff = difflib.unified_diff(_read(root / MASTER).splitlines(True), _read(root / path).splitlines(True),
                                        MASTER, path)
            return {"state": name, "diff": "".join(diff)}
    return {"state": "synced", "diff": ""}


def approve(root: Path) -> dict[str, Any]:
    root = Path(root)
    if not (root / PROPOSED).exists():
        raise LookupError("no pending master.yaml proposal")
    text = _read(root / PROPOSED)
    _check(root, text)  # re-validate: the file may have been edited since propose
    write_text(root / MASTER, text)
    (root / PROPOSED).unlink()
    (root / REJECTED).unlink(missing_ok=True)
    return state(root)


def reject(root: Path) -> dict[str, Any]:
    root = Path(root)
    if not (root / PROPOSED).exists():
        raise LookupError("no pending master.yaml proposal")
    (root / PROPOSED).replace(root / REJECTED)
    return state(root)
