from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO

from careeros.apply.questions import (
    classify_question,
    clear_cache,
    load_eeo_answers,
    load_standard_answers,
    match_standard_answer,
    normalize_eeo,
    select_eeo_option,
)
from careeros.apply.session import ApplySession

pytestmark = pytest.mark.unit

# fixture profile (fake candidate); tests never read the personal profile/ directory
PROFILE_ANSWERS = EXAMPLE_REPO / "profile" / "standard_answers.yaml"

MINI = """\
- key: work_authorization
  match: ["authorized to work", "legally authorized", "work authorization"]
  answer: "Yes"
- key: sponsorship
  match: ["sponsorship", "require .*visa"]
  answer: "No"
- key: salary_expectation
  match: ["salary", "expected .*salary"]
  answer: null
- key: years_experience_fulltime
  match: ["years of .*full.?time"]
  answer: "0"
- key: years_experience
  match: ["years of .*experience"]
  answer: "1"
- key: school
  match: ["school", "university"]
  answer: "Springfield State University"
- key: current_title
  match: ["current title", "current role"]
  answer: "Software Engineer"
- key: linkedin
  match: ["linkedin"]
  answer: "https://linkedin.com/in/alex-example"
- key: bad_regex
  match: ["(unclosed"]
  answer: "never"
eeo:
  gender: "Decline to self-identify"
  veteran: "I am not a protected veteran"
  race_ethnicity:
    answer: "Asian"
    prefer: "East Asian"
    match_not: ["Hispanic"]
  disability:
    answer: "No, I do not have a disability"
"""


@pytest.fixture
def answers_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "standard_answers.yaml"
    p.write_text(MINI, encoding="utf-8")
    clear_cache()
    return p


@pytest.fixture
def dict_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "sa.yaml"
    p.write_text(
        "answers:\n  - key: phone\n    match: ['phone']\n    answer: '201'\neeo:\n  gender: Decline\n",
        encoding="utf-8",
    )
    clear_cache()
    return p


# --- loading -------------------------------------------------------------------------------

def test_loads_list_plus_trailing_eeo_block(answers_yaml: Path) -> None:
    items = load_standard_answers(answers_yaml)
    assert [i["key"] for i in items][:2] == ["work_authorization", "sponsorship"]
    assert load_eeo_answers(answers_yaml)["veteran"] == "I am not a protected veteran"


def test_loads_dict_shape(dict_yaml: Path) -> None:
    assert match_standard_answer("Phone number", dict_yaml) == ("phone", "201")
    assert load_eeo_answers(dict_yaml) == {"gender": "Decline"}


def test_real_profile_file_parses() -> None:
    items = load_standard_answers(PROFILE_ANSWERS)
    keys = {i["key"] for i in items}
    assert {"work_authorization", "sponsorship", "salary_expectation", "linkedin"} <= keys
    assert "gender" in load_eeo_answers(PROFILE_ANSWERS)


# --- matching ---------------------------------------------------------------------------------

def test_match_basic(answers_yaml: Path) -> None:
    assert match_standard_answer("Are you legally authorized to work in the United States?", answers_yaml) == (
        "work_authorization", "Yes")
    assert match_standard_answer("Will you now or in the future require visa sponsorship?", answers_yaml) == (
        "sponsorship", "No")


def test_match_is_case_insensitive_and_whitespace_tolerant(answers_yaml: Path) -> None:
    assert match_standard_answer("  LINKEDIN\n  profile URL *", answers_yaml) == (
        "linkedin", "https://linkedin.com/in/alex-example")


def test_salary_returns_null_answer_not_none(answers_yaml: Path) -> None:
    hit = match_standard_answer("What is your expected base salary?", answers_yaml)
    assert hit is not None
    assert hit == ("salary_expectation", None)


def test_no_match_returns_none(answers_yaml: Path) -> None:
    assert match_standard_answer("Describe a project you are proud of", answers_yaml) is None
    assert match_standard_answer("", answers_yaml) is None


def test_eeo_questions_never_match_standard(answers_yaml: Path) -> None:
    assert match_standard_answer("Gender", answers_yaml) is None
    assert match_standard_answer("Are you a protected veteran?", answers_yaml) is None
    assert match_standard_answer("Voluntary Self-Identification of Disability", answers_yaml) is None


