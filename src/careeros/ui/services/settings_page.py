"""Helpers behind the Settings routes: the section list, the 422 body, file paths shown relative to the repo, and
the Runs page's ranking preview (the next jobs with the draft weights, before they are saved).

The preview ranks with the same code as `careeros run status` (runner.select_candidates); only the ranking
weights are swapped for the draft ones, in memory. Nothing is written.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Union

from typing_extensions import TypedDict

from careeros.ui.services.settings_io import SettingsInvalid
from careeros.ui.settings_schema import SECTIONS

PREVIEW_KINDS = ("score", "prepare")



# Response shapes of GET /api/settings and GET /api/settings/{section} (settings_schema/model.py to_dict and
# settings_io.read_section), typed for ui/openapi.json -> ui/src/api/schema.gen.ts. Numbers that can be int or
# float are `int | float` so ints stay ints on the wire.
class SectionSummary(TypedDict):
    id: str
    title: str
    help: str
    files: list[str]


class SectionList(TypedDict):
    sections: list[SectionSummary]


class FieldSchema(TypedDict):
    id: str
    file: str
    key: str
    control: str
    label: str
    help: str
    default: Any
    recommended: bool
    personal: bool
    options: list[Any]
    strict_options: bool
    min: Union[int, float, None]
    max: Union[int, float, None]
    step: Union[int, float, None]
    integer: bool
    nullable: bool
    unit: str
    locked: bool
    readonly: bool
    note: str


class PolicyItem(TypedDict):
    """A locked row: a rule the code enforces whatever the config says."""
    control: Literal["policy"]
    label: str
    value: str
    why: str
    locked: Literal[True]


class GroupSchema(TypedDict):
    id: str
    title: str
    help: str
    items: list[Union[PolicyItem, FieldSchema]]


class SectionSchema(TypedDict):
    id: str
    title: str
    help: str
    files: list[str]
    groups: list[GroupSchema]


class UnquotedWarning(TypedDict):
    message: str
    intended: Any


class SectionData(TypedDict):
    section: SectionSchema
    values: dict[str, Any]
    defaults: dict[str, Any]
    warnings: dict[str, UnquotedWarning]
    files: dict[str, str]
    version: str


def section_list() -> list[SectionSummary]:
    return [{"id": s.id, "title": s.title, "help": s.help, "files": s.files()} for s in SECTIONS]


def invalid_body(e: SettingsInvalid) -> dict[str, Any]:
    n = len(e.fields) + len(e.general)
    return {"detail": f"Fix {n} error{'' if n == 1 else 's'} to save.", "fields": dict(e.fields),
            "general": list(e.general)}


def relative_files(files: dict[str, str], root: Path) -> dict[str, str]:
    """{file: path relative to the repo root} (a symlinked or outside path shows its file name only)."""
    out = {}
    for k, p in files.items():
        try:
            out[k] = Path(p).relative_to(root).as_posix()
        except ValueError:
            out[k] = Path(p).name
    return out


def check_weights(weights: dict[str, Any]) -> dict[str, float]:
    from careeros.runs.config import DEFAULT_RANKING

    out: dict[str, float] = {}
    for k, v in (weights or {}).items():
        if k not in DEFAULT_RANKING:
            raise ValueError(f"unknown ranking weight {k!r}; valid: {', '.join(DEFAULT_RANKING)}")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise ValueError(f"runs.ranking.{k} must be a number 0 or more")
        out[k] = float(v)
    return out


def ranking_preview(settings: Any, kind: str, weights: dict[str, Any], now: datetime,
                    limit: int = 5) -> dict[str, Any]:
    from careeros.runs.config import load_runs_config
    from careeros.runs.runner import select_candidates

    if kind not in PREVIEW_KINDS:
        raise ValueError("kind must be score or prepare")
    draft = check_weights(weights)
    cfg = load_runs_config(settings)
    cfg = replace(cfg, ranking={**cfg.ranking, **draft})
    ranked, _ = select_candidates(settings, kind, cfg, now)
    return {"kind": kind, "items": ranked[:limit], "total": len(ranked)}
