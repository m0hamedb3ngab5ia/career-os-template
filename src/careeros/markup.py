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

# Where `**` may appear, as field paths (`experience[0].bullets[2].text`, `skills.programming[0]`). One source of
# truth for doctor (profile/master.yaml) and templates/resume/render.py (resume.json): `**` anywhere else is an error.
BULLET_SECTIONS = ("experience", "projects", "leadership")
_BULLET = r"(?:%s)\[\d+\]\.bullets\[\d+\]" % "|".join(BULLET_SECTIONS)
_KEY = r"(?:\.[^.\[\]]+|\[\d+\])"  # one dict key or list index
_BOLD_PATHS = {
    # master.yaml: bullet text, every bullet variant, every summary variant
    "master": re.compile(rf"^(?:summary_variants{_KEY}|{_BULLET}\.(?:text|variants{_KEY}))$"),
    # resume.json: the tailored bullet text and the chosen summary
    "resume": re.compile(rf"^(?:summary|{_BULLET}\.text)$"),
}


def bold_allowed(path: str, source: Literal["master", "resume"]) -> bool:
    """True when `**bold**` markup may appear at field `path` of profile/master.yaml ("master") or resume.json
    ("resume")."""
    return bool(_BOLD_PATHS[source].match(path))


def iter_strings(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """(field path, value) for every string in a YAML/JSON tree: `a.b[0].c`."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from iter_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


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
