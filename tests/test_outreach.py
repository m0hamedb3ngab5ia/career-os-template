"""Outreach gate: a contact the candidate already knows on LinkedIn (1st degree, or any mutual connections)
never gets an automated message; the draft is marked for the candidate to tailor by hand."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from careeros.models import Contact
from careeros.outreach import (
    OutreachPolicy,
    check_contacts,
    mark_contact,
    needs_manual_outreach,
)

pytestmark = pytest.mark.unit

ON = OutreachPolicy()


def test_policy_defaults_are_on():
    assert ON.manual_if_connected is True
    assert ON.manual_if_mutuals is True


def test_policy_from_example_settings(example_settings):
    p = OutreachPolicy.from_settings(example_settings)
    assert p == OutreachPolicy(manual_if_connected=True, manual_if_mutuals=True)


def test_policy_missing_block_uses_defaults(example_settings):
    example_settings.pipeline.pop("outreach", None)
    assert OutreachPolicy.from_settings(example_settings) == ON


def test_policy_reads_overrides(example_settings):
    example_settings.pipeline["outreach"] = {"manual_if_connected": True, "manual_if_mutuals": False}
    assert OutreachPolicy.from_settings(example_settings).manual_if_mutuals is False


def test_first_degree_is_manual():
    assert needs_manual_outreach({"name": "Jane", "linkedin_degree": 1}, ON) == (True, "LINKEDIN_CONNECTED")


def test_mutuals_are_manual():
    assert needs_manual_outreach({"name": "Jane", "linkedin_degree": 2, "mutuals": 3}, ON) == (True, "LINKEDIN_MUTUALS")


def test_connected_wins_over_mutuals():
    assert needs_manual_outreach({"linkedin_degree": 1, "mutuals": 5}, ON) == (True, "LINKEDIN_CONNECTED")


def test_stranger_or_unknown_is_automatable():
    assert needs_manual_outreach({"linkedin_degree": 3, "mutuals": 0}, ON) == (False, None)
    assert needs_manual_outreach({"name": "Unknown"}, ON) == (False, None)
    assert needs_manual_outreach({"linkedin_degree": None, "mutuals": None}, ON) == (False, None)


def test_switches_off():
    off = OutreachPolicy(manual_if_connected=False, manual_if_mutuals=False)
    assert needs_manual_outreach({"linkedin_degree": 1, "mutuals": 4}, off) == (False, None)
    only_connected = OutreachPolicy(manual_if_connected=True, manual_if_mutuals=False)
    assert needs_manual_outreach({"linkedin_degree": 2, "mutuals": 4}, only_connected) == (False, None)


def test_accepts_contact_model():
    c = Contact(company="Acme", name="Jane", linkedin_degree=1)
    assert needs_manual_outreach(c, ON) == (True, "LINKEDIN_CONNECTED")


def test_contact_model_validates_degree_and_mutuals():
    with pytest.raises(ValueError):
        Contact(company="Acme", name="Jane", linkedin_degree=4)
    with pytest.raises(ValueError):
        Contact(company="Acme", name="Jane", mutuals=-1)


def test_check_contacts_reports_each():
    data = {"contacts": [
        {"name": "Jane", "role": "recruiter", "linkedin_degree": 1},
        {"name": "Sam", "role": "team_lead", "mutuals": 2},
        {"name": "Kim", "role": "hiring_manager"},
    ]}
    out = check_contacts(data, ON)
    assert [(r["name"], r["manual"], r["reason"]) for r in out] == [
        ("Jane", True, "LINKEDIN_CONNECTED"), ("Sam", True, "LINKEDIN_MUTUALS"), ("Kim", False, None)]
    assert out[1]["detail"] == "2 mutual connections"
    assert out[0]["detail"] == "connected on LinkedIn"


def test_mark_contact_updates_file(tmp_path: Path):
    f = tmp_path / "contacts.json"
    f.write_text(json.dumps({"contacts": [{"name": "Jane Doe"}, {"name": "Sam"}]}))
    c = mark_contact(f, "jane doe", degree=1, mutuals=4)
    assert c["linkedin_degree"] == 1 and c["mutuals"] == 4
    saved = json.loads(f.read_text())
    assert saved["contacts"][0]["linkedin_degree"] == 1
    assert "linkedin_degree" not in saved["contacts"][1]


def test_mark_contact_partial_and_errors(tmp_path: Path):
    f = tmp_path / "contacts.json"
    f.write_text(json.dumps({"contacts": [{"name": "Jane", "linkedin_degree": 2}]}))
    assert mark_contact(f, "Jane", mutuals=0)["linkedin_degree"] == 2
    with pytest.raises(KeyError):
        mark_contact(f, "Nobody", degree=1)
    with pytest.raises(ValueError):
        mark_contact(f, "Jane", degree=0)
    with pytest.raises(ValueError):
        mark_contact(f, "Jane", mutuals=-2)
