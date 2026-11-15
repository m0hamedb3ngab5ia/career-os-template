from __future__ import annotations

import json

import pytest

from careeros.cli import main
from careeros.config import Settings
from careeros.hard_filters import hard_filters, min_years_required, pay_exempts_location
from careeros.store import Store
from conftest import make_temp_root

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("text,years", [
    ("You have 6+ years of experience building ML systems.", 6),
    ("At least 5 years of professional software experience.", 5),
    ("5-7 years of experience with Python.", 5),
    ("Minimum of 4 years' experience in backend development.", 4),
    ("3+ years of experience with Go.", 3),
    ("2+ years of experience required.\nNice to have: 8+ years of experience in trading.", 2),
    ("Bonus: 7+ years of experience with Kafka.", None),
    ("1+ years of internship experience.", None),
    ("We were founded 10 years ago and serve 5 million users.", None),
    ("New grads welcome; no prior experience required.", None),
])
def test_min_years_required(text, years):
    assert min_years_required(text) == years


def _posting(**kw):
    p = {"job_id": "job000000001", "company": "Acme Robotics", "title": "Software Engineer",
         "location": "New York, NY", "description_text": "2+ years of experience with Python.",
         "salary_min": None, "salary_max": None, "raw": {}, "ats": "greenhouse",
         "url": "https://x.test/1"}
    p.update(kw)
    return p


def test_clean_posting_has_no_fails(settings: Settings):
    assert hard_filters(settings, _posting()) == []


@pytest.mark.parametrize("kw,fail", [
    ({"description_text": "You bring 6+ years of experience shipping production services."}, "yoe_gt_3"),
    ({"title": "Senior Software Engineer"}, "title_senior"),
    ({"salary_max": 50000}, "salary_below_min"),
])
def test_each_rule(settings: Settings, kw, fail):
    assert hard_filters(settings, _posting(**kw)) == [fail]


def test_max_years_is_configurable(settings: Settings):
    settings.targets["seniority"]["max_years_required"] = 6
    assert hard_filters(settings, _posting(description_text="6+ years of experience.")) == []
    assert hard_filters(settings, _posting(description_text="7+ years of experience.")) == ["yoe_gt_6"]


def test_company_and_location(settings: Settings):
    settings.companies.setdefault("blocklist", {})["companies"] = ["Acme Robotics"]
    settings.targets["location"]["blocked_countries"] = ["DE"]
    assert hard_filters(settings, _posting(location="Berlin, Germany")) == ["company_blocked", "location_blocked"]


def test_scout_filter_toggle_off_keeps_senior(settings: Settings):
    settings.targets["scout"] = {"filters": {"seniority": False}}
    assert hard_filters(settings, _posting(title="Senior Software Engineer")) == []


def _job(tmp_path, **kw):
    root = make_temp_root(tmp_path / "repo")
    d = root / "data" / "jobs" / "job000000001"
    d.mkdir(parents=True)
    (d / "posting.json").write_text(json.dumps(_posting(**kw)))
    return root, d


def test_cli_hard_fail_writes_skip_score(tmp_path, capsys):
    root, d = _job(tmp_path, description_text="Requires 8+ years of experience.")
    assert main(["--root", str(root), "job", "filters", "job000000001"]) == 3
    sc = json.loads((d / "score.json").read_text())
    assert sc["decision"] == "skip" and sc["fit"] == 0 and sc["tier"] is None
    assert sc["hard_filter_fails"] == ["yoe_gt_3"] and sc["skip_reason"] == "yoe_gt_3"
    assert "8" in sc["fit_reasons"][0]
    assert Store(Settings.load(root)).load_score("job000000001").hard_filter_fails == ["yoe_gt_3"]
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["hard_filter_fails"] == ["yoe_gt_3"]


def test_cli_pass_writes_nothing(tmp_path):
    root, d = _job(tmp_path)
    assert main(["--root", str(root), "job", "filters", "job000000001"]) == 0
    assert not (d / "score.json").exists()


