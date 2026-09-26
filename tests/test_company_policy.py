"""careeros.company_policy: posting close dates, per-company caps, rejection cooldown with the deadline
exception, deadline clusters, the gate, and the recruiter transparency note. Pure: records in, dicts out."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from careeros.company_policy import (
    JobRecord,
    Policy,
    gate,
    order_jobs,
    parse_deadline_text,
    posting_closes_at,
    rank_candidates,
    slots,
    transparency_note,
)
from careeros.config import ConfigError, _check_shapes
from careeros.models import Posting

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 26)


def d(n: int) -> date:
    """TODAY + n days."""
    return TODAY + timedelta(days=n)


def rec(job_id: str, status: str = "scored", fit: int | None = 80, category: str | None = "swe_backend",
        company: str = "Acme", title: str | None = None, **kw) -> JobRecord:
    kw.setdefault("decision", "prepare" if status in ("found", "scored") else None)
    return JobRecord(job_id=job_id, company=company, title=title or f"Role {job_id}", status=status, fit=fit,
                     category=category, **kw)


@pytest.fixture
def policy(settings) -> Policy:
    return Policy.from_settings(settings)


def posting(text: str = "", published: str | None = "2026-09-20", raw: dict | None = None, ats="greenhouse"):
    return Posting(company="Acme", title="Software Engineer", ats=ats, ats_job_id="1", description_text=text,
                   first_published=published, posted_at=published, raw=raw or {})


# --- posting_closes_at: structured ATS fields ---------------------------------------------------------

def test_greenhouse_application_deadline_field():
    p = posting(raw={"application_deadline": "2026-10-16T23:59:00-04:00"})
    assert posting_closes_at(p) == date(2026, 10, 16)


def test_greenhouse_custom_metadata_deadline():
    p = posting(raw={"metadata": {"Employment Type": "Full-time", "Application Deadline": "2026-11-01"}})
    assert posting_closes_at(p) == date(2026, 11, 1)


def test_structured_field_beats_text():
    p = posting("Application deadline: December 1, 2026", raw={"application_deadline": "2026-10-02T09:00:00Z"})
    assert posting_closes_at(p) == date(2026, 10, 2)


def test_bad_structured_value_falls_back_to_text():
    p = posting("Apply by October 9, 2026.", raw={"application_deadline": "soon"})
    assert posting_closes_at(p) == date(2026, 10, 9)


def test_stored_closes_at_is_used():
    p = posting("Apply by October 9, 2026.")
    p.closes_at = "2026-10-01"
    assert posting_closes_at(p) == date(2026, 10, 1)


# --- posting_closes_at: description text --------------------------------------------------------------

@pytest.mark.parametrize("text,want", [
    ("Application Deadline: December 16, 2026", date(2026, 12, 16)),
    ("The application deadline for this position is Oct 16, 2026.", date(2026, 10, 16)),
    ("Applications close at 17:00 CET on 19th October", date(2026, 10, 19)),
    ("Key Dates  Applications Close: Sunday November 1st 2026  Eligibility", date(2026, 11, 1)),
    ("Applications open: 1 September 2026  Applications close:  30 September 2026", date(2026, 9, 30)),
    ("Please apply by 10/03/2026 to be considered.", date(2026, 10, 3)),
    ("Applications will be accepted no later than 2026-11-30.", date(2026, 11, 30)),
    ("Closing date: 14 Nov 2026", date(2026, 11, 14)),
    ("Deadline: Oct. 5", date(2026, 10, 5)),
    ("We are accepting applications until November 2, 2026.", date(2026, 11, 2)),
])
def test_text_deadlines(text, want):
    assert posting_closes_at(posting(text)) == want


@pytest.mark.parametrize("text", [
    "",
    "Deadline to apply: None. Applications will be reviewed on a rolling basis. Start June 1, 2027.",
    "Able to work under pressure with tight deadlines. Start date: January 5, 2027.",
    "Offer Deadline  In an effort to build more transparency, we share our offer timelines.",
    "There is no set application deadline for this position.",
    "You must be able to start no later than June 1, 2027.",
    "Application deadline: February 30, 2026",
    "Graduating between December 2025 and June 2026.",
])
def test_text_without_a_deadline(text):
    assert posting_closes_at(posting(text)) is None


def test_year_inferred_from_posting_date_rolls_over_new_year():
    assert posting_closes_at(posting("Apply by January 15.", published="2026-12-01")) == date(2027, 1, 15)
    assert posting_closes_at(posting("Apply by December 15.", published="2026-12-01")) == date(2026, 12, 15)


def test_parse_deadline_text_reference_date():
    assert parse_deadline_text("apply by March 3", ref=date(2026, 2, 1)) == date(2026, 3, 3)
    assert parse_deadline_text("nothing here", ref=TODAY) is None


# --- config -------------------------------------------------------------------------------------------

def test_policy_defaults_from_example(policy):
    assert policy.cap_for("Acme") == (2, 90)
    assert policy.cooldown_days == 30 and policy.cluster_days == 7
    assert policy.is_similar("swe_backend") and policy.is_similar("ml_engineering")
    assert not policy.is_similar("product_manager") and not policy.is_similar(None) and not policy.is_similar("other")


def test_company_caps_override_and_aliases(settings):
    settings.companies["company_caps"] = {"Big Corp Inc": {"max": 3, "window_days": 30, "aliases": ["BigCo"]}}
    p = Policy.from_settings(settings)
    assert p.cap_for("big corp") == (3, 30)
    assert p.cap_for("BigCo") == (3, 30)
    assert p.company_key("BigCo") == p.company_key("Big Corp, Inc.")
    assert p.cap_for("Acme") == (2, 90)


def test_company_cap_window_defaults_to_90(settings):
    settings.companies["company_caps"] = {"Acme": {"max": 1}}
    assert Policy.from_settings(settings).cap_for("Acme") == (1, 90)


def test_volume_defaults_when_missing(settings):
    settings.targets.pop("volume", None)
    p = Policy.from_settings(settings)
    assert p.cap_for("x") == (2, 90) and p.cooldown_days == 30 and p.cluster_days == 7


@pytest.mark.parametrize("caps,msg", [
    ([{"Acme": 3}], "company_caps must be a mapping"),
    ({"Acme": 3}, r"company_caps\.Acme must be a mapping"),
    ({"Acme": {"max": "three"}}, r"company_caps\.Acme\.max must be a whole number >= 1"),
    ({"Acme": {"max": 0}}, r"company_caps\.Acme\.max must be a whole number >= 1"),
    ({"Acme": {"max": True}}, r"company_caps\.Acme\.max must be a whole number >= 1"),
    ({"Acme": {"max": 2, "window_days": 0}}, r"window_days must be a whole number >= 1"),
    ({"Acme": {"max": 2, "per_days": 30}}, "unknown key 'per_days'"),
    ({"Acme": {"max": 2, "aliases": "Acme Labs"}}, "aliases must be a list"),
])
def test_bad_company_caps_raise(caps, msg):
    with pytest.raises(ConfigError, match=msg):
        _check_shapes({"companies": {"company_caps": caps}, "targets": {}})


@pytest.mark.parametrize("volume,msg", [
    ([1, 2], "volume must be a mapping"),
    ({"max_per_company_per_90_days": 0}, "max_per_company_per_90_days must be a whole number >= 1"),
    ({"same_company_cooldown_days": -1}, "same_company_cooldown_days must be a whole number >= 0"),
    ({"deadline_cluster_days": "a week"}, "deadline_cluster_days must be a whole number >= 0"),
])
def test_bad_volume_raises(volume, msg):
    with pytest.raises(ConfigError, match=msg):
        _check_shapes({"targets": {"volume": volume}, "companies": {}})


def test_valid_shapes_pass():
    _check_shapes({"targets": {"volume": {"max_per_company_per_90_days": 2, "deadline_cluster_days": 0}},
                   "companies": {"company_caps": {"Acme": {"max": 3, "window_days": 30, "aliases": ["A"]}}}})


# --- slots ------------------------------------------------------------------------------------------

def test_slots_count_submitted_in_window_and_reservations(policy):
    records = [
        rec("a1", "applied", date_applied=d(-10)),
        rec("a2", "interview", date_applied=d(-100)),          # outside the 90-day window
        rec("a3", "rejected", date_applied=d(-20), rejected_at=d(-40)),  # submitted in window: counts
        rec("q1", "queued"),
        rec("x1", "applied", company="Other Co", date_applied=d(-1)),
        rec("s1", "scored"),                                   # a candidate, not a reservation
    ]
    got = slots("ACME, Inc.", records=records, policy=policy, today=TODAY)
    assert (got["submitted"], got["reserved"], got["used"], got["allowed"], got["remaining"]) == (2, 1, 3, 2, 0)
    assert got["window_days"] == 90


def test_slots_active_status_without_date_still_counts(policy):
    got = slots("Acme", records=[rec("a1", "screening")], policy=policy, today=TODAY)
    assert got["submitted"] == 1 and got["remaining"] == 1


def test_slots_empty_company(policy):
    got = slots("Nobody", records=[], policy=policy, today=TODAY)
    assert (got["used"], got["allowed"], got["remaining"]) == (0, 2, 2)


def test_slots_use_override(settings):
    settings.companies["company_caps"] = {"Acme": {"max": 3, "window_days": 30}}
    p = Policy.from_settings(settings)
    records = [rec("a1", "applied", date_applied=d(-10)), rec("a2", "applied", date_applied=d(-45))]
    got = slots("Acme", records=records, policy=p, today=TODAY)
    assert (got["submitted"], got["allowed"], got["remaining"], got["window_days"]) == (1, 3, 2, 30)


# --- rank_candidates / cap ------------------------------------------------------------------------------

def test_rank_selects_top_fit_up_to_remaining(policy):
    records = [rec("a1", "applied", date_applied=d(-5)),
               rec("c1", fit=75), rec("c2", fit=91), rec("c3", fit=88, category="data_engineering")]
    ranked = {r["job_id"]: r for r in rank_candidates("Acme", records=records, policy=policy, today=TODAY)}
    assert ranked["c2"]["selected"] and ranked["c2"]["allowed"] and ranked["c2"]["reason"] == "ok"
    for j in ("c1", "c3"):
        assert not ranked[j]["allowed"] and ranked[j]["reason"] == "company_cap"
    order = [r["job_id"] for r in rank_candidates("Acme", records=records, policy=policy, today=TODAY)]
    assert order == ["c2", "c3", "c1"]


def test_rank_excludes_unrelated_and_nonprepare(policy):
    records = [rec("pm", category="product_manager", fit=99), rec("low", "skipped", decision="skip",
               skip_reason="below_min_fit", fit=50), rec("ok", fit=70), rec("unk", category=None, fit=None)]
    ranked = {r["job_id"]: r for r in rank_candidates("Acme", records=records, policy=policy, today=TODAY)}
    assert "low" not in ranked  # skipped for its own reasons: not competing for a slot
    assert ranked["pm"]["reason"] == "not_similar" and not ranked["pm"]["allowed"]
    assert ranked["ok"]["allowed"]


def test_reserved_jobs_keep_their_slots(policy):
    records = [rec("q1", "queued", fit=70), rec("q2", "prepared", fit=72), rec("c1", fit=99)]
    ranked = {r["job_id"]: r for r in rank_candidates("Acme", records=records, policy=policy, today=TODAY)}
    assert ranked["q1"]["allowed"] and ranked["q2"]["allowed"]
    assert ranked["c1"]["reason"] == "company_cap"


def test_deferred_jobs_compete_again(policy):
    records = [rec("c1", "skipped", decision="skip", skip_reason="company_cap", fit=90)]
    ranked = rank_candidates("Acme", records=records, policy=policy, today=TODAY)
    assert ranked[0]["job_id"] == "c1" and ranked[0]["allowed"]


def test_closed_posting_is_blocked(policy):
    ranked = rank_candidates("Acme", records=[rec("c1", closes_at=d(-1))], policy=policy, today=TODAY)
    assert ranked[0]["reason"] == "closed" and not ranked[0]["allowed"]


# --- cooldown with the deadline exception ----------------------------------------------------------------

def _rejected(days_ago: int = 5) -> JobRecord:
    return rec("r1", "rejected", date_applied=d(-100), rejected_at=d(-days_ago))  # applied outside the window


def test_cooldown_blocks_until_it_ends(policy):
    records = [_rejected(5), rec("c1", fit=90)]
    g = gate("c1", records=records, policy=policy, today=TODAY)
    assert not g["allowed"] and g["reason"] == "cooldown" and g["until"] == d(25).isoformat()
    assert g["urgent"] is False


def test_cooldown_over_after_its_days(policy):
    records = [_rejected(31), rec("c1", fit=90)]
    assert gate("c1", records=records, policy=policy, today=TODAY)["allowed"]


def test_deadline_before_cooldown_end_applies_now_and_is_urgent(policy):
    records = [_rejected(5), rec("c1", fit=90, closes_at=d(10))]
    g = gate("c1", records=records, policy=policy, today=TODAY)
    assert g["allowed"] and g["urgent"] and g["reason"] == "ok" and g["closes_at"] == d(10).isoformat()
    assert "closes " + d(10).isoformat() in g["action_note"]


def test_deadline_after_cooldown_end_waits(policy):
    records = [_rejected(5), rec("c1", fit=90, closes_at=d(60))]
    g = gate("c1", records=records, policy=policy, today=TODAY)
    assert not g["allowed"] and g["reason"] == "cooldown"


def test_unknown_close_date_waits(policy):
    g = gate("c1", records=[_rejected(5), rec("c1", closes_at=None)], policy=policy, today=TODAY)
    assert g["reason"] == "cooldown"


def test_deadline_exception_still_capped(policy):
    records = [_rejected(5), rec("a1", "applied", date_applied=d(-3)), rec("a2", "applied", date_applied=d(-4)),
               rec("c1", fit=90, closes_at=d(3))]
    g = gate("c1", records=records, policy=policy, today=TODAY)
    assert not g["allowed"] and g["reason"] == "company_cap"


def test_cooldown_ranks_deadline_jobs_ahead_of_higher_fit(policy):
    # one slot left: the job that would miss its deadline takes it over the higher-fit job that can wait
    records = [_rejected(5), rec("a1", "applied", date_applied=d(-3)),
               rec("hi", fit=95), rec("due", fit=80, closes_at=d(7))]
    ranked = {r["job_id"]: r for r in rank_candidates("Acme", records=records, policy=policy, today=TODAY)}
    assert ranked["due"]["allowed"] and ranked["due"]["urgent"]
    assert ranked["hi"]["reason"] == "company_cap"


def test_reserved_job_blocked_by_new_rejection(policy):
    g = gate("q1", records=[_rejected(2), rec("q1", "queued")], policy=policy, today=TODAY)
    assert not g["allowed"] and g["reason"] == "cooldown"


def test_cooldown_zero_disables(settings):
    settings.targets["volume"]["same_company_cooldown_days"] = 0
    p = Policy.from_settings(settings)
    assert gate("c1", records=[_rejected(0), rec("c1")], policy=p, today=TODAY)["allowed"]


# --- deadline clusters --------------------------------------------------------------------------------

def test_cluster_marks_selected_similar_roles_urgent(policy):
    records = [rec("c1", fit=90, closes_at=d(20)), rec("c2", fit=85, closes_at=d(25), category="swe_platform")]
    ranked = {r["job_id"]: r for r in rank_candidates("Acme", records=records, policy=policy, today=TODAY)}
    assert ranked["c1"]["urgent"] and ranked["c2"]["urgent"]


def test_cluster_needs_dates_within_window(policy):
    records = [rec("c1", fit=90, closes_at=d(20)), rec("c2", fit=85, closes_at=d(40))]
    ranked = rank_candidates("Acme", records=records, policy=policy, today=TODAY)
    assert not any(r["urgent"] for r in ranked)


def test_cluster_overrides_cooldown(policy):
    # both close after the cooldown ends, but close together: apply to both now
    records = [_rejected(5), rec("c1", fit=90, closes_at=d(40)), rec("c2", fit=85, closes_at=d(44))]
    ranked = {r["job_id"]: r for r in rank_candidates("Acme", records=records, policy=policy, today=TODAY)}
    assert ranked["c1"]["allowed"] and ranked["c2"]["allowed"]
    assert ranked["c1"]["urgent"] and ranked["c2"]["urgent"]


def test_cluster_only_among_selected(policy):
    # c3 is over the cap: it neither joins the cluster nor makes c1 urgent
    records = [rec("a1", "applied", date_applied=d(-2)),
               rec("c1", fit=90, closes_at=d(20)), rec("c3", fit=60, closes_at=d(21))]
    ranked = {r["job_id"]: r for r in rank_candidates("Acme", records=records, policy=policy, today=TODAY)}
    assert ranked["c1"]["allowed"] and not ranked["c1"]["urgent"]
    assert ranked["c3"]["reason"] == "company_cap" and not ranked["c3"]["urgent"]


def test_cluster_includes_reserved(policy):
    records = [rec("q1", "queued", closes_at=d(15)), rec("c1", fit=70, closes_at=d(12))]
    g = gate("c1", records=records, policy=policy, today=TODAY)
    assert g["allowed"] and g["urgent"]


# --- gate -------------------------------------------------------------------------------------------------

def test_gate_shape(policy):
    g = gate("c1", records=[rec("c1", fit=88)], policy=policy, today=TODAY)
    assert set(g) >= {"job_id", "company", "allowed", "reason", "urgent", "closes_at", "until", "slots",
                      "action_note", "detail"}
    assert g["allowed"] and g["reason"] == "ok" and g["slots"]["remaining"] == 2 and g["action_note"] == ""


def test_gate_candidate_even_if_decision_missing(policy):
    # the gate is asked about this job: it competes even before score.json has a final decision
    g = gate("c1", records=[rec("c1", "found", decision=None)], policy=policy, today=TODAY)
    assert g["allowed"]


def test_gate_already_applied(policy):
    g = gate("a1", records=[rec("a1", "applied", date_applied=d(-1))], policy=policy, today=TODAY)
    assert not g["allowed"] and g["reason"] == "already_applied"


def test_gate_unscored(policy):
    g = gate("c1", records=[rec("c1", "found", fit=None, category=None, decision=None)], policy=policy, today=TODAY)
    assert not g["allowed"] and g["reason"] == "unscored"


def test_gate_unknown_job(policy):
    with pytest.raises(KeyError):
        gate("nope", records=[], policy=policy, today=TODAY)


def test_gate_detail_mentions_slots(policy):
    records = [rec("a1", "applied", date_applied=d(-1)), rec("a2", "applied", date_applied=d(-2)), rec("c1")]
    g = gate("c1", records=records, policy=policy, today=TODAY)
    assert "2/2" in g["detail"] and "90 days" in g["detail"]


# --- ordering ---------------------------------------------------------------------------------------------

def test_order_jobs_urgent_first_then_close_date_then_fit(policy):
    records = [rec("q1", "queued", fit=95), rec("q2", "queued", fit=70, company="B Co", closes_at=d(30)),
               rec("u1", "queued", fit=60, company="C Co", closes_at=d(9)),
               rec("u2", "queued", fit=65, company="C Co", closes_at=d(8))]
    jobs = [{"job_id": r.job_id, "fit": r.fit} for r in records]
    out = order_jobs(jobs, records=records, policy=policy, today=TODAY)
    assert [j["job_id"] for j in out] == ["u2", "u1", "q2", "q1"]
    assert out[0]["urgent"] is True and out[0]["closes_at"] == d(8).isoformat()
    assert out[-1]["urgent"] is False and out[-1]["closes_at"] is None


# --- transparency note ----------------------------------------------------------------------------------

def test_transparency_note_lists_other_active(policy):
    records = [rec("i1", "interview", title="Backend Engineer"), rec("a1", "applied", title="Data Engineer"),
               rec("q1", "queued", title="Platform Engineer"), rec("r1", "rejected", title="Old Role"),
               rec("s1", "scored", title="Scored Only"), rec("o1", "applied", company="Other Co")]
    note = transparency_note("Acme", records=records, exclude_job="i1")
    assert note == ("Also active at Acme: Data Engineer (applied), Platform Engineer (queued) "
                    "— mention these to the recruiter.")


def test_transparency_note_empty_when_nothing_else(policy):
    assert transparency_note("Acme", records=[rec("i1", "interview")], exclude_job="i1") == ""
