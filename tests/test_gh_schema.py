"""Greenhouse question schema -> normalized fields -> fill_plan (no network: recorded fixture)."""
from __future__ import annotations

import pytest
import yaml
from conftest import EXAMPLE_REPO, load_fixture

from careeros.apply.gh_schema import build_plan, normalize, pick_option
from careeros.apply.questions import clear_cache

pytestmark = pytest.mark.unit

DATA = load_fixture("greenhouse/job_questions.json")
ANSWERS = EXAMPLE_REPO / "profile" / "standard_answers.yaml"
PROFILE = yaml.safe_load((EXAMPLE_REPO / "profile" / "master.yaml").read_text())


@pytest.fixture(autouse=True)
def _clear():
    clear_cache()


def _by_id(fields):
    return {f["field_id"]: f for f in fields}


def test_normalize_types_and_sources():
    f = _by_id(normalize(DATA))
    assert f["first_name"] == {"field_id": "first_name", "label": "First Name", "type": "text", "required": True,
                               "options": []}
    assert f["resume"]["type"] == "file" and "resume_text" not in f  # paste-text alternative dropped
    assert f["question_68581533"]["type"] == "textarea"
    assert f["question_68581532[]"]["type"] == "checkbox_group" and len(f["question_68581532[]"]["options"]) == 4
    assert f["question_68581540"]["type"] == "select" and f["question_68581540"]["options"]
    assert {"veteran_status", "race", "gender"} <= f.keys()  # compliance
    assert f["latitude"]["type"] == "hidden" and f["location"]["type"] == "text"  # location_questions


def test_normalize_keeps_api_order():
    ids = [x["field_id"] for x in normalize(DATA)]
    assert ids[:4] == ["first_name", "last_name", "email", "phone"]


@pytest.mark.parametrize("answer,expect", [("Yes", "Yes"), ("yes", "Yes"), ("No", "No"), ("Maybe", None)])
def test_pick_option_exact_then_prefix(answer, expect):
    assert pick_option(["Yes", "No"], answer) == expect


def test_pick_option_word_prefix_only():
    assert pick_option(["Decline To Self Identify", "Male"], "Decline") == "Decline To Self Identify"
    assert pick_option(["Not sure"], "No") is None


def _plan(**kw):
    return build_plan(normalize(DATA), profile=PROFILE, answers_path=ANSWERS, company="Ledgerline",
                      files={"resume": "/tmp/r.pdf", "cover_letter": None}, **kw)


def test_plan_identity_files_and_hidden():
    f = _by_id(_plan()["fields"])
    assert f["first_name"]["value"] == "Alex" and f["last_name"]["value"] == "Example"
    assert f["email"]["value"] == "alex@example.com" and f["email"]["source"] == "profile"
    assert f["resume"]["value"] == "/tmp/r.pdf" and not f["resume"]["needs_review"]
    assert f["cover_letter"]["value"] is None
    assert f["latitude"]["needs_review"] is False and f["latitude"]["value"] is None


def test_plan_selects_are_exact_option_labels_or_review():
    for x in _plan()["fields"]:
        if x["type"] in ("select", "multiselect") and x["value"] is not None:
            assert x["value"] in x["options"], x
        if x["type"] == "checkbox_group" and x["value"] is not None:
            assert set(x["value"]) <= set(x["options"]), x
        if x["value"] is None and x["type"] not in ("hidden", "file"):  # optional files stay blank
            assert x["needs_review"], x


def test_plan_eeo_only_from_eeo_block():
    f = _by_id(_plan()["fields"])
    assert f["veteran_status"]["value"] == "I don't wish to answer" and f["veteran_status"]["source"] == "eeo"


def test_preferred_name_is_not_a_referral():  # "Preferred" contains "referred"
    f = _by_id(_plan()["fields"])
    assert f["question_68581528"]["value"] is None and f["question_68581528"]["needs_review"]


def test_plan_essay_left_for_review():
    f = _by_id(_plan()["fields"])
    assert f["question_68581533"]["value"] is None and f["question_68581533"]["needs_review"]


def test_plan_greenhouse_extras_only_where_profile_has_data():
    f = _by_id(_plan()["fields"])
    assert f["candidate-location"] == {"field_id": "candidate-location", "label": "Location (City)",
                                       "type": "select_async", "value": "Springfield", "source": "profile",
                                       "needs_review": False}
    assert f["school--0"]["value"] == "Springfield State University"
    assert f["start-year--0"]["value"] == "2022"
    assert "country" not in f  # example identity has no country
    prof = {**PROFILE, "identity": {**PROFILE["identity"], "country": "United States"}}
    f2 = _by_id(build_plan(normalize(DATA), profile=prof, answers_path=ANSWERS, company="x", files={})["fields"])
    assert f2["country"]["value"] == "United States"


def _paused(tmp_path, label):
    ans = tmp_path / "sa.yaml"
    ans.write_text("answers:\n  - key: current_employer\n    match: ['current employer']\n    answer: Foo\n")
    fields = [{"field_id": "q1", "label": label, "type": "text", "required": True, "options": []}]
    return build_plan(fields, profile=PROFILE, answers_path=ans, files={})["fields"][0]


@pytest.mark.parametrize("label,kind", [
    ("Are you legally authorized to work in the United States?", "legal"),
    ("What are your salary expectations?", "salary"),
    ("Please enter your Social Security Number", "sensitive"),
])
def test_plan_never_guesses_legal_salary_sensitive(tmp_path, label, kind):
    row = _paused(tmp_path, label)
    assert row["value"] is None and row["needs_review"] and row["source"] == f"pause:{kind}"
