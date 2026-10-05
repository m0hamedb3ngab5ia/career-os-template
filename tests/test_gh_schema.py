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
    assert f["latitude"]["type"] == "hidden"  # location_questions
    assert "location" not in f  # job-boards renders it as the candidate-location autocomplete (plan extras)


def test_normalize_adds_hispanic_before_race():
    """The API folds Hispanic/Latino into race; job-boards asks it first and shows race only after "No"."""
    ids = [x["field_id"] for x in normalize(DATA)]
    assert ids.index("hispanic_ethnicity") == ids.index("race") - 1
    h = _by_id(normalize(DATA))["hispanic_ethnicity"]
    assert h["type"] == "select" and h["options"] == ["Yes", "No", "Decline To Self Identify"]


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


def test_pick_option_ambiguous_prefix_is_none():
    assert pick_option(["Yes, but I need sponsorship later", "Yes, I am a citizen"], "Yes") is None
    assert pick_option(["Yes", "Yes, but later"], "Yes") == "Yes"  # exact still wins


def test_plan_combined_degree_needs_review():
    f = _by_id(_plan()["fields"])  # example profile: "Bachelor of Science, Computer Science", no discipline
    assert f["degree--0"]["needs_review"] and f["discipline--0"]["needs_review"]
    assert f["discipline--0"]["value"] is None
    edu = {**PROFILE["education"][0], "degree": "BS", "discipline": "Computer Science"}
    f2 = _by_id(build_plan([], profile={**PROFILE, "education": [edu]}, answers_path=ANSWERS, files={})["fields"])
    assert f2["degree--0"]["value"] == "BS" and not f2["degree--0"]["needs_review"]
    assert f2["discipline--0"]["value"] == "Computer Science" and not f2["discipline--0"]["needs_review"]


@pytest.mark.unit
def test_carry_over_keeps_user_edits_and_skips_by_field_id():
    from careeros.apply.gh_schema import carry_over

    old = {"fields": [
        {"field_id": "a", "type": "text", "value": "mine", "source": "user", "needs_review": False},
        {"field_id": "b", "type": "text", "value": None, "source": "unanswered", "skipped": True, "needs_review": False},
        {"field_id": "gone", "type": "text", "value": "x", "source": "user", "needs_review": False},
        {"field_id": "c", "type": "text", "value": "old", "source": "standard:k", "needs_review": False}]}
    new = {"fields": [
        {"field_id": "a", "type": "text", "value": None, "source": "unanswered", "needs_review": True},
        {"field_id": "b", "type": "text", "value": None, "source": "unanswered", "needs_review": True},
        {"field_id": "c", "type": "text", "value": "new", "source": "standard:k", "needs_review": False}]}
    by = {f["field_id"]: f for f in carry_over(old, new)["fields"]}
    assert by["a"]["value"] == "mine" and by["a"]["source"] == "user" and not by["a"]["needs_review"]
    assert by["b"]["skipped"] is True and by["b"]["value"] is None
    assert by["c"]["value"] == "new" and "gone" not in by


DRAFT_FIELDS = [{"field_id": "q_why", "label": "Why do you want to work here?", "type": "textarea", "options": [],
                 "required": True},
                {"field_id": "q_sal", "label": "What are your salary expectations?", "type": "text", "options": [],
                 "required": True},
                {"field_id": "q_visa", "label": "Will you require visa sponsorship?", "type": "text", "options": [],
                 "required": True},
                {"field_id": "q_tea", "label": "Favourite tea", "type": "select", "options": ["Green", "Black"],
                 "required": False}]
DRAFTS = [{"question": "Why do you want to work here? ", "answer": "Because of the mission.", "type": "essay"},
          {"question": "What are your salary expectations?", "answer": "Lots", "type": "essay"},
          {"question": "Will you require visa sponsorship?", "answer": "No", "type": "essay"},
          {"question": "Favourite tea", "answer": "Green", "type": "essay"}]


@pytest.mark.unit
def test_build_plan_ai_draft_only_for_freetext_never_legal_salary():
    """REQ-105/DEC-010: answers.json drafts fill freetext fields with no saved answer, unreviewed; never
    legal/salary/EEO, never selects."""
    by = _by_id(build_plan(DRAFT_FIELDS, profile={}, answers_path=ANSWERS, files={}, drafts=DRAFTS)["fields"])
    assert by["q_why"]["value"] == "Because of the mission." and by["q_why"]["source"] == "ai_draft"
    assert by["q_why"]["reviewed"] is False and by["q_why"]["needs_review"] is True
    for fid in ("q_sal", "q_visa"):  # salary/legal: saved answer or pause, never the draft
        assert by[fid]["source"] != "ai_draft" and "reviewed" not in by[fid]
    assert by["q_tea"]["value"] is None and by["q_tea"]["source"] == "unanswered"
    assert _by_id(build_plan(DRAFT_FIELDS, profile={}, answers_path=ANSWERS, files={})["fields"])["q_why"]["value"] is None


@pytest.mark.unit
def test_carry_over_keeps_draft_review_only_for_same_text():
    from careeros.apply.gh_schema import carry_over

    def plan(text, **kw):
        return {"fields": [{"field_id": "q", "type": "textarea", "value": text, "source": "ai_draft",
                            "reviewed": False, "needs_review": True, **kw}]}
    old = plan("A", reviewed=True, needs_review=False)
    assert carry_over(old, plan("A"))["fields"][0]["reviewed"] is True
    assert carry_over(old, plan("A"))["fields"][0]["needs_review"] is False
    assert carry_over(old, plan("B"))["fields"][0]["reviewed"] is False  # draft rewritten: review again
    assert carry_over(plan("A"), plan("A"))["fields"][0]["reviewed"] is False
