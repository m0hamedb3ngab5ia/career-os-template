"""Scam / data-harvesting gate: every check yields a reason code, a level (block | review | info) and
evidence; `verdict()` turns a list of flags into Pass / Review / Block."""
from __future__ import annotations

import pytest

from careeros.models import Posting
from careeros.safety.scam import (
    Flag,
    auto_submit_allowed,
    check_form_fields,
    check_posting,
    company_domains,
    company_risk,
    registrable_domain,
    verdict,
)

pytestmark = pytest.mark.unit


def _p(**kw) -> Posting:
    # Stripe is on the example dream list (curated), so only the check under test can flag it.
    base = dict(company="Stripe", title="Software Engineer, New Grad", ats="greenhouse",
                url="https://boards.greenhouse.io/stripe/jobs/1", apply_url="https://boards.greenhouse.io/stripe/jobs/1",
                description_text="Build payments infrastructure.")
    base.update(kw)
    return Posting(**base)


def _codes(flags: list[Flag], level: str | None = None) -> set[str]:
    return {f.code for f in flags if level is None or f.level == level}


# --- verdict model -------------------------------------------------------------------------------------

@pytest.mark.parametrize("levels,want", [
    ([], "pass"), (["info"], "pass"), (["info", "review"], "review"),
    (["review", "skip"], "skip"), (["skip", "block", "review"], "block"),
])
def test_verdict(levels, want):
    assert verdict([Flag(f"X{i}", lv) for i, lv in enumerate(levels)]) == want


def test_flag_carries_evidence_and_timestamp_and_round_trips():
    f = Flag("SCAM_BRAND_DOMAIN_MISMATCH", "block", "x", evidence=("https://a", "https://b"))
    assert f.at and Flag.from_dict(f.to_dict()) == f
    assert f.to_dict()["evidence"] == ["https://a", "https://b"]


# --- domains ---------------------------------------------------------------------------------------------

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
    assert check_posting(p, example_settings) == []


def test_configured_company_domain_is_allowed(example_settings):
    example_settings.companies["company_domains"] = {"Acme": "acmecorp.io"}
    p = _p(company="Acme", ats="custom", url="https://jobs.acmecorp.io/1", apply_url="https://jobs.acmecorp.io/1")
    assert company_domains(example_settings, "Acme") == {"acmecorp.io"}
    assert check_posting(p, example_settings) == []


def test_unrecognized_apply_domain_is_review_not_block(example_settings):
    p = _p(ats="custom", apply_url="https://apply.smallats.io/stripe/1")
    flags = check_posting(p, example_settings)
    assert _codes(flags) == {"SCAM_APPLY_DOMAIN_UNRECOGNIZED"} and verdict(flags) == "review"


def test_free_email_recruiter_is_review_not_block(example_settings):
    p = _p(description_text="Send your resume to stripe.founder@gmail.com today.")
    flags = check_posting(p, example_settings)
    assert _codes(flags) == {"SCAM_FREE_EMAIL_RECRUITER"} and verdict(flags) == "review"
    assert "stripe.founder@gmail.com" in flags[0].detail


def test_company_email_is_fine(example_settings):
    assert check_posting(_p(description_text="Questions: recruiting@stripe.com"), example_settings) == []


@pytest.mark.parametrize("text", [
    "You will receive a check to deposit and purchase equipment.",
    "A small training fee of $50 is required.",
    "Salary paid in USDT crypto.",
    "Buy your laptop from our vendor; we will reimburse you after the first week.",
    "Please purchase gift cards for onboarding.",
    "Install AnyDesk so our IT team can set up your computer.",
])
def test_payment_and_remote_access_requests_block(example_settings, text):
    flags = check_posting(_p(description_text=text), example_settings)
    assert verdict(flags) == "block", flags


@pytest.mark.parametrize("text,code", [
    ("Interviews are conducted over WhatsApp with our hiring manager.", "SCAM_CHAT_ONLY_INTERVIEW"),
    ("Contact us on Telegram for an interview.", "SCAM_CHAT_ONLY_INTERVIEW"),
    ("No interview required, hired immediately!", "SCAM_NO_INTERVIEW"),
])
def test_suspicious_process_is_review(example_settings, text, code):
    flags = check_posting(_p(description_text=text), example_settings)
    assert _codes(flags) == {code} and verdict(flags) == "review"


@pytest.mark.parametrize("text", [
    "We build crypto custody infrastructure for institutions.",
    "Our fee-free payments API serves millions.",
    "Laptop and equipment provided on day one.",
    "We use TeamViewer-like remote support tooling in our product.",
])
def test_legit_mentions_do_not_trip(example_settings, text):
    assert check_posting(_p(description_text=text), example_settings) == []


def test_salary_far_above_market_is_review(example_settings):
    floor = example_settings.targets["candidate"]["min_base_usd"]
    flags = check_posting(_p(salary_min=floor * 4, salary_max=floor * 5), example_settings)
    assert _codes(flags, "review") == {"SCAM_SALARY_IMPLAUSIBLE"}


# --- registry ----------------------------------------------------------------------------------------------

def test_registry_high_confidence_blocks_medium_reviews(example_settings):
    high = [{"company": "Stripe", "reason": "fake recruiter", "confidence": "high", "state": "active",
             "evidence": ["https://x"]}]
    med = [{**high[0], "confidence": "medium"}]
    f_high = check_posting(_p(), example_settings, registry=high)
    assert _codes(f_high, "block") == {"SCAM_FLAGGED_BEFORE"} and f_high[0].evidence == ("https://x",)
    assert _codes(check_posting(_p(), example_settings, registry=med), "review") == {"SCAM_FLAGGED_BEFORE"}