def test_file_order_first_hit_wins(answers_yaml: Path) -> None:
    # specific entry listed first beats the general one that would also match
    assert match_standard_answer("How many years of full-time experience do you have?", answers_yaml) == (
        "years_experience_fulltime", "0")
    assert match_standard_answer("Years of relevant experience", answers_yaml) == ("years_experience", "1")
    # school is listed before current_title in MINI, so it wins on a question mentioning both
    assert match_standard_answer("What is your current title at your school?", answers_yaml)[0] == "school"


def test_real_profile_years_experience_order() -> None:
    assert match_standard_answer("Years of full-time work experience", PROFILE_ANSWERS)[0] == "years_experience_fulltime"
    assert match_standard_answer("How many years of experience do you have with Python?", PROFILE_ANSWERS)[0] == "years_experience"


# --- eeo ------------------------------------------------------------------------------------------

def test_normalize_eeo_accepts_both_shapes(answers_yaml: Path) -> None:
    n = normalize_eeo(load_eeo_answers(answers_yaml))
    assert n["gender"] == {"answer": "Decline to self-identify", "prefer": None, "match_not": []}
    assert n["race_ethnicity"]["prefer"] == "East Asian"
    assert n["race_ethnicity"]["match_not"] == ["Hispanic"]


def test_eeo_prefer_wins_when_offered(answers_yaml: Path) -> None:
    eeo = load_eeo_answers(answers_yaml)
    opts = ["Asian", "Black or African American", "East Asian (e.g. Chinese, Japanese, Korean)", "White", "Decline To Self Identify"]
    assert select_eeo_option("race_ethnicity", opts, eeo) == "East Asian (e.g. Chinese, Japanese, Korean)"


def test_eeo_falls_back_to_answer_prefix_even_with_match_not_term(answers_yaml: Path) -> None:
    eeo = load_eeo_answers(answers_yaml)
    opts = ["Hispanic or Latino", "Asian (Not Hispanic or Latino)", "Two or More Races", "Decline To Self Identify"]
    assert select_eeo_option("race_ethnicity", opts, eeo) == "Asian (Not Hispanic or Latino)"


def test_eeo_match_not_blocks_loose_substring(answers_yaml: Path) -> None:
    eeo = load_eeo_answers(answers_yaml)
    opts = ["Hispanic or Latino of Asian descent", "White", "Decline"]
    assert select_eeo_option("race_ethnicity", opts, eeo) is None


def test_eeo_prefix_and_case_insensitive(answers_yaml: Path) -> None:
    eeo = load_eeo_answers(answers_yaml)
    opts = ["Yes, I have a disability (or previously had a disability)", "NO, I DO NOT HAVE A DISABILITY", "I do not want to answer"]
    assert select_eeo_option("disability", opts, eeo) == "NO, I DO NOT HAVE A DISABILITY"
    assert select_eeo_option("veteran", ["I identify as one or more of the classifications", "I am not a protected veteran", "I don't wish to answer"], eeo) == "I am not a protected veteran"


def test_eeo_unknown_field_or_no_option_is_none(answers_yaml: Path) -> None:
    eeo = load_eeo_answers(answers_yaml)
    assert select_eeo_option("shoe_size", ["9"], eeo) is None
    assert select_eeo_option("gender", ["Male", "Female"], eeo) is None
    assert select_eeo_option("gender", [], eeo) is None


def test_example_profile_eeo_shape_declines() -> None:
    eeo = load_eeo_answers(PROFILE_ANSWERS)
    assert set(eeo) == {"gender", "hispanic_latino", "race_ethnicity", "veteran", "disability"}
    assert all(isinstance(v, dict) and "answer" in v for v in eeo.values())
    assert {"prefer", "match_not"} <= set(eeo["race_ethnicity"])
    assert select_eeo_option("gender", ["Male", "Female", "Decline To Self Identify"], eeo) == "Decline To Self Identify"
    assert select_eeo_option("hispanic_latino", ["Yes", "No", "Decline"], eeo) == "Decline"
    # no decline option offered -> blank (the skill raises an Action Item), never a guess
    assert select_eeo_option("race_ethnicity", ["Asian", "East Asian"], eeo) is None


