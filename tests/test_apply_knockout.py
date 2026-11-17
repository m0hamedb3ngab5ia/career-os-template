"""Knockout-risk detection on fill plans (research: docs/work/yield-model/research/greenhouse.md s2)."""
from __future__ import annotations

import pytest

from careeros.apply.knockout import knockout_risk

pytestmark = pytest.mark.unit


def f(label, value, **kw):
    return {"field_id": "q", "label": label, "value": value, "type": "select", **kw}


@pytest.mark.parametrize("label,value,want", [
    ("Are you legally authorized to work in the United States?", "No", "work_authorization"),
    ("Will you now or in the future require sponsorship for employment visa status?", "Yes", "sponsorship"),
    ("Are you willing to work on-site in Austin, TX?", "No", "location"),
    ("Are you willing to relocate?", "No", "location"),
    ("Do you currently reside in the United States?", "No", "location"),
    ("Do you have 5+ years of experience with Python?", "No", "years_experience"),
    ("Do you have a Bachelor's degree or higher?", "No", "degree"),
])
def test_flags_negative_answers(label, value, want):
    assert knockout_risk([f(label, value)]) == [want]


@pytest.mark.parametrize("label,value", [
    ("Are you legally authorized to work in the United States?", "Yes"),
    ("Will you require sponsorship?", "No"),
    ("Are you willing to work on-site in Austin, TX?", "Yes"),
    ("Why do you want to work here?", "No"),
    ("Are you legally authorized to work in the United States?", None),
])
def test_ignores_safe_or_unrelated(label, value):
    assert knockout_risk([f(label, value)]) == []


def test_skipped_fields_ignored_and_labels_deduped():
    rows = [f("Are you authorized to work in the US?", "No", skipped=True),
            f("Are you eligible to work in the US?", "No"), f("Legally authorized to work?", "No")]
    assert knockout_risk(rows) == ["work_authorization"]


@pytest.mark.parametrize("value,expected", [("Yes", []), ("No", ["work_authorization"])])
def test_authorized_without_sponsorship_is_an_authorization_question(value, expected):
    label = "Are you legally authorized to work in the United States without visa sponsorship?"
    assert knockout_risk([f(label, value)]) == expected