@pytest.mark.parametrize("text", [
    "Acme has 20 years of experience in fintech.",
    "For 10 years we have built experiences people love.",
    "Our team brings 15 years of experience to every launch.",
])
def test_company_history_is_not_a_years_requirement(text):
    # a false skip drops a real job silently; when unsure, leave it to the skill
    assert min_years_required(text) is None


def test_required_years_survive_a_preferred_clause_on_the_same_line():
    assert min_years_required("5+ years of experience required, 7 years of experience preferred.") == 5


@pytest.mark.parametrize("kw,cap,exempt", [
    ({"salary_min": 150000}, 150000, True),
    ({"salary_min": 149999, "salary_max": 200000}, 150000, False),
    ({"salary_max": 200000}, 150000, False),  # only a maximum posted: minimum unknown
    ({"salary_min": 160000, "salary_currency": "GBP"}, 150000, False),
    ({"salary_min": 160000}, None, False),
])
def test_pay_exempts_location(settings, kw, cap, exempt):
    settings.targets.setdefault("thresholds", {})["any_location_min_base_usd"] = cap
    assert pay_exempts_location(settings, _posting(**kw)) is exempt


def test_cli_reports_pay_exempts_location(tmp_path, capsys):
    root, d = _job(tmp_path, salary_min=150000)
    t = root / "config" / "targets.yaml"
    import yaml
    cfg = yaml.safe_load(t.read_text())
    cfg["thresholds"]["any_location_min_base_usd"] = 150000
    t.write_text(yaml.safe_dump(cfg))
    assert main(["--root", str(root), "job", "filters", "job000000001"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["pay_exempts_location"] is True


def test_non_usd_salary_is_not_compared_with_the_usd_floor(settings):
    settings.targets.setdefault("candidate", {})["min_base_usd"] = 90000
    assert "salary_below_min" not in hard_filters(settings, _posting(salary_max=60000, salary_currency="GBP"))
    assert "salary_below_min" in hard_filters(settings, _posting(salary_max=60000, salary_currency="USD"))


# ---- location_nonpreferred: decisive only when thresholds.min_fit_nonpreferred_location > 100 ----

def _never(settings, preferred=("New York NY", "Boston MA"), regions=("Northeast US",), **extra):
    settings.targets["thresholds"]["min_fit_nonpreferred_location"] = 101
    loc = settings.targets["location"]
    loc.update(preferred=list(preferred), preferred_regions=list(regions), remote_ok=True, **extra)
    return settings


@pytest.mark.parametrize("location,skipped", [
    ("Austin, TX", True),
    ("Austin, Texas", True),
    ("San Francisco, CA; Austin, TX", True),
    ("Boston, MA", False),                      # preferred city
    ("Cambridge, MA", False),                   # same state as a preferred city: leave to the skill
    ("Albany, NY", False),
    ("Pittsburgh, PA", False),                  # Northeast US region
    ("Austin, TX | Newark, NJ", False),         # one location is in a preferred region
    ("Remote - US", False),                     # remote_ok
    ("Austin, TX (Remote)", False),
    ("London, UK", False),                      # not a US state: unparseable, skill decides
    ("", False),
    ("Austin, TX; Somewhere", False),           # one part unparseable
    ("Jersey City, NJ", False),                 # Northeast by state, never by the word
    ("New York, New York", False),              # full state name
    ("Northeast", False), ("East Coast", False), ("Multiple locations", False), ("US", False),
    ("Boston", False), ("Manhattan", False), ("Hoboken", False),   # city without a state
    ("Austin, TX (Hybrid)", False), ("Hybrid", False),
    ("San Francisco, CA • New York, NY • United States", False),   # union touches preferred NY
    ("New York, NY (HQ), San Francisco, CA", False),
    ("San Francisco, CA | New York City, NY", False),
    ("San Francisco, CA / New York, NY", False), ("San Francisco, CA & Austin, TX", True),
    ("Austin, TX • United States", True),
    ("Dallas, TX; Austin, TX", True),           # every location outside
])
def test_location_nonpreferred(settings: Settings, location, skipped):
    _never(settings)
    fails = hard_filters(settings, _posting(location=location))
    assert (fails == ["location_nonpreferred"]) is skipped and (skipped or fails == [])


def test_location_check_off_when_threshold_not_above_100(settings: Settings):
    _never(settings)
    settings.targets["thresholds"]["min_fit_nonpreferred_location"] = 100
    assert hard_filters(settings, _posting(location="Austin, TX")) == []


def test_pay_exempts_the_location_skip(settings: Settings):
    _never(settings)
    settings.targets["thresholds"]["any_location_min_base_usd"] = 150000
    assert hard_filters(settings, _posting(location="Austin, TX", salary_min=160000)) == []
    assert hard_filters(settings, _posting(location="Austin, TX", salary_min=100000)) == ["location_nonpreferred"]


def test_remote_not_ok_does_not_exempt(settings: Settings):
    _never(settings)
    settings.targets["location"]["remote_ok"] = False
    assert hard_filters(settings, _posting(location="Austin, TX", remote=True)) == ["location_nonpreferred"]


def test_unmapped_region_is_undecidable(settings: Settings):
    _never(settings, regions=("US",))           # whole US preferred
    assert hard_filters(settings, _posting(location="Austin, TX")) == []
    _never(settings, regions=("Narnia",))
    assert hard_filters(settings, _posting(location="Austin, TX")) == []


def test_cli_location_skip_writes_score(tmp_path):
    root, d = _job(tmp_path, location="Austin, TX")
    s = Settings.load(root)
    s.targets["thresholds"]["min_fit_nonpreferred_location"] = 101
    s.targets["location"].update(preferred=["Boston MA"], preferred_regions=[], remote_ok=True)
    import yaml
    (root / "config" / "targets.yaml").write_text(yaml.safe_dump(s.targets))
    assert main(["--root", str(root), "job", "filters", "job000000001"]) == 3
    sc = json.loads((d / "score.json").read_text())
    assert sc["skip_reason"] == "location_nonpreferred" and sc["fit_reasons"][0].startswith("prefilter:")


def test_unparseable_pay_does_not_skip_or_exempt(settings: Settings):
    _never(settings)
    settings.targets["thresholds"]["any_location_min_base_usd"] = 150000
    p = _posting(location="Boston", salary_min=None)
    assert not pay_exempts_location(settings, p) and hard_filters(settings, p) == []


def test_skip_note_names_prefilter_and_states(tmp_path):
    from careeros.hard_filters import reasons
    s = Settings.load(make_temp_root(tmp_path / "r"))
    _never(s)
    why = reasons(s, _posting(location="Austin, TX; Denver, CO"), ["location_nonpreferred"])[0]
    assert why.startswith("prefilter: location_nonpreferred (CO, TX)")


def test_prefilter_never_skips_what_claude_prepared(tmp_path):
    from careeros.hard_filters import compare_with_scores
    root, d = _job(tmp_path, location="Austin, TX")
    s = Settings.load(root)
    _never(s)
    (d / "score.json").write_text(json.dumps({"decision": "skip"}))
    assert compare_with_scores(s) == []
    (d / "score.json").write_text(json.dumps({"decision": "prepare"}))
    assert compare_with_scores(s) == ["job000000001"]   # a prefilter bug, surfaced


def test_preferred_state_entry_without_a_code(settings: Settings):
    _never(settings, preferred=("New Jersey (any city)",), regions=())
    assert hard_filters(settings, _posting(location="Hoboken, NJ")) == []
    assert hard_filters(settings, _posting(location="Austin, TX")) == ["location_nonpreferred"]
