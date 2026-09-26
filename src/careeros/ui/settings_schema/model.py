"""Settings schema building blocks: a Field is one form control bound to one YAML key, a Policy is a locked row the
system enforces, a Group is one card of a Settings page, a Section is one page.

Pure data plus validation; no FastAPI, no file IO. The UI renders every section from `Section.to_dict()` with one
generic form renderer, so a new setting is one Field here (and its key in examples/config).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

# Controls the generic renderer knows. Values:
#   switch bool · number / slider int|float · select / preset_cards one of options · text str · time "HH:MM"
#   time_range {start, end} | null · tags [str] · rule_list [token] or [{if, tier}] · reason_levels {CODE: level}
#   schedule {every_hours|every_days|at, enabled, preset, ...} · key_value {str: value} · records [{...}]
CONTROLS = ("switch", "number", "slider", "select", "preset_cards", "text", "time", "time_range", "tags",
            "rule_list", "reason_levels", "schedule", "key_value", "records")
FILES = ("targets", "companies", "qa", "pipeline")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

Check = Callable[[Any], "str | None"]
SectionCheck = Callable[[dict[str, Any]], list[tuple[str, str]]]


@dataclass(frozen=True)
class Field:
    file: str                       # targets | companies | qa | pipeline (config/<file>.yaml)
    key: str                        # dotted path in that file
    control: str
    label: str
    help: str = ""
    default: Any = None             # the value "Reset to recommended" writes; None for personal fields
    recommended: bool = True        # the UI shows "(Recommended)" next to `default`
    personal: bool = False          # the candidate's own facts (INSERT in examples): no recommended value
    options: tuple[Any, ...] = ()   # select / preset_cards / tags / reason_levels choices
    strict_options: bool = True     # tags: only `options` allowed (False: options are suggestions)
    min: float | None = None
    max: float | None = None
    step: float | None = None
    integer: bool = False
    nullable: bool = False
    unit: str = ""
    locked: bool = False            # policy the system enforces: shown, never editable
    readonly: bool = False          # shown, not editable in this version
    note: str = ""                  # why locked / readonly
    pattern: str | None = None      # text: the value must match; tags / rule_list: every item must match
    check: Check | None = None      # extra per-value check -> error text

    @property
    def id(self) -> str:
        return f"{self.file}:{self.key}"

    @property
    def editable(self) -> bool:
        return not (self.locked or self.readonly)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "file": self.file, "key": self.key, "control": self.control, "label": self.label,
                "help": self.help, "default": self.default, "recommended": self.recommended,
                "personal": self.personal, "options": list(self.options), "strict_options": self.strict_options,
                "min": self.min, "max": self.max, "step": self.step, "integer": self.integer,
                "nullable": self.nullable, "unit": self.unit, "locked": self.locked, "readonly": self.readonly,
                "note": self.note}


@dataclass(frozen=True)
class Policy:
    """A locked row: a rule the code enforces whatever the config says."""
    label: str
    value: str
    why: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"control": "policy", "label": self.label, "value": self.value, "why": self.why, "locked": True}


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    items: tuple[Field | Policy, ...]
    help: str = ""

    def fields(self) -> list[Field]:
        return [i for i in self.items if isinstance(i, Field)]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "help": self.help, "items": [i.to_dict() for i in self.items]}


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    groups: tuple[Group, ...]
    help: str = ""
    checks: tuple[SectionCheck, ...] = ()

    def fields(self) -> list[Field]:
        return [f for g in self.groups for f in g.fields()]

    def field(self, fid: str) -> Field | None:
        return next((f for f in self.fields() if f.id == fid), None)

    def group(self, gid: str) -> Group | None:
        return next((g for g in self.groups if g.id == gid), None)

    def files(self) -> list[str]:
        return sorted({f.file for f in self.fields()})

    def check(self, values: dict[str, Any]) -> list[tuple[str, str]]:
        """Cross-field checks over the effective values ({field id: value}); [(field id, message)]."""
        return [e for c in self.checks for e in c(values)]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "help": self.help, "files": self.files(),
                "groups": [g.to_dict() for g in self.groups]}


# --- validation -------------------------------------------------------------------------------------------

def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def _number(f: Field, v: Any) -> str | None:
    if not _is_num(v):
        return "Enter a number."
    if f.integer and not float(v).is_integer():
        return "Enter a whole number."
    if f.min is not None and v < f.min:
        return f"Must be at least {_fmt(f.min)}."
    if f.max is not None and v > f.max:
        return f"Must be at most {_fmt(f.max)}."
    return None


def _str_list(v: Any) -> str | None:
    if not isinstance(v, list):
        return "Must be a list."
    if not all(isinstance(x, str) and x.strip() for x in v):
        return "Every entry needs some text."
    return None


def _shape(f: Field, v: Any) -> str | None:
    c = f.control
    if c == "switch":
        return None if isinstance(v, bool) else "Must be on or off."
    if c in ("number", "slider"):
        return _number(f, v)
    if c in ("select", "preset_cards"):
        return None if v in f.options else f"Choose one of: {', '.join(map(str, f.options))}."
    if c == "text":
        if not isinstance(v, str):
            return "Must be text."
        return "That format isn't recognised." if f.pattern and not re.fullmatch(f.pattern, v) else None
    if c == "time":
        return None if isinstance(v, str) and _HHMM.match(v) else "Use 24-hour HH:MM, e.g. 09:00."
    if c == "time_range":
        if not (isinstance(v, dict) and set(v) == {"start", "end"}):
            return "Needs a start and an end time."
        ok = all(isinstance(v[k], str) and _HHMM.match(v[k]) for k in ("start", "end"))
        return None if ok else "Use 24-hour HH:MM, e.g. 09:00."
    if c == "tags" or (c == "rule_list" and f.pattern):
        err = _str_list(v)
        if err:
            return err
        if f.options and f.strict_options:
            bad = [x for x in v if x not in f.options]
            if bad:
                return f"Not an option: {', '.join(bad)}."
        if f.pattern:
            bad = [x for x in v if not re.fullmatch(f.pattern, x)]
            if bad:
                return f"Not a valid rule: {', '.join(bad)}."
        return None
    if c in ("rule_list", "records"):
        ok = isinstance(v, list) and all(isinstance(x, dict) for x in v)
        return None if ok else "Must be a list of rows."
    if c in ("key_value", "schedule"):
        return None if isinstance(v, dict) else "Must be a set of name: value pairs."
    if c == "reason_levels":
        if not isinstance(v, dict):
            return "Must map each check code to a level."
        codes = {str(o).upper() for o in f.options}
        for code, level in v.items():
            if str(code).upper() not in codes:
                return f"Unknown check code {code}."
            if level not in ("block", "skip", "review", "info", "off"):
                return f"{code}: choose block, skip, review, info or off."
        return None
    return f"Unknown control {c}."


def validate_value(f: Field, v: Any) -> str | None:
    """Plain-language error for `v` in field `f`, or None when it's valid. Shape only: the config loaders run after
    the write (settings_io) and catch anything that needs the whole file."""
    if v is None:
        return None if f.nullable else "A value is required."
    err = _shape(f, v)
    if err is None and f.check is not None:
        err = f.check(v)
    return err
