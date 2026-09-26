"""Daily apply cap (code, not skill prose), auto-submit policy (config only: runs never apply), retry bookkeeping."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from careeros.company_policy import JobRecord
from careeros.config import ConfigError
from careeros.runs.policy import (
    AutoSubmitPolicy,
    applied_on,
    auto_submit_decision,
    cap_status,
    daily_cap,
    load_retry_config,
)

pytestmark = pytest.mark.unit


def targets(max_day=15, mult=None):
    v = {"max_applications_per_day": max_day}
    if mult is not None:
        v["season_multiplier"] = mult
    return {"volume": v}


@pytest.mark.parametrize("day,want", [(date(2026, 9, 26), 30), (date(2026, 10, 2), 22), (date(2026, 7, 1), 15)])
def test_daily_cap_applies_the_season_multiplier_and_floors(day, want):
    assert daily_cap(targets(15, {"9": 2.0, "10": 1.5}), day) == want


def test_daily_cap_int_month_keys_and_defaults():
    assert daily_cap(targets(10, {9: 3}), date(2026, 9, 1)) == 30
    assert daily_cap({}, date(2026, 9, 1)) == 15  # volume.max_applications_per_day default


@pytest.mark.parametrize("bad", [
    {"volume": {"max_applications_per_day": 0}},
    {"volume": {"max_applications_per_day": "ten"}},
    {"volume": {"max_applications_per_day": 5, "season_multiplier": {"13": 2}}},
    {"volume": {"max_applications_per_day": 5, "season_multiplier": {"9": -1}}},
    {"volume": {"max_applications_per_day": 5, "season_multiplier": [2]}},
])
def test_daily_cap_rejects_bad_config(bad):
    with pytest.raises(ConfigError):
        daily_cap(bad, date(2026, 9, 1))


def rec(jid, applied=None, status="applied"):
    return JobRecord(job_id=jid, company="Acme", title="SWE", status=status, date_applied=applied)


def test_applied_on_counts_calendar_day_only():
    today = date(2026, 9, 26)
    recs = [rec("a", today), rec("b", today), rec("c", date(2026, 9, 25)), rec("d", None, "queued")]
    assert applied_on(recs, today) == 2


def test_cap_status():
    today = date(2026, 9, 26)
    st = cap_status(targets(2, {}), [rec("a", today)], today)
    assert st == {"date": "2026-09-26", "cap": 2, "applied": 1, "remaining": 1, "multiplier": 1.0,
                  "base": 2, "reached": False}
    assert cap_status(targets(1, {}), [rec("a", today)], today)["reached"] is True


# --- auto-submit policy: config shape + a pure decision; nothing calls it to submit yet -----------------------

def pol(**kw) -> AutoSubmitPolicy:
    return AutoSubmitPolicy.from_config({"auto_submit": kw})


def job(**kw):
    base = {"tier": "C", "fit": 75, "dream": False, "category": "swe_backend", "safety_pass": True}
    return {**base, **kw}


def test_disabled_by_default():
    p = AutoSubmitPolicy.from_config({})
    assert p.enabled is False
    assert auto_submit_decision(job(), p) == (False, "auto_submit disabled")


def test_allow_and_manual_rules():
    p = pol(enabled=True, allow=["tier_c", "tier_b"], manual=["tier_a", "fit_gte_90"])
    assert auto_submit_decision(job(tier="C", fit=75), p) == (True, "allowed: tier_c")
    assert auto_submit_decision(job(tier="B", fit=92), p) == (False, "manual: fit_gte_90")
    assert auto_submit_decision(job(tier=None, fit=75), p)[0] is False


def test_tier_a_is_never_auto_even_if_allowed():
    p = pol(enabled=True, allow=["tier_a"], manual=[])
    assert auto_submit_decision(job(tier="A"), p) == (False, "manual: tier_a (never auto-submitted)")


def test_safety_must_pass():
    p = pol(enabled=True, allow=["tier_c"], manual=[])
    assert auto_submit_decision(job(safety_pass=False), p) == (False, "safety verdict is not pass")


@pytest.mark.parametrize("token,j,hit", [
    ("fit_lt_70", job(fit=65), True), ("fit_lt_70", job(fit=70), False),
    ("dream", job(dream=True), True), ("category_swe_backend", job(), True), ("category_data", job(), False),
])
def test_rule_tokens(token, j, hit):
    p = pol(enabled=True, allow=[token], manual=[])
    assert auto_submit_decision(j, p)[0] is hit


@pytest.mark.parametrize("bad", [
    {"auto_submit": []}, {"auto_submit": {"enabled": "yes"}}, {"auto_submit": {"allow": ["tier_d"]}},
    {"auto_submit": {"manual": ["fit_gte_x"]}}, {"auto_submit": {"bogus": 1}},
])
def test_auto_submit_config_is_validated(bad):
    with pytest.raises(ConfigError):
        AutoSubmitPolicy.from_config(bad)


def test_retry_config_defaults_and_validation():
    assert load_retry_config({}) == {"max_attempts": 2, "action_item": True}
    assert load_retry_config({"retry": {"max_attempts": 3}})["max_attempts"] == 3
    with pytest.raises(ConfigError):
        load_retry_config({"retry": {"max_attempts": 0}})
    with pytest.raises(ConfigError):
        load_retry_config({"retry": {"action_item": "y"}})


def test_example_config_documents_the_defaults():
    import yaml
    from conftest import EXAMPLE_REPO

    from careeros.runs.policy import DEFAULT_AUTO_SUBMIT, DEFAULT_RETRY, load_prepare_config

    runs = yaml.safe_load((EXAMPLE_REPO / "config" / "pipeline.yaml").read_text())["runs"]
    p = AutoSubmitPolicy.from_config(runs)
    assert {"enabled": p.enabled, "allow": p.allow, "manual": p.manual} == DEFAULT_AUTO_SUBMIT
    assert load_retry_config(runs) == DEFAULT_RETRY
    assert load_prepare_config(runs) == load_prepare_config({})


def test_default_manual_rule_is_fit_85_and_configurable():
    from careeros.runs.policy import DEFAULT_AUTO_SUBMIT

    assert DEFAULT_AUTO_SUBMIT["manual"] == ["tier_a", "fit_gte_85"]
    p = pol(enabled=True, allow=["tier_b", "tier_c"])  # manual left at the default
    assert auto_submit_decision(job(tier="B", fit=85), p) == (False, "manual: fit_gte_85")
    assert auto_submit_decision(job(tier="B", fit=84), p) == (True, "allowed: tier_b")
    p2 = pol(enabled=True, allow=["tier_b"], manual=["tier_a", "fit_gte_95"])
    assert auto_submit_decision(job(tier="B", fit=90), p2)[0] is True


def test_daily_cap_stop_defaults_on_and_is_configurable():
    from careeros.runs.policy import load_prepare_config

    assert load_prepare_config({}) == {"stop_at_daily_cap": True}
    assert load_prepare_config({"prepare": {"stop_at_daily_cap": False}}) == {"stop_at_daily_cap": False}
