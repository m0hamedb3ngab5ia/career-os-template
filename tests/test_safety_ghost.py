"""Ghost-job detection lowers confidence or asks for review; it skips only when every sign lines up."""
from __future__ import annotations

from datetime import date

import pytest

from careeros.models import Posting
from careeros.safety.ghost import check_ghost, ghost_settings, history_key, load_signals
from careeros.safety.scam import verdict

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 25)


def _p(**kw) -> Posting:
    base = dict(company="Nimbus", title="Software Engineer", location="New York, NY", ats="greenhouse",
                ats_job_id="1", url="https://boards.greenhouse.io/nimbus/jobs/1", posted_at="2026-09-20T10:00:00Z")
    base.update(kw)
    return Posting(**base)


def _codes(flags, level=None):
    return {f.code for f in flags if level is None or f.level == level}


def test_defaults(example_settings):
    g = ghost_settings(example_settings)
    assert (g["old_post_days"], g["very_old_post_days"], g["recent_update_days"], g["repost_flag_count"]) == (30, 45, 30, 3)


def test_fresh_posting_is_clean(example_settings):
    assert check_ghost(_p(), None, {}, example_settings, today=TODAY) == []


def test_30_days_only_lowers_confidence(example_settings):
    flags = check_ghost(_p(posted_at="2026-08-20"), None, {}, example_settings, today=TODAY)
    assert _codes(flags, "info") == {"GHOST_OLD_POST"} and verdict(flags) == "pass"


def test_45_days_with_recent_update_or_hiring_is_review(example_settings):
    p = _p(posted_at="2026-06-01", last_updated="2026-09-10")
    assert verdict(check_ghost(p, None, {}, example_settings, today=TODAY)) == "review"
    company_hist = {"nimbus|backend engineer|new york ny": {"first_published": "2026-09-15"}}
    p2 = _p(posted_at="2026-06-01", last_updated="2026-06-01")
    flags = check_ghost(p2, None, {}, example_settings, today=TODAY, company_history=company_hist)
    assert verdict(flags) == "review" and "GHOST_STALE_NO_ACTIVITY" not in _codes(flags)


def test_skip_only_when_old_no_update_no_hiring_not_evergreen(example_settings):
    p = _p(posted_at="2026-06-01", last_updated="2026-06-01")
    flags = check_ghost(p, None, {}, example_settings, today=TODAY, company_history={})
    assert _codes(flags, "skip") == {"GHOST_STALE_NO_ACTIVITY"}


@pytest.mark.parametrize("kw", [
    {"title": "Software Engineer (Evergreen)"},
    {"description_text": "We hire for this role on a rolling basis throughout the year."},
    {"title": "Senior Staff Engineer"},
])
def test_evergreen_or_senior_roles_are_never_skipped(example_settings, kw):
    p = _p(posted_at="2026-05-01", last_updated="2026-05-01", **kw)
    flags = check_ghost(p, None, {}, example_settings, today=TODAY, company_history={})
    assert verdict(flags) == "review"


def test_age_uses_history_when_role_never_reposted(example_settings):
    hist = {"first_seen": "2026-07-01T00:00:00+00:00", "first_published": None, "ats_job_ids": ["1"]}
    assert "GHOST_OLD_POST" in _codes(check_ghost(_p(), hist, {}, example_settings, today=TODAY))


def test_no_date_at_all_is_not_old(example_settings):
    assert check_ghost(_p(posted_at=None), None, {}, example_settings, today=TODAY) == []


def test_reposted_is_review_with_counts(example_settings):
    hist = {"first_seen": "2026-09-10T00:00:00+00:00", "ats_job_ids": ["1", "2", "3"], "times_reposted": 2,
            "sightings": ["2026-07-01", "2026-08-01", "2026-09-10"]}
    flags = check_ghost(_p(), hist, {}, example_settings, today=TODAY)
    assert _codes(flags, "review") == {"GHOST_REPOSTED"} and "3" in flags[0].detail