def test_bad_regex_is_skipped(answers_yaml: Path) -> None:
    assert match_standard_answer("(unclosed", answers_yaml) is None


def test_real_profile_common_questions() -> None:
    q = {
        "Are you legally authorized to work in the U.S.?": "work_authorization",
        "Do you now or will you in the future require sponsorship for employment visa status?": "sponsorship",
        "LinkedIn Profile": "linkedin",
        "GitHub URL": "github",
        "How did you hear about this job?": "referral",
        "Have you previously applied to this company?": "previously_applied",
        "What is your GPA?": "gpa",
    }
    for text, key in q.items():
        hit = match_standard_answer(text, PROFILE_ANSWERS)
        assert hit is not None and hit[0] == key, (text, hit)


# --- classification --------------------------------------------------------------------------------

@pytest.mark.parametrize("text,kind", [
    ("Gender", "eeo"),
    ("Race/Ethnicity", "eeo"),
    ("Are you Hispanic or Latino?", "eeo"),
    ("Veteran Status", "eeo"),
    ("Disability Status", "eeo"),
    ("Expected salary", "salary"),
    ("Compensation expectations (USD)", "salary"),
    ("Are you authorized to work in the US?", "legal"),
    ("Will you require sponsorship?", "legal"),
    ("Do you have a security clearance?", "legal"),
    ("Are you subject to a non-compete agreement?", "legal"),
    ("Why do you want to work at Acme?", "essay"),
    ("Tell us about a time you disagreed with a teammate.", "essay"),
    ("Describe your most impactful project", "essay"),
    ("LinkedIn Profile", "standard"),
    ("Current company", "standard"),
    ("How did you hear about us?", "standard"),
    ("Favorite color", "unknown"),
    ("", "unknown"),
])
def test_classify(text: str, kind: str) -> None:
    assert classify_question(text) == kind


def test_classify_with_yaml_prefers_standard(answers_yaml: Path) -> None:
    assert classify_question("Please enter your school name", answers_yaml) == "standard"
    # legal beats standard even when the yaml has an answer: skill must still route via standard answers
    assert classify_question("Are you authorized to work in the US?", answers_yaml) == "legal"


# --- session --------------------------------------------------------------------------------------

def test_session_roundtrip_and_log(tmp_path: Path) -> None:
    job = tmp_path / "job1"
    s = ApplySession.start("job1", "greenhouse", apply_url="https://boards.greenhouse.io/x/jobs/1",
                           tier="B", auto_submit=True, resume_version="swe_backend-v1")
    s.step("open_tab")
    s.shot(s.next_screenshot_path(job, "form"))
    assert s.can_click_submit()
    s.mark_submit_clicked()
    assert not s.can_click_submit()
    s.finish("submitted", reason="confirmation matched", confirmation_text="Thank you for applying")
    p = s.save(job)
    assert p.name == "apply_session.json"
    assert (job / "screenshots").is_dir()
    log = (job / "log.md").read_text()
    assert "[applier] greenhouse session submitted" in log
    back = ApplySession.load(job)
    assert back is not None and back.outcome == "submitted" and back.status == "applied"
    assert back.submit_clicked and len(back.steps) == 3
    assert s.result_line().startswith("RESULT: {")


def test_session_rejects_bad_outcome() -> None:
    s = ApplySession.start("j", "lever")
    with pytest.raises(ValueError):
        s.finish("done")


def test_session_tier_a_never_submits() -> None:
    s = ApplySession.start("j", "greenhouse", tier="A", auto_submit=False)
    assert not s.can_click_submit()
    s.finish("needs_review", reason="tier A", action_item={"type": "review", "what": "review & submit"})
    assert s.status == "needs_review" and s.action_item["type"] == "review"


# --- backfill: EEO ranking on realistic option lists ----------------------------------------------

GREENHOUSE_GENDER = ["Male", "Female", "Decline To Self Identify"]
WORKDAY_GENDER = ["Female", "Non-Binary", "I do not wish to answer"]


