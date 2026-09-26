"""`**bold**` markup inside profile bullet text (and summary_variants).

The candidate marks tech names and metrics in `profile/master.yaml` bullet text:

    text: Built a **FastAPI** service in **Python**, processing **2 million events per day**

tailor-resume copies the text (markers included) into resume.json; templates/resume/render.py turns each span
into `\\textbf{...}` in resume.tex and drops the markers from resume.txt. Every truth / number / keyword check
compares `strip_bold(text)`, so bold never changes a QA verdict. Prose (cover letters, answers, outreach) never
carries markers.

Rules (`validate_bold`): markers come in pairs, a span is non-empty and has no leading/trailing space, and
`***` is not allowed (flat markup: no nesting, no bold next to a literal `*`). A single `*` is plain text.

Pure functions, standard library only: the standalone render script imports this module too.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Literal

MARKER = "**"

# Where `**` may appear: bullet text / variants and summary_variants in master.yaml, bullet text and the summary in
# resume.json. One source of truth for doctor and templates/resume/render.py: `**` anywhere else is an error.
BULLET_SECTIONS = ("experience", "projects", "leadership")


def bold_allowed_at(keys: tuple[Any, ...], source: Literal["master", "resume"]) -> bool:
    """Structural twin of `bold_allowed`: `keys` is the field's key/index tuple, so a dict key containing `.` or
    `[` (`variants: {long.v2: ...}`) can't be mistaken for extra path segments."""
    bullet = (len(keys) >= 5 and keys[0] in BULLET_SECTIONS and isinstance(keys[1], int)
              and keys[2] == "bullets" and isinstance(keys[3], int))
    if source == "resume":
        return keys == ("summary",) or (bullet and keys[4:] == ("text",))
    if keys[:1] == ("summary_variants",) and len(keys) >= 2:
        return True
    return bullet and (keys[4:] == ("text",) or (keys[4] == "variants" and len(keys) >= 6))


def iter_fields(node: Any, keys: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], str]]:
    """(key/index tuple, value) for every string in a YAML/JSON tree: ("a", "b", 0, "c")."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from iter_fields(v, (*keys, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_fields(v, (*keys, i))
    elif isinstance(node, str):
        yield keys, node


def format_path(keys: tuple[Any, ...]) -> str:
    """("a", "b", 0) -> "a.b[0]" (for messages)."""
    out = ""
    for k in keys:
        out += f"[{k}]" if isinstance(k, int) else (f".{k}" if out else str(k))
    return out


def strip_bold(text: Any) -> str:
    """`text` with every `**` removed (also from invalid markup, so a marker never leaks). None -> ""."""
    if text is None:
        return ""
    return str(text).replace(MARKER, "")


def validate_bold(text: Any) -> str | None:
    """None when `text` is valid markup (or not a string); else a one-line reason."""
    if not isinstance(text, str) or MARKER not in text:
        return None
    if "****" in text:
        return "empty bold span ('****')"
    if "***" in text:
        return "'***' is not allowed (no nested bold, no bold next to a literal '*')"
    parts = text.split(MARKER)
    if len(parts) % 2 == 0:
        return "unbalanced '**' (odd number of markers)"
    for span in parts[1::2]:
        if not span.strip():
            return "empty bold span ('****' or '** **')"
        if span != span.strip():
            return f"bold span '{span}' starts or ends with a space (nested or misplaced '**'?)"
    return None


def bold_spans(text: Any) -> list[str]:
    """The bolded phrases of `text`, in order. Raises ValueError on invalid markup."""
    err = validate_bold(text)
    if err:
        raise ValueError(f"invalid **bold** markup: {err}")
    if not isinstance(text, str):
        return []
    return text.split(MARKER)[1::2]


# The one `**` that is never markup: a numeric power (`2**32`, `10**6`, `2 ** 10`). Every other `**` in prose counts,
# on purpose: a code snippet with `**` in an answer is a visible false alarm, a pasted bullet marker is not.
_NUMERIC_POWER = re.compile(r"(?<=\d)\s?\*\*\s?(?=\d)")


def has_markdown_bold(text: Any) -> bool:
    """True when `text` holds any `**` other than a numeric power: bold pairs, glued pairs (`**REST API**s`) and
    stray markers copied from bullet text all count."""
    return isinstance(text, str) and MARKER in _NUMERIC_POWER.sub(" ", text)
