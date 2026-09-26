"""Outreach gate: people the candidate already knows on LinkedIn get a hand-tailored message, never an automated one.

`contacts.json` entries may carry `linkedin_degree` (1 = connected) and `mutuals` (count of mutual connections),
recorded by the candidate with `careeros outreach mark`. `draft-outreach` calls `careeros outreach check` and, for a
manual contact, marks the draft `manual_tailor: true` and opens a `send_linkedin` Action Item instead of queueing it.
Unknown degree/mutuals = no known relationship = the normal (draft-only / verified-email) rules apply.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from careeros.config import Settings
from careeros.models import Contact

LINKEDIN_CONNECTED = "LINKEDIN_CONNECTED"
LINKEDIN_MUTUALS = "LINKEDIN_MUTUALS"


@dataclass(frozen=True)
class OutreachPolicy:
    manual_if_connected: bool = True
    manual_if_mutuals: bool = True

    @classmethod
    def from_settings(cls, s: Settings) -> "OutreachPolicy":
        cfg = s.pipeline.get("outreach") or {}
        return cls(manual_if_connected=bool(cfg.get("manual_if_connected", True)),
                   manual_if_mutuals=bool(cfg.get("manual_if_mutuals", True)))


def _fields(contact: Mapping[str, Any] | Contact) -> tuple[int | None, int | None]:
    if isinstance(contact, Contact):
        return contact.linkedin_degree, contact.mutuals
    return contact.get("linkedin_degree"), contact.get("mutuals")


def needs_manual_outreach(contact: Mapping[str, Any] | Contact, policy: OutreachPolicy) -> tuple[bool, str | None]:
    """(manual, reason code). Connected beats mutuals when both apply."""
    degree, mutuals = _fields(contact)
    if policy.manual_if_connected and degree == 1:
        return True, LINKEDIN_CONNECTED
    if policy.manual_if_mutuals and (mutuals or 0) > 0:
        return True, LINKEDIN_MUTUALS
    return False, None


def _detail(reason: str | None, mutuals: int | None) -> str:
    if reason == LINKEDIN_CONNECTED:
        return "connected on LinkedIn"
    if reason == LINKEDIN_MUTUALS:
        return f"{mutuals} mutual connection{'' if mutuals == 1 else 's'}"
    return ""


def check_contacts(data: Mapping[str, Any], policy: OutreachPolicy) -> list[dict[str, Any]]:
    out = []
    for c in data.get("contacts") or []:
        manual, reason = needs_manual_outreach(c, policy)
        out.append({"name": c.get("name", ""), "role": c.get("role", ""), "manual": manual, "reason": reason,
                    "detail": _detail(reason, c.get("mutuals"))})
    return out


def mark_contact(path: Path, name: str, degree: int | None = None, mutuals: int | None = None) -> dict[str, Any]:
    """Record degree/mutuals for the contact named `name` (case-insensitive) in contacts.json; returns the entry."""
    if degree is not None and not 1 <= degree <= 3:
        raise ValueError("degree must be 1, 2 or 3")
    if mutuals is not None and mutuals < 0:
        raise ValueError("mutuals must be >= 0")
    data = json.loads(path.read_text(encoding="utf-8"))
    key = name.strip().lower()
    for c in data.get("contacts") or []:
        if str(c.get("name", "")).strip().lower() == key:
            if degree is not None:
                c["linkedin_degree"] = degree
            if mutuals is not None:
                c["mutuals"] = mutuals
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            return c
    raise KeyError(name)