@pytest.mark.parametrize("entry", [
    {"company": "Stripe", "confidence": "high", "state": "cleared"},
    {"company": "Stripe", "confidence": "high", "state": "active", "expires_at": "2020-01-01T00:00:00+00:00"},
])
def test_cleared_or_expired_registry_entries_are_ignored(example_settings, entry):
    assert check_posting(_p(), example_settings, registry=[entry]) == []


# --- company risk (made-up companies) -----------------------------------------------------------------------

def test_company_risk_levels(example_settings):
    assert company_risk(example_settings, "Stripe") == ("curated", None)
    assert company_risk(example_settings, "Nimbus Quantum")[0] == "unchecked"
    v = [{"company": "Nimbus Quantum", "risk": "medium", "signals": ["website ok"]}]
    assert company_risk(example_settings, "Nimbus Quantum", verified=v)[0] == "medium"


def _nimbus(**kw):
    return _p(company="Nimbus Quantum", url="https://boards.greenhouse.io/nimbusq/jobs/1",
              apply_url="https://boards.greenhouse.io/nimbusq/jobs/1", **kw)


def test_unknown_company_is_review_never_block(example_settings):
    flags = check_posting(_nimbus(), example_settings)
    assert _codes(flags) == {"COMPANY_NOT_YET_CHECKED"} and verdict(flags) == "review"


@pytest.mark.parametrize("risk,code,want", [
    ("low", None, "pass"),
    ("medium", "COMPANY_SPARSE_PUBLIC_FOOTPRINT", "review"),
    ("high", "COMPANY_CONTRADICTIONS", "block"),
])
def test_verified_risk_drives_verdict(example_settings, risk, code, want):
    v = [{"company": "Nimbus Quantum", "risk": risk, "signals": ["a", "b"], "evidence": ["https://nimbusq.com"]}]
    flags = check_posting(_nimbus(), example_settings, verified=v)
    assert verdict(flags) == want and (_codes(flags) == ({code} if code else set()))


def test_lookalike_of_curated_brand_blocks(example_settings):
    p = _p(company="Stripe Talent Recruiting", ats="custom", url="https://talent-hub.net/j/1",
           apply_url="https://talent-hub.net/j/1")
    assert "SCAM_BRAND_DOMAIN_MISMATCH" in _codes(check_posting(p, example_settings), "block")


def test_curated_brand_itself_is_not_lookalike(example_settings):
    assert check_posting(_p(company="Stripe"), example_settings) == []


def test_dream_priority_never_bypasses_fraud(example_settings):
    p = _p(description_text="A small training fee of $50 is required.")  # Stripe is a dream company
    assert verdict(check_posting(p, example_settings)) == "block"


# --- form fields ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("label", [
    "Social Security Number", "SSN", "Date of Birth", "Birth date (MM/DD/YYYY)",
    "Bank account number", "Routing number", "Upload a copy of your passport",
    "Driver's license number", "Mother's maiden name", "National ID number",
])
def test_identity_and_bank_fields_block_before_offer(label):
    flags = check_form_fields([label])
    assert _codes(flags, "block") == {"FIELD_SENSITIVE_PRE_OFFER"} and label in flags[0].detail


def test_identity_fields_allowed_after_offer():
    assert check_form_fields(["Date of Birth", "SSN"], status="offer") == []


@pytest.mark.parametrize("label,code", [
    ("Application fee", "FIELD_PAYMENT"),
    ("Gmail password", "FIELD_CREDENTIALS"),
    ("Security question: your first pet", "FIELD_CREDENTIALS"),
    ("Enter the 6-digit code we texted you", "FIELD_CREDENTIALS"),
    ("AnyDesk ID for remote setup", "FIELD_REMOTE_ACCESS"),
])
def test_payment_credentials_remote_access_always_block(label, code):
    assert _codes(check_form_fields([label], status="offer", page_url="https://quick.xyz/form"), "block") == {code}


def test_ats_account_password_and_code_are_normal():
    labels = ["Create a password", "Confirm password", "Verification code sent to your email"]
    assert check_form_fields(labels, page_url="https://acme.wd5.myworkdayjobs.com/apply") == []


@pytest.mark.parametrize("label", [
    "First name", "Email", "Phone", "LinkedIn profile", "Date available to start", "City",
    "Are you legally authorized to work in the US?", "Will you now or in the future require sponsorship?",
    "Resume/CV",
])
def test_ordinary_and_work_authorization_fields_pass(label):
    assert check_form_fields([label]) == []


# --- auto-submit allowlist -----------------------------------------------------------------------------------

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


def test_levels_are_configurable_per_code(example_settings):
    from careeros.safety.scam import apply_levels

    example_settings.targets.setdefault("safety", {})["levels"] = {
        "SCAM_FREE_EMAIL_RECRUITER": "block", "SCAM_SALARY_IMPLAUSIBLE": "off"}
    floor = example_settings.targets["candidate"]["min_base_usd"]
    p = _p(description_text="Email me at founder@gmail.com", salary_max=floor * 5)
    flags = apply_levels(check_posting(p, example_settings), example_settings)
    assert {(f.code, f.level) for f in flags} == {("SCAM_FREE_EMAIL_RECRUITER", "block")}
