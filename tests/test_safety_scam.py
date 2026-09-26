"""Scam / data-harvesting gate: posting checks, form-field checks, auto-submit allowlist."""
from __future__ import annotations

import pytest

from careeros.models import Posting
from careeros.safety.scam import (
    Flag,
    auto_submit_allowed,
    check_form_fields,
    check_posting,
    company_domains,
    registrable_domain,
)

pytestmark = pytest.mark.unit


def _p(**kw) -> Posting:
    # Stripe is on the example dream list (curated), so only the check under test can flag it.
    base = dict(company="Stripe", title="Software Engineer, New Grad", ats="greenhouse",
                url="https://boards.greenhouse.io/stripe/jobs/1", apply_url="https://boards.greenhouse.io/stripe/jobs/1",
                description_text="Build payments infrastructure.")
    base.update(kw)
    return Posting(**base)


def _codes(flags: list[Flag], severity: str | None = None) -> set[str]:
    return {f.code for f in flags if severity is None or f.severity == severity}


@pytest.mark.parametrize("url,want", [
    ("https://boards.greenhouse.io/acme/jobs/1", "greenhouse.io"),
    ("https://jobs.lever.co/acme/abc", "lever.co"),
    ("https://acme.wd5.myworkdayjobs.com/en-US/x", "myworkdayjobs.com"),
    ("https://careers.acme.co.uk/x", "acme.co.uk"),
    ("acme.com", "acme.com"),
    ("", ""),
])
def test_registrable_domain(url, want):
    assert registrable_domain(url) == want


def test_clean_board_posting_has_no_flags(example_settings):
    assert check_posting(_p(), example_settings) == []


def test_company_own_domain_is_allowed(example_settings):
    p = _p(ats="custom", url="https://careers.stripe.com/jobs/1", apply_url="https://careers.stripe.com/apply/1")
    assert "apply_domain" not in _codes(check_posting(p, example_settings))


def test_configured_company_domain_is_allowed(example_settings):
    example_settings.companies["company_domains"] = {"Acme": "acmecorp.io"}
    p = _p(company="Acme", ats="custom", url="https://jobs.acmecorp.io/1", apply_url="https://jobs.acmecorp.io/1")
    assert company_domains(example_settings, "Acme") == {"acmecorp.io"}
    assert check_posting(p, example_settings) == []


def test_unknown_apply_domain_is_hard(example_settings):
    p = _p(ats="custom", apply_url="https://quick-hire-now.xyz/form")
    assert "apply_domain" in _codes(check_posting(p, example_settings), "hard")


def test_free_email_contact_is_hard(example_settings):
    p = _p(description_text="Send your resume to acme.recruiting.team@gmail.com today.")
    assert "free_email_contact" in _codes(check_posting(p, example_settings), "hard")


def test_company_email_is_fine(example_settings):
    p = _p(description_text="Questions: recruiting@stripe.com")
    assert check_posting(p, example_settings) == []


@pytest.mark.parametrize("text", [
    "Interviews are conducted over WhatsApp with our hiring manager.",
    "Contact us on Telegram for an interview.",
    "You will receive a check to deposit and purchase equipment.",
    "A small training fee of $50 is required.",
    "Salary paid in USDT crypto.",
    "Buy your laptop and software; we will reimburse you after the first week.",
])
def test_scam_phrases_are_hard(example_settings, text):
    assert "scam_phrase" in _codes(check_posting(_p(description_text=text), example_settings), "hard")


@pytest.mark.parametrize("text", [
    "We build crypto custody infrastructure for institutions.",
    "Our fee-free payments API serves millions.",
    "Laptop and equipment provided on day one.",
])
def test_legit_mentions_do_not_trip(example_settings, text):
    assert check_posting(_p(description_text=text), example_settings) == []


