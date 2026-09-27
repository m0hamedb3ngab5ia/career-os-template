"""Declarative Settings schema: one Field per YAML key the UI can edit (see sections.py)."""
from __future__ import annotations

from typing import Any

from careeros.ui.settings_schema.model import CONTROLS, Field, Group, Policy, Section, validate_value
from careeros.ui.settings_schema.sections import NOT_IN_UI, SAFETY_CODES, SECTIONS

__all__ = ["CONTROLS", "NOT_IN_UI", "SAFETY_CODES", "SECTIONS", "Field", "Group", "Policy", "Section",
           "get_section", "reset_group", "validate_value"]


def get_section(section_id: str) -> Section | None:
    return next((s for s in SECTIONS if s.id == section_id), None)


def reset_group(section_id: str, group_id: str) -> dict[str, Any]:
    """{field id: recommended value} for the group's editable fields ("Reset to recommended"). Personal fields
    have no recommended value and are left out. KeyError for an unknown section or group."""
    sec = get_section(section_id)
    group = sec.group(group_id) if sec else None
    if group is None:
        raise KeyError(f"{section_id}/{group_id}")
    return {f.id: f.default for f in group.fields() if f.editable and not f.personal}