def test_edits_to_same_requisition_are_not_reposts(example_settings):
    hist = {"first_seen": "2026-09-10T00:00:00+00:00", "ats_job_ids": ["1"], "times_edited": 5,
            "sightings": ["2026-09-10"]}
    assert check_ghost(_p(), hist, {}, example_settings, today=TODAY) == []


def test_old_reposts_outside_window_do_not_count(example_settings):
    hist = {"first_seen": "2026-09-10T00:00:00+00:00", "ats_job_ids": ["1", "2", "3"],
            "sightings": ["2025-01-01", "2025-02-01", "2026-09-10"]}
    assert "GHOST_REPOSTED" not in _codes(check_ghost(_p(), hist, {}, example_settings, today=TODAY))


def test_aggregator_only_is_review(example_settings):
    flags = check_ghost(_p(raw={"source": "jobright"}), None, {}, example_settings, today=TODAY)
    assert _codes(flags, "review") == {"GHOST_AGGREGATOR_ONLY"}
    p2 = _p(raw={"source": "jobright", "resolved_from": "https://jobright.ai/j/1"})
    assert check_ghost(p2, None, {}, example_settings, today=TODAY) == []


@pytest.mark.parametrize("scope,level", [
    ("company-wide", "review"),
    ("engineering", "review"),       # matches the role's department/title
    ("New York", "review"),          # matches the location
    ("sales; EMEA", "info"),         # current but does not cover this role
])
def test_freeze_needs_current_evidence_covering_the_role(example_settings, scope, level):
    sig = {"nimbus": {"kind": "freeze", "date": "2026-08-01", "scope": scope, "source_url": "https://news/x"}}
    flags = check_ghost(_p(departments=["Engineering"]), None, sig, example_settings, today=TODAY)
    assert {f.level for f in flags if f.code == "GHOST_HIRING_FREEZE"} == {level}
    assert flags[0].evidence == ("https://news/x",)


def test_old_freeze_or_lifted_freeze_is_ignored(example_settings):
    old = {"nimbus": {"kind": "freeze", "date": "2025-01-01", "scope": "company-wide", "source_url": "u"}}
    lifted = {"nimbus": {"kind": "none", "date": "2026-09-01", "source_url": "u"}}
    assert check_ghost(_p(), None, old, example_settings, today=TODAY) == []
    assert check_ghost(_p(), None, lifted, example_settings, today=TODAY) == []


def test_layoffs_only_lower_confidence(example_settings):
    sig = {"nimbus": {"kind": "layoffs", "date": "2026-06-01", "source_url": "u"}}
    flags = check_ghost(_p(), None, sig, example_settings, today=TODAY)
    assert _codes(flags, "info") == {"GHOST_RECENT_LAYOFFS"} and verdict(flags) == "pass"


def test_dream_company_skip_becomes_review(example_settings):
    p = _p(company="Stripe", posted_at="2026-05-01", last_updated="2026-05-01")
    flags = check_ghost(p, None, {}, example_settings, today=TODAY, company_history={})
    assert verdict(flags) == "review" and "GHOST_STALE_NO_ACTIVITY" in _codes(flags)


@pytest.mark.parametrize("a,b", [
    (("Software Engineer, New Grad (2026)", "New York, NY"), ("Software Engineer - New Grad", "New York, NY")),
    (("Software Engineer II R-12345", "NYC"), ("Software Engineer II", "NYC")),
])
def test_history_key_normalizes(a, b):
    assert history_key("Acme", *a) == history_key("Acme, Inc.", *b)


def test_history_key_distinguishes_roles():
    assert history_key("Acme", "Software Engineer", "NY") != history_key("Acme", "Data Engineer", "NY")


def test_load_signals_merges_config_over_data(example_settings, tmp_path):
    import json

    f = tmp_path / "company_signals.json"
    f.write_text(json.dumps({"nimbus": {"kind": "layoffs", "date": "2026-06-01", "source_url": "a"}}))
    example_settings.companies["hiring_signals"] = [{"company": "Nimbus", "kind": "none", "date": "2026-09-01"}]
    assert load_signals(example_settings, f)["nimbus"]["kind"] == "none"
