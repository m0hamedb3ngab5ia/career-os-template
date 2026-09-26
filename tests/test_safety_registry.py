"""Flagged company/domain registry (data/flagged_registry.yaml)."""
from __future__ import annotations

import pytest
import yaml

from careeros.safety import registry

pytestmark = pytest.mark.unit


def test_missing_file_is_empty(tmp_path):
    assert registry.load(tmp_path / "none.yaml") == []


def test_add_then_bump(tmp_path):
    path = tmp_path / "data" / "flagged_registry.yaml"
    e1 = registry.add_or_bump(path, company="Shady LLC", domain="shady.xyz", reason="apply_domain", job_id="aaa")
    assert e1["count"] == 1 and e1["job_ids"] == ["aaa"]
    e2 = registry.add_or_bump(path, company="Shady", domain="", reason="free_email_contact", job_id="bbb")
    assert e2["count"] == 2 and e2["job_ids"] == ["aaa", "bbb"]
    entries = yaml.safe_load(path.read_text())["entries"]
    assert len(entries) == 1 and "free_email_contact" in entries[0]["reason"]


@pytest.mark.parametrize("company,domain,hit", [
    ("Shady LLC", "", True),
    ("shady", "", True),
    ("Other", "https://apply.shady.xyz/form", True),
    ("Other", "other.com", False),
    ("", "", False),
])
def test_is_flagged(company, domain, hit):
    entries = [{"company": "Shady LLC", "domain": "shady.xyz"}]
    assert bool(registry.is_flagged(entries, company, domain)) is hit


def test_entry_without_domain_never_matches_on_domain():
    assert registry.is_flagged([{"company": "X", "domain": ""}], "Y", "whatever.com") is None


def test_default_path(settings, tmp_path):
    assert registry.default_path(settings).name == "flagged_registry.yaml"


def test_verified_list_round_trip(tmp_path):
    path = tmp_path / "verified_companies.yaml"
    registry.add_verified(path, "Nimbus Quantum", domain="nimbusq.com", evidence="https://nimbusq.com/careers")
    registry.add_verified(path, "Nimbus Quantum", domain="nimbusq.com", evidence="linkedin 120 employees")
    e = registry.load(path)
    assert len(e) == 1 and "linkedin" in e[0]["evidence"] and e[0]["domain"] == "nimbusq.com"
