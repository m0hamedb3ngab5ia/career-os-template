"""Yield model priors (MODEL.md §2, §4) and the referral term in prepare ranking."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from careeros.runs.ranking import Candidate, rank
from careeros.yield_model import p_offer, referral_lift, referral_lifts

pytestmark = pytest.mark.unit
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


def test_p_offer_priors():
    assert p_offer("cold", 70) == pytest.approx(0.0018)
    assert p_offer("referral", 40) == pytest.approx(0.02)          # referrer already filtered fit
    assert p_offer("cold", 70, stale=True) == pytest.approx(0.0018 * 0.7)
    assert p_offer("cold", 100) > p_offer("cold", 70) > p_offer("cold", 40)


def test_referral_lift_scales_with_company_strength():
    normal = referral_lift(70)
    assert normal == pytest.approx(1 + 0.1 * (0.02 - 0.0018) / 0.0018)
    assert 1 < referral_lift(70, strength="weak") < normal < referral_lift(70, strength="strong")
    assert referral_lift(70, tie="warm") > normal


def _w(**kw):
    return {"fresh_hours": 24, "stale_days": 30, "freshness_weight": 0, "dream_bonus": 0, "deadline_bonus": 0,
            "deadline_days": 7, "fit_weight": 0, "retry_bonus": 0, "referral_weight": 15, **kw}


def test_rank_puts_a_referral_job_first_and_says_why():
    a = Candidate("a", "Acme", "SWE", "scored", None, fit=70, referral_lift=2.0)
    b = Candidate("b", "Beta", "SWE", "scored", None, fit=70)
    out = rank([b, a], _w(), NOW, "prepare")
    assert [r["job_id"] for r in out] == ["a", "b"] and "referral possible" in out[0]["why"] and "(+15)" in out[0]["why"]
    assert rank([a], _w(), NOW, "score")[0]["score"] == 0  # prepare only


def test_referral_lifts_from_network_and_company_strength(settings):
    from careeros.network import network_path

    p = network_path(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"connections": [{"name": "X", "company": "Acme Inc", "position": "SWE"},
                                             {"name": "Y", "company": "Weakco", "position": "PM"}]}))
    settings.companies["referral_strength"] = {"Weakco": "weak"}
    lifts = referral_lifts(settings, [("j1", "Acme", 70, False), ("j2", "Weakco", 70, False), ("j3", "Nobody", 70, False)])
    assert set(lifts) == {"j1", "j2"} and lifts["j1"] > lifts["j2"] > 1


def test_bad_referral_strength_is_config_error(tmp_path):
    import shutil

    import yaml
    from conftest import EXAMPLE_REPO

    from careeros.config import ConfigError, Settings

    root = tmp_path / "r"
    shutil.copytree(EXAMPLE_REPO / "config", root / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", root / "profile")
    p = root / "config" / "companies.yaml"
    d = yaml.safe_load(p.read_text())
    d["referral_strength"] = {"Acme": "great"}
    p.write_text(yaml.safe_dump(d))
    with pytest.raises(ConfigError, match="referral_strength"):
        Settings.load(root)


@pytest.mark.parametrize("bad", [{1: "weak"}, {"": "weak"}])
def test_referral_strength_keys_must_be_names(tmp_path, bad):
    import shutil

    import yaml
    from conftest import EXAMPLE_REPO

    from careeros.config import ConfigError, Settings

    root = tmp_path / "r"
    shutil.copytree(EXAMPLE_REPO / "config", root / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", root / "profile")
    p = root / "config" / "companies.yaml"
    d = yaml.safe_load(p.read_text())
    d["referral_strength"] = bad
    p.write_text(yaml.safe_dump(d))
    with pytest.raises(ConfigError, match="referral_strength"):
        Settings.load(root)


def test_priors_come_from_config(settings):
    settings.pipeline["yield_priors"] = {"q_ask": {"weak": 0.2}}
    from careeros.yield_model import priors

    pr = priors(settings)
    assert pr["q_ask"] == {"warm": 0.4, "weak": 0.2} and pr["r"]["cold"] == 0.03
    assert referral_lift(70, pr=pr) == pytest.approx(1 + 0.2 * (0.02 - 0.0018) / 0.0018)


def test_bad_prior_is_config_error(settings):
    from careeros.config import ConfigError
    from careeros.yield_model import priors

    settings.pipeline["yield_priors"] = {"r": {"cold": 3}}
    with pytest.raises(ConfigError, match="yield_priors.r.cold"):
        priors(settings)


@pytest.mark.integration
def test_imported_network_reorders_the_prepare_queue(settings):
    from test_runs_prepare import NOW as PNOW, add_job

    from careeros.network import network_path
    from careeros.runs.config import load_runs_config
    from careeros.runs.runner import select_candidates
    from careeros.store import Store

    st = Store(settings)
    a = add_job(st, 1, company="Acme", fit=75)
    b = add_job(st, 2, company="Beta", fit=80)
    order = lambda: select_candidates(settings, "prepare", load_runs_config(settings), PNOW)[0]
    assert [c["job_id"] for c in order()] == [b, a]
    p = network_path(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"connections": [{"name": "X", "company": "Acme", "position": "SWE"}]}))
    sel = order()
    assert [c["job_id"] for c in sel] == [a, b] and "referral possible" in sel[0]["why"]


def test_bad_prior_fails_at_load(tmp_path):
    import shutil

    import yaml
    from conftest import EXAMPLE_REPO

    from careeros.config import ConfigError, Settings

    root = tmp_path / "r"
    shutil.copytree(EXAMPLE_REPO / "config", root / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", root / "profile")
    p = root / "config" / "pipeline.yaml"
    d = yaml.safe_load(p.read_text())
    d["yield_priors"] = {"m_stale": 0}
    p.write_text(yaml.safe_dump(d))
    with pytest.raises(ConfigError, match="yield_priors.m_stale"):
        Settings.load(root)
