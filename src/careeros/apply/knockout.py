"""Likely auto-reject answers in a fill plan. Warning only: never changes an answer, never blocks.

Greenhouse employers can auto-reject on Yes/No and select answers (work authorization, sponsorship, location,
minimum years, degree). Research: docs/work/yield-model/research/greenhouse.md s2.
"""
from __future__ import annotations

import re
from typing import Any

_NO, _YES = re.compile(r"^\s*no\b", re.I), re.compile(r"^\s*yes\b", re.I)
# (label, question regex, knockout answer). First match per field wins; "authorized ... without sponsorship" is an
# authorization question (No = knockout), so it is checked before the plain sponsorship rule.
_RULES: list[tuple[str, re.Pattern[str], re.Pattern[str]]] = [
    ("work_authorization", re.compile(r"without\s+(\w+\s+)?sponsor", re.I), _NO),
    ("sponsorship", re.compile(r"sponsor|visa", re.I), _YES),
    ("work_authorization", re.compile(r"(authori[sz]ed|eligible|legally|right) to work|work authori[sz]ation", re.I), _NO),
    ("location", re.compile(r"on-?site|in[- ]office|relocat|(reside|located|live|based) in|commut", re.I), _NO),
    ("years_experience", re.compile(r"\d+\+?\s*(or more )?years|years of (professional |relevant )?experience", re.I), _NO),
    ("degree", re.compile(r"(bachelor|master|degree|phd)", re.I), _NO),
]


def knockout_risk(fields: list[dict[str, Any]]) -> list[str]:
    """Labels of the knockout categories hit by a negative answer, in first-seen order, deduplicated."""
    out: list[str] = []
    for f in fields:
        v = f.get("value")
        if f.get("skipped") or not isinstance(v, str):
            continue
        for label, q, bad in _RULES:
            if q.search(str(f.get("label") or "")):
                if bad.search(v) and label not in out:
                    out.append(label)
                break
    return out