def test_eeo_substring_needs_word_boundary() -> None:
    """answer "Male" must never pick "Female" (substring) when the form has no Male option."""
    eeo = {"gender": {"answer": "Male"}}
    assert select_eeo_option("gender", GREENHOUSE_GENDER, eeo) == "Male"
    assert select_eeo_option("gender", WORKDAY_GENDER, eeo) is None
    assert select_eeo_option("gender", ["Gender: Male", "Gender: Female"], eeo) == "Gender: Male"


def test_eeo_exact_beats_prefix() -> None:
    eeo = {"hispanic_latino": {"answer": "No"}}
    assert select_eeo_option("hispanic_latino", ["Not Declared", "No", "Yes"], eeo) == "No"
    assert select_eeo_option("hispanic_latino", ["Yes", "No", "Decline To Self Identify"], eeo) == "No"
    # a word-prefix is still accepted ("No, I am not Hispanic or Latino")
    wd = ["Yes, I am Hispanic or Latino", "No, I am not Hispanic or Latino", "I do not wish to answer"]
    assert select_eeo_option("hispanic_latino", wd, eeo) == "No, I am not Hispanic or Latino"


WORKDAY_RACE = [
    "American Indian or Alaska Native (Not Hispanic or Latino) (United States of America)",
    "Asian (Not Hispanic or Latino) (United States of America)",
    "Black or African American (Not Hispanic or Latino) (United States of America)",
    "Hispanic or Latino (United States of America)",
    "Native Hawaiian or Other Pacific Islander (Not Hispanic or Latino) (United States of America)",
    "Two or More Races (Not Hispanic or Latino) (United States of America)",
    "White (Not Hispanic or Latino) (United States of America)",
    "I do not wish to answer. (United States of America)",
]
GREENHOUSE_RACE = ["American Indian or Alaskan Native", "Asian", "Black or African American", "Hispanic or Latino",
                   "White", "Native Hawaiian or Other Pacific Islander", "Two or More Races", "Decline To Self Identify"]


@pytest.mark.parametrize("opts,want", [
    (GREENHOUSE_RACE, "Asian"),
    (WORKDAY_RACE, "Asian (Not Hispanic or Latino) (United States of America)"),
    (GREENHOUSE_RACE + ["East Asian"], "East Asian"),  # prefer wins when offered
    (["Hispanic or Latino", "Two or More Races"], None),
])
def test_eeo_race_prefer_fallback_match_not(opts, want) -> None:
    eeo = {"race_ethnicity": {"answer": "Asian", "prefer": "East Asian", "match_not": ["Hispanic"]}}
    assert select_eeo_option("race_ethnicity", opts, eeo) == want


def test_example_veteran_and_disability_decline() -> None:
    eeo = load_eeo_answers(PROFILE_ANSWERS)
    gh_vet = ["I am not a protected veteran",
              "I identify as one or more of the classifications of protected veteran", "I don't wish to answer"]
    assert select_eeo_option("veteran", gh_vet, eeo) == "I don't wish to answer"
    cc305 = ["Yes, I have a disability, or have had one in the past",
             "No, I do not have a disability and have not had one in the past", "I do not want to answer"]
    assert select_eeo_option("disability", cc305, eeo) == "I do not want to answer"


def test_eeo_veteran_and_disability_realistic() -> None:
    eeo = {"veteran": {"answer": "I am not a protected veteran"},
           "disability": {"answer": "No, I do not have a disability"}}
    gh_vet = ["I am not a protected veteran",
              "I identify as one or more of the classifications of protected veteran", "I don't wish to answer"]
    assert select_eeo_option("veteran", gh_vet, eeo) == "I am not a protected veteran"
    cc305 = ["Yes, I have a disability, or have had one in the past",
             "No, I do not have a disability and have not had one in the past", "I do not want to answer"]
    assert select_eeo_option("disability", cc305, eeo) == cc305[1]
    # Workday wording differs ("Don't") -> no guess, leave blank (-> Action Item)
    wd = ["Yes, I Have A Disability, Or Have A History/Record Of Having A Disability",
          "No, I Don't Have A Disability, Or A History/Record Of Having A Disability", "I Don't Wish To Answer"]
    assert select_eeo_option("disability", wd, eeo) is None


# --- backfill: legal / salary questions never borrow an unrelated standard answer ------------------

