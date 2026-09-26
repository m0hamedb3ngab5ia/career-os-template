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

from typing import Any

MARKER = "**"


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