def test_salary_far_above_market_is_soft(example_settings):
    floor = example_settings.targets["candidate"]["min_base_usd"]
    flags = check_posting(_p(salary_min=floor * 4, salary_max=floor * 5), example_settings)
    assert _codes(flags, "soft") == {"salary_implausible"} and not _codes(flags, "hard")


def test_registry_hit_is_hard(example_settings):
    reg = [{"company": "Stripe", "domain": "", "reason": "fake recruiter"}]
    assert "registry" in _codes(check_posting(_p(), example_settings, registry=reg), "hard")


@pytest.mark.parametrize("label", [
    "Social Security Number", "SSN", "Date of Birth", "Birth date (MM/DD/YYYY)",
    "Bank account number", "Routing number", "Upload a copy of your passport",
    "Driver's license number", "Mother's maiden name", "Application fee", "National ID number",
])
def test_sensitive_fields_are_hard(label):
    flags = check_form_fields([label])
    assert _codes(flags, "hard") == {"sensitive_field"} and label in flags[0].detail


@pytest.mark.parametrize("label", [
    "First name", "Email", "Phone", "LinkedIn profile", "Date available to start",
    "City", "Are you legally authorized to work in the US?", "Resume/CV",
])
def test_ordinary_fields_pass(label):
    assert check_form_fields([label]) == []


def test_identity_fields_allowed_after_offer_but_fees_never():
    assert check_form_fields(["Date of Birth", "SSN"], status="offer") == []
    assert _codes(check_form_fields(["Training fee"], status="offer")) == {"sensitive_field"}


def test_auto_submit_allowed_on_board_posting(example_settings):
    assert auto_submit_allowed(_p(), example_settings) == (True, "")


@pytest.mark.parametrize("kw,reason", [
    ({"ats": "workday", "apply_url": "https://acme.wd5.myworkdayjobs.com/x"}, "ats"),
    ({"apply_url": "https://acme-careers.xyz/apply"}, "domain"),
    ({"raw": {"source": "jobright"}}, "aggregator"),
])
def test_auto_submit_refused(example_settings, kw, reason):
    ok, why = auto_submit_allowed(_p(**kw), example_settings)
    assert not ok and reason in why


def test_aggregator_posting_resolved_to_company_board_is_allowed(example_settings):
    p = _p(raw={"source": "jobright", "resolved_from": "https://jobright.ai/jobs/9"})
    assert auto_submit_allowed(p, example_settings) == (True, "")


def test_flag_round_trips():
    f = Flag("apply_domain", "hard", "x")
    assert Flag.from_dict(f.to_dict()) == f


# --- made-up / look-alike companies -------------------------------------------------------------------

def test_curated_company_is_trusted(example_settings):
    from careeros.safety.scam import company_trust

    board_co = example_settings.boards[0]["company"]
    assert company_trust(example_settings, board_co) == "curated"
    assert company_trust(example_settings, "Totally Unknown Startup") == "unverified"
    assert company_trust(example_settings, "Totally Unknown Startup", verified=[{"company": "Totally Unknown Startup"}]) \
        == "verified"


def test_unknown_company_is_soft_flagged_and_blocks_auto(example_settings):
    p = _p(company="Nimbus Quantum", url="https://boards.greenhouse.io/nimbusq/jobs/1",
           apply_url="https://boards.greenhouse.io/nimbusq/jobs/1")
    flags = check_posting(p, example_settings)
    assert _codes(flags, "soft") == {"company_unverified"} and not _codes(flags, "hard")


def test_lookalike_of_curated_company_is_hard(example_settings):
    brand = example_settings.boards[0]["company"]
    p = _p(company=f"{brand} Talent Recruiting", ats="custom", url="https://talent-hub.net/j/1",
           apply_url="https://talent-hub.net/j/1")
    assert "lookalike_company" in _codes(check_posting(p, example_settings), "hard")


def test_curated_brand_itself_is_not_lookalike(example_settings):
    brand = example_settings.boards[0]["company"]
    assert "lookalike_company" not in _codes(check_posting(_p(company=brand), example_settings))
