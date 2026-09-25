from __future__ import annotations

from pathlib import Path

import pytest

from careeros.config import Settings
from careeros.models import Posting
from careeros.scout import Prefilter

pytestmark = pytest.mark.unit


def _p(title="Software Engineer", company="Acme", location="New York, NY", raw=None):
    return Posting(company=company, title=title, location=location, ats="greenhouse", ats_job_id=title, raw=raw or {})


@pytest.mark.parametrize("title,reason", [
    ("Senior Software Engineer", "seniority"),
    ("Sr. Backend Engineer", "seniority"),
    ("Staff Software Engineer", "seniority"),
    ("Software Engineer, Tech Lead", "seniority"),
    ("Software Engineer Intern", "seniority"),
    ("Software Engineer (Co-op)", "seniority"),
    ("Software Engineering Manager, Payments", "title"),  # "software engineering" is not a keyword
    ("Backend Engineer - Head of Platform", "seniority"),
    ("Software Engineer II", "ok"),
    ("Software Engineer, Leadership Tools", "ok"),  # "lead" must not match inside "leadership"
    ("Software Engineer, Internal Tools", "ok"),     # "intern" must not match inside "internal"
    ("Data Engineer", "ok"),
])
def test_seniority_filter(example_settings, title, reason):
    assert Prefilter(example_settings).check(_p(title))[1] == reason


@pytest.mark.parametrize("title,reason,cat", [
    ("Solutions Engineer", "title", None),
    ("Software Engineer, Technical Support", "title", "swe_backend"),  # "technical support" excluded
    ("Support Engineer", "title", None),
    ("Hardware Engineer", "title", None),
    ("Software Engineer, Hardware Engineer Tools", "title", "swe_backend"),  # excluded keyword vetoes
    ("Full-Stack Engineer", "ok", "swe_fullstack"),
    ("SRE", "ok", "sre_devops"),
    ("Answer Desk Lead", "title", None),
])
def test_excluded_and_category(example_settings, title, reason, cat):
    ok, why, c = Prefilter(example_settings).check(_p(title))
    assert why == reason and c == cat and ok is (reason == "ok")


def _pf(blocked, aliases=None):
    loc = {"blocked_countries": blocked}
    if aliases is not None:
        loc["country_aliases"] = aliases
    return Prefilter(Settings(root=Path("."), categories={"be": {"title_keywords": ["software engineer"]}},
                              targets={"location": loc}))


@pytest.mark.parametrize("location,raw,blocked", [
    ("Berlin, Germany", {}, True),
    ("Munich", {}, True),
    ("Remote", {"country": "DE"}, True),
    ("Remote", {"country": "de"}, True),
    ("Remote", {"address": {"postalAddress": {"addressCountry": "DE"}}}, True),
    ("Remote", {"address": {"postalAddress": {"addressCountry": "Germany"}}}, True),  # Ashby uses full names
    ("London, UK", {}, True),
    ("Kyiv, Ukraine", {}, False),  # alias "uk" must not match inside "ukraine"
    ("Bengaluru, India", {}, True),
    ("Indianapolis, IN", {}, False),  # "india" alias must not match inside "indianapolis"
    ("New York, NY", {}, False),
    ("Remote", {"address": "not a dict"}, False),
])
def test_country_aliases(location, raw, blocked):
    pf = _pf(["DE", "GB", "IN"])
    assert pf.location_blocked(_p(location=location, raw=raw)) is blocked


def test_unknown_country_code_falls_back_to_code_word():
    pf = _pf(["FR"])
    assert pf.location_blocked(_p(location="Remote (FR)"))
    assert not pf.location_blocked(_p(location="San Francisco, CA"))


def test_configured_aliases_extend_and_override_builtins():
    pf = _pf(["XX", "DE"], aliases={"XX": ["Freedonia", "Fredville"], "DE": ["bavaria"]})
    assert pf.location_blocked(_p(location="Fredville, Freedonia"))
    assert pf.location_blocked(_p(location="Remote", raw={"country": "XX"}))
    assert pf.location_blocked(_p(location="Bavaria"))
    assert not pf.location_blocked(_p(location="Berlin"))  # per-code override replaces the built-in list
    assert pf.location_blocked(_p(location="Remote", raw={"country": "DE"}))  # the code itself still counts


def test_no_blocked_countries_never_blocks():
    assert not _pf([]).location_blocked(_p(location="Berlin", raw={"country": "DE"}))


def test_example_config_blocks_no_country(example_settings):
    assert example_settings.blocked_countries() == []
    assert not Prefilter(example_settings).location_blocked(_p(location="Berlin, Germany"))


def test_blocklist_checked_before_title(example_settings):
    assert Prefilter(example_settings).check(_p("Product Manager", company="Globex Bank")) == (False, "blocklist", None)