@pytest.mark.parametrize("text", [
    "Have you ever been convicted of a crime in any city, state or country?",
    "Do you consent to a background check covering your current employer?",
    "Are you subject to export control restrictions in your city of residence?",
])
def test_legal_question_not_answered_by_loose_pattern(text: str) -> None:
    assert classify_question(text) == "legal"
    assert match_standard_answer(text, PROFILE_ANSWERS) is None


@pytest.mark.parametrize("text", [
    "What base pay are you targeting in your city?",
    "Hourly rate expectation (include your zip code)",
])
def test_salary_question_not_answered_by_loose_pattern(text: str) -> None:
    assert classify_question(text) == "salary"
    hit = match_standard_answer(text, PROFILE_ANSWERS)
    assert hit is None or hit[1] is None


def test_legal_questions_with_standard_entry_still_match() -> None:
    assert match_standard_answer("Will you now or in the future require visa sponsorship?", PROFILE_ANSWERS) == (
        "sponsorship", "No")
    assert match_standard_answer("Are you at least 18 years of age?", PROFILE_ANSWERS) == ("over_18", "Yes")
    assert match_standard_answer("Do you hold an active security clearance?", PROFILE_ANSWERS) == (
        "security_clearance", "No")


@pytest.mark.parametrize("text,key", [
    ("How many years of full-time experience do you have?", "years_experience_fulltime"),
    ("Years of professional experience post-graduation", "years_experience_fulltime"),
    ("Years of relevant experience", "years_experience"),
    ("Years of full-time professional experience post-grad", "years_experience_fulltime"),
    ("How many years of experience with Python?", "years_experience"),
    ("What is your expected salary?", "salary_expectation"),
])
def test_fixture_profile_file_order(text: str, key: str) -> None:
    assert match_standard_answer(text, PROFILE_ANSWERS)[0] == key


# --- backfill: session guard -------------------------------------------------------------------

def test_session_second_submit_click_raises(tmp_path: Path) -> None:
    s = ApplySession.start("j", "greenhouse", tier="B", auto_submit=True)
    s.mark_submit_clicked()
    with pytest.raises(RuntimeError):
        s.mark_submit_clicked()
    assert sum(1 for st in s.steps if st["action"] == "submit_click") == 1


def test_session_no_auto_submit_cannot_mark(tmp_path: Path) -> None:
    s = ApplySession.start("j", "greenhouse", tier="A", auto_submit=False)
    with pytest.raises(RuntimeError):
        s.mark_submit_clicked()
    assert not s.submit_clicked


def test_session_submit_guard_survives_reload(tmp_path: Path) -> None:
    s = ApplySession.start("j", "lever", auto_submit=True)
    s.mark_submit_clicked()
    s.save(tmp_path)  # crash after click, before finish
    back = ApplySession.load(tmp_path)
    assert back.submit_clicked and not back.can_click_submit()
    assert back.outcome is None and back.status == "needs_review"


def test_session_save_is_atomic_and_appends_log(tmp_path: Path) -> None:
    import json

    s = ApplySession.start("j", "ashby")
    s.step("fill", ok=False, note="upload failed")
    s.finish("blocked", reason="captcha", action_item={"type": "captcha", "what": "solve captcha"})
    s.save(tmp_path)
    s.save(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["apply_session.json", "log.md"]
    d = json.loads((tmp_path / "apply_session.json").read_text())
    assert d["status"] == "needs_review" and d["n_steps"] == 2 and d["failed_steps"][0]["action"] == "fill"
    log = (tmp_path / "log.md").read_text().splitlines()
    assert len(log) == 2 and "action item: captcha - solve captcha" in log[0]
    res = json.loads(s.result_line().removeprefix("RESULT: "))
    assert res["outcome"] == "blocked" and res["submit_clicked"] is False
    assert ApplySession.load(tmp_path / "nope") is None


def test_screenshot_paths_numbered_and_sanitized(tmp_path: Path) -> None:
    s = ApplySession.start("j", "greenhouse")
    p1 = s.shot(s.next_screenshot_path(tmp_path, "form page/1"))
    p2 = s.next_screenshot_path(tmp_path, "x" * 80)
    assert Path(p1).name == "01_form_page_1.png" and p2.name == "02_" + "x" * 40 + ".png"
