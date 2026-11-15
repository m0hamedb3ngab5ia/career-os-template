from __future__ import annotations

import json

import pytest

from careeros.cli import main
from careeros.config import Settings
from careeros.hard_filters import hard_filters, min_years_required
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
