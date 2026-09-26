"""Flagged registry (reason, confidence, evidence, expiry, review state) and verified-company records."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import yaml

from careeros.safety import registry

pytestmark = pytest.mark.unit


def test_missing_file_is_empty(tmp_path):
    assert registry.load(tmp_path / "none.yaml") == []


def test_add_then_bump_keeps_reason_confidence_evidence_expiry(tmp_path):
    path = tmp_path / "data" / "flagged_registry.yaml"
    e1 = registry.add_or_bump(path, company="Shady LLC", domain="shady.xyz", reason="SCAM_PAYMENT_REQUEST",
                              job_id="aaa", confidence="high", evidence=["https://shady.xyz/job"])
    assert e1["count"] == 1 and e1["state"] == "active" and e1["confidence"] == "high"
    exp = datetime.fromisoformat(e1["expires_at"])
    assert timedelta(days=170) < exp - datetime.now(timezone.utc) < timedelta(days=190)
    e2 = registry.add_or_bump(path, company="Shady", reason="SCAM_FREE_EMAIL_RECRUITER", job_id="bbb",
                              confidence="medium", evidence=["https://shady.xyz/job2"])
    assert e2["count"] == 2 and e2["job_ids"] == ["aaa", "bbb"] and e2["confidence"] == "high"  # never downgraded
    assert e2["evidence"] == ["https://shady.xyz/job", "https://shady.xyz/job2"]
    entries = yaml.safe_load(path.read_text())["entries"]
    assert len(entries) == 1 and "SCAM_FREE_EMAIL_RECRUITER" in entries[0]["reason"]


@pytest.mark.parametrize("company,domain,hit", [
    ("Shady LLC", "", True),
    ("shady", "", True),
    ("Other", "https://apply.shady.xyz/form", True),
    ("Other", "other.com", False),
    ("", "", False),
])
def test_is_flagged(company, domain, hit):
    entries = [{"company": "Shady LLC", "domain": "shady.xyz", "state": "active"}]
    assert bool(registry.is_flagged(entries, company, domain)) is hit


@pytest.mark.parametrize("entry", [
    {"company": "Shady", "state": "cleared"},
    {"company": "Shady", "state": "active", "expires_at": "2020-01-01T00:00:00+00:00"},
])
def test_cleared_and_expired_entries_never_match(entry):
    assert registry.is_flagged([entry], "Shady") is None


def test_shared_ats_domain_is_never_stored(tmp_path):
    e = registry.add_or_bump(tmp_path / "r.yaml", company="X", domain="boards.greenhouse.io", reason="r")
    assert e["domain"] == ""


def test_clear_sets_state_and_keeps_history(tmp_path):
    path = tmp_path / "r.yaml"
    registry.add_or_bump(path, company="Shady", reason="r", confidence="high")
    e = registry.clear(path, "Shady", note="confirmed legit by phone")
    assert e["state"] == "cleared" and "confirmed legit" in e["review_note"]
    assert registry.is_flagged(registry.load(path), "Shady") is None


def test_default_path(settings):
    assert registry.default_path(settings).name == "flagged_registry.yaml"


def test_verified_record_needs_two_signals_for_low_risk(tmp_path):
    path = tmp_path / "verified_companies.yaml"
    with pytest.raises(ValueError):
        registry.add_verified(path, "Nimbus", risk="low", signals=["website"])
    e = registry.add_verified(path, "Nimbus", risk="low", domain="nimbusq.com",
                              signals=["official site describes product", "careers page lists role"],
                              evidence=["https://nimbusq.com/careers"])
    e = registry.add_verified(path, "Nimbus", risk="low", signals=["LinkedIn: founders identifiable"],
                              evidence=["https://linkedin.com/company/nimbusq"])
    assert len(registry.load(path)) == 1 and len(e["signals"]) == 3 and len(e["evidence"]) == 2
    assert e["risk"] == "low" and e["domain"] == "nimbusq.com" and e["checked_at"]
