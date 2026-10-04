"""Deterministic prompt-injection scan of untrusted posting/imported text (REQ-109, DEC-002).

`scan` returns human-readable reasons (empty = clean). Store.save_posting runs it on every posting it stores and
records hits in the job's flags.json; `blocked(flags)` is what the runner's eligibility checks before prepare/apply.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_INSTRUCTION = re.compile(
    r"\b(?:ignore|disregard)\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\b|\bsystem prompt\b|\byou are now\b"
    r"|\bas an ai\b|\bnew instructions\b", re.I)
_HIDDEN_CHARS = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
_HIDDEN_HTML = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d])|opacity\s*:\s*0(?![.\d])"
    r"|(?<![-\w])color\s*:\s*(?:#fff(?:fff)?\b|white\b|transparent\b|rgba\([^)]*,\s*0\s*\))", re.I)
_TOOLS = re.compile(r"\bBash\b|\bWebFetch\b|\bWebSearch\b|\bcurl\s|mcp__\w*|\bcareeros\s", re.I)
_EMAIL = re.compile(r"mailto:|[\w.+-]+@[\w-]+\.[\w.-]+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n")  # a "." inside "x@y.io" is not a sentence end


def _hit(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(0).strip() if m else None


def scan(text: str, html: str = "", extra: Iterable[str] = ()) -> list[str]:
    """Reasons this posting looks like a prompt-injection attempt; [] = clean. `extra` = config regexes."""
    both = f"{text}\n{html}"
    reasons = []
    if m := _hit(_INSTRUCTION, both):
        reasons.append(f"instruction phrase: {m!r}")
    if m := _HIDDEN_CHARS.search(both):
        reasons.append(f"zero-width/bidi char U+{ord(m.group(0)):04X}")
    if m := _hit(_HIDDEN_HTML, html):
        reasons.append(f"hidden html: {m!r}")
    if m := _hit(_TOOLS, both):
        reasons.append(f"tool name: {m!r}")
    if any(_INSTRUCTION.search(s) and _EMAIL.search(s) for s in _SENTENCE_END.split(both)):
        reasons.append("email in instruction sentence")
    for pat in extra:
        if re.search(pat, both, re.I):
            reasons.append(f"extra pattern: {pat}")
    return reasons


def blocked(flags: dict[str, Any] | None) -> bool:
    """Flagged and not yet cleared by the user (`careeros job clear-injection`)."""
    return bool(flags and flags.get("injection_suspected") and not flags.get("injection_cleared_at"))
