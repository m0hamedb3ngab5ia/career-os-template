"""Every label of a recorded Greenhouse form -> classify + match against the example candidate's
profile/standard_answers.yaml (copied to a temp root, loaded from disk like the apply-job skill does)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import FIXTURES

from careeros.apply.questions import (
    classify_question,
    clear_cache,
    load_eeo_answers,
    match_standard_answer,
    normalize_eeo,
    select_eeo_option,
)

pytestmark = pytest.mark.integration

FORM = json.loads((FIXTURES / "greenhouse_form.json").read_text())
QUESTIONS = FORM["questions"]


@pytest.fixture
def answers_path(temp_root: Path) -> Path:
    clear_cache()
    return temp_root / "profile" / "standard_answers.yaml"


def test_fixture_is_realistic():
    assert len(QUESTIONS) >= 20
    assert {q["eeo_field"] for q in QUESTIONS if "eeo_field" in q} == {
        "gender", "hispanic_latino", "race_ethnicity", "veteran", "disability"}


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["label"][:40] for q in QUESTIONS])
def test_each_label_classified_and_matched(q, answers_path: Path):
    kind = classify_question(q["label"], answers_path)
    assert kind == q["kind"], (q["label"], kind)
    hit = match_standard_answer(q["label"], answers_path)
    assert (hit[0] if hit else None) == q["expect"], (q["label"], hit)
    if kind == "eeo":
        assert hit is None  # EEO never comes from the standard list


def test_no_auto_answer_for_unmatched_legal_or_any_salary(answers_path: Path):
    by_key = {a["key"]: a for a in yaml.safe_load(answers_path.read_text())["answers"]}
    for q in QUESTIONS:
        kind = classify_question(q["label"], answers_path)
        hit = match_standard_answer(q["label"], answers_path)
        if kind == "salary":
            assert hit is None or hit[1] is None, q["label"]  # -> Action Item
        if kind == "legal":
            if hit is None:
                continue  # -> Action Item
            # only an explicit legal entry from standard_answers.yaml, verbatim
            assert hit[0] in {"work_authorization", "sponsorship", "citizenship", "over_18", "non_compete",
                              "security_clearance"}, (q["label"], hit)
            assert hit[1] == by_key[hit[0]]["answer"]
    unanswered_legal = [q["label"] for q in QUESTIONS
                        if classify_question(q["label"], answers_path) == "legal" and match_standard_answer(q["label"], answers_path) is None]
    assert len(unanswered_legal) == 2  # felony + background check -> Action Items


def test_answered_selects_pick_an_offered_option(answers_path: Path):
    for q in QUESTIONS:
        hit = match_standard_answer(q["label"], answers_path)
        if hit and hit[1] is not None and q.get("options") and "eeo_field" not in q:
            assert hit[1] in q["options"], (q["label"], hit)


def _resolve(answers_path: Path) -> tuple[dict, dict]:
    eeo = load_eeo_answers(answers_path)
    got = {q["eeo_field"]: select_eeo_option(q["eeo_field"], q["options"], eeo) for q in QUESTIONS if "eeo_field" in q}
    return got, normalize_eeo(eeo)


def test_example_eeo_block_declines_every_field(answers_path: Path):
    got, _ = _resolve(answers_path)
    assert got == {
        "gender": "Decline To Self Identify",
        "hispanic_latino": "Decline To Self Identify",
        "race_ethnicity": "Decline To Self Identify",
        "veteran": "I don't wish to answer",
        "disability": "I do not want to answer",
    }


FILLED_EEO = """
eeo:
    gender:
      answer: "Female"
    hispanic_latino:
      answer: "No"
    race_ethnicity:
      answer: "Asian"
      prefer: "East Asian"
      match_not: ["Hispanic"]
    veteran:
      answer: "I am not a protected veteran"
    disability:
      answer: "No, I do not have a disability"
"""


def test_edited_eeo_block_resolves_to_configured_values(answers_path: Path):
    """The shape a candidate gets after editing the `# EDIT` values: loaded from disk, same parser."""
    text = answers_path.read_text()
    answers_path.write_text(text[: text.index("\neeo:")] + FILLED_EEO)
    clear_cache()
    got, spec = _resolve(answers_path)
    assert got == {
        "gender": "Female",
        "hispanic_latino": "No",
        "race_ethnicity": "Asian",  # prefer "East Asian" not offered -> answer
        "veteran": "I am not a protected veteran",
        "disability": "No, I do not have a disability and have not had one in the past",
    }
    for field, choice in got.items():
        assert choice.lower().startswith(str(spec[field]["answer"]).lower()), field


def test_crash_after_submit_click_blocks_rerun(tmp_path: Path):
    """The exact skill order in two processes: click persisted, process dies, rerun refuses."""
    import subprocess

    from conftest import PY, ROOT

    job = tmp_path / "job"
    env = {"PYTHONPATH": str(ROOT / "src"), "HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    crash = ("import os, sys; from careeros.apply.session import ApplySession as S; "
             "s = S.start('j', 'greenhouse', tier='B', auto_submit=True); s.mark_submit_clicked(sys.argv[1]); os._exit(9)")
    assert subprocess.run([PY, "-c", crash, str(job)], env=env).returncode == 9
    check = "import sys; from careeros.apply.session import ApplySession as S; print(S.already_submitted(sys.argv[1]))"
    out = subprocess.run([PY, "-c", check, str(job)], env=env, capture_output=True, text=True).stdout.strip()
    assert out == "True"
