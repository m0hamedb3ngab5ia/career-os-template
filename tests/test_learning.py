"""careeros.learning: answers the human gave once land in profile/standard_answers.yaml (round-trip safe, still
valid for qa + doctor) and ATS/company hurdles land in profile/apply_lessons.yaml for the next apply-job."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO, make_temp_root

from careeros.config import Settings
from careeros.learning import (learn_answer, learn_lesson, lessons_for, question_from_action, slug)

pytestmark = pytest.mark.unit


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_temp_root(tmp_path / "repo")


@pytest.fixture
def s(root: Path) -> Settings:
    return Settings.load(root)


def _job(root: Path, job_id: str = "acme-1", company: str = "Acme") -> Path:
    d = root / "data" / "jobs" / job_id
    d.mkdir(parents=True)
    (d / "posting.json").write_text(json.dumps({"id": job_id, "company": company, "title": "Engineer",
                                                "url": "https://example.com/j", "source": "greenhouse", "ats": "greenhouse"}))
    return d


def test_slug():
    assert slug("Which of the team's offices do you prefer?") == "which_of_the_teams_offices_do_you_prefer"
    assert slug("   ") == "question"


def test_learn_answer_appends_entry_that_matches_and_keeps_comments(s: Settings, root: Path):
    from careeros.apply.questions import answer_for, clear_cache

    p = root / "profile" / "standard_answers.yaml"
    before = p.read_text()
    e = learn_answer(s, question="Are you willing to travel up to 25%?", answer="Yes", job_id="acme-1")
    assert e["key"] == "are_you_willing_to_travel_up_to_25" and e["answer"] == "Yes"
    assert "learned" in e["note"] and "acme-1" in e["note"]
    text = p.read_text()
    assert text.startswith(before.split("\nanswers:")[0])  # header comments kept
    assert "# INSERT" in text and "eeo:" in text
    clear_cache()
    assert answer_for("Are you willing to  travel up to 25%?", p) == (e["key"], "Yes")
    assert "\neeo:\n    gender:" in text  # eeo block untouched (4-space indent of the example kept)
    # identity-document labels stay unanswerable even when learned (scam field gate)
    learn_answer(s, question="Driver's license number", answer="123")
    clear_cache()
    assert answer_for("Driver's license number", p) is None
    doc = yaml.safe_load(text)
    assert doc["answers"][-1]["key"] == e["key"] and doc["eeo"]["gender"]["answer"] == "Decline"


def test_learn_answer_result_passes_doctor_schema_and_qa(s: Settings, root: Path):
    from careeros.doctor import schema_problems, _safe_yaml
    from careeros.qa import Checker

    learn_answer(s, question="Are you a former intern here?", answer="No")
    prof = {n: _safe_yaml(root / "profile" / f"{n}.yaml") for n in ("master", "standard_answers", "confidential_terms")}
    cfg = {n: _safe_yaml(root / "config" / f"{n}.yaml") for n in ("targets", "categories", "companies", "qa", "pipeline")}
    assert schema_problems(cfg, prof) == []
    d = _job(root)
    learn_answer(s, question="Which office do you prefer?", answer="Springfield", job_id="acme-1")
    q = Checker(d, root)
    q.check_standard_answers()
    assert [c for c in q.checks if c["check"] == "standard_answers"][0]["ok"], q.checks


def test_qa_standard_answers_uses_the_posting_companys_learned_answer(s: Settings, root: Path):
    from careeros.qa import Checker

    q_text = "Which office would you join?"
    learn_answer(s, question=q_text, answer="Springfield", key="office", scope="company", company="Acme")
    sa = root / "profile" / "standard_answers.yaml"  # hand-edited: another company, listed first, reuses the key
    doc = yaml.safe_load(sa.read_text())
    doc["company_answers"] = {"Globex": [{"key": "office", "match": ["office"], "answer": "Shelbyville"},
                             *doc["company_answers"]["Acme"]][:1], **doc["company_answers"]}
    sa.write_text(yaml.safe_dump(doc, sort_keys=False))
    d = _job(root)  # company Acme
    for ans, ok in (("Springfield", True), ("Shelbyville", False)):
        (d / "answers.json").write_text(json.dumps([{"question": q_text, "answer": ans, "type": "standard",
                                                     "standard_key": "office"}]))
        q = Checker(d, root)
        q.check_standard_answers()
        assert [c for c in q.checks if c["check"] == "standard_answers"][0]["ok"] is ok, (ans, q.checks)


def test_learn_answer_records_into_answers_json(s: Settings, root: Path):
    d = _job(root)
    (d / "answers.json").write_text(json.dumps([{"question": "Which office do you prefer?", "answer": None,
                                                 "needs_review": True, "type": "generated"}]))
    e = learn_answer(s, question="Which office do you prefer?", answer="Springfield", job_id="acme-1")
    rec = json.loads((d / "answers.json").read_text())
    assert len(rec) == 1 and rec[0]["answer"] == "Springfield" and rec[0]["needs_review"] is False
    assert rec[0]["source"] == "learned" and rec[0]["standard_key"] == e["key"] and rec[0]["type"] == "standard"


def test_learn_answer_refusals(s: Settings, root: Path):
    with pytest.raises(ValueError):
        learn_answer(s, question="Q?", answer="   ")
    learn_answer(s, question="Q one?", answer="A", key="q_one")
    with pytest.raises(ValueError, match="q_one"):
        learn_answer(s, question="Q one again?", answer="B", key="q_one")
    ex = Settings.load(EXAMPLE_REPO)
    with pytest.raises(ValueError, match="examples"):
        learn_answer(ex, question="Q?", answer="A")
    assert "Q?" not in (EXAMPLE_REPO / "profile" / "standard_answers.yaml").read_text()


def test_company_scope_and_eeo(s: Settings, root: Path):
    from careeros.apply.questions import answer_for, clear_cache, load_company_answers

    p = root / "profile" / "standard_answers.yaml"
    e = learn_answer(s, question="Have you worked for Acme before?", answer="No", scope="company", company="Acme")
    doc = yaml.safe_load(p.read_text())
    assert doc["company_answers"]["Acme"][0]["key"] == e["key"]
    clear_cache()
    assert load_company_answers(p, "acme")[0]["answer"] == "No"
    assert answer_for("Have you worked for Acme before?", p) is None
    assert answer_for("Have you worked for Acme before?", p, company="ACME") == (e["key"], "No")
    e2 = learn_answer(s, question="Veteran status", answer="I am not a protected veteran", eeo=True, key="veteran")
    doc = yaml.safe_load(p.read_text())
    assert doc["eeo"]["veteran"]["answer"] == "I am not a protected veteran" and e2["key"] == "veteran"
    with pytest.raises(ValueError):
        learn_answer(s, question="x", answer="y", scope="company")


def test_lessons_create_append_and_filter(s: Settings, root: Path):
    p = root / "profile" / "apply_lessons.yaml"
    p.unlink()
    a = learn_lesson(s, text="Workday needs the résumé uploaded before the review page unlocks", ats="workday")
    b = learn_lesson(s, text="Acme asks for a portfolio link on page 2", company="Acme", job_id="acme-1", tags=("form",))
    c = learn_lesson(s, text="Always wait for the spinner after Next", job_id="x")
    doc = yaml.safe_load(p.read_text())
    assert [x["id"] for x in doc["lessons"]] == [a["id"], b["id"], c["id"]]
    assert b["tags"] == ["form"] and b["added"] and a["company"] is None
    assert [x["text"] for x in lessons_for(s)] == [c["text"]]
    assert [x["id"] for x in lessons_for(s, ats="workday", company="acme")] == [a["id"], b["id"], c["id"]]
    assert [x["id"] for x in lessons_for(s, ats="greenhouse")] == [c["id"]]
    with pytest.raises(ValueError):
        learn_lesson(s, text=" ")
    with pytest.raises(ValueError):
        learn_lesson(Settings.load(EXAMPLE_REPO), text="nope")


def test_example_lessons_ship_and_load(tmp_path: Path):
    from careeros.bootstrap import copy_examples

    root = tmp_path / "r"
    root.mkdir()
    copy_examples(root)
    assert (root / "profile" / "apply_lessons.yaml").exists()
    got = lessons_for(Settings.load(root), ats="workday")
    assert got and all(x["text"] for x in got)


def test_doctor_validates_apply_lessons_shape(root: Path):
    from careeros.doctor import check_apply_lessons

    p = root / "profile" / "apply_lessons.yaml"
    assert check_apply_lessons(root)[0].level == "pass"
    p.write_text("lessons:\n  - id: a\n")
    assert check_apply_lessons(root)[0].level == "fail"
    p.write_text("- just a list\n")
    assert check_apply_lessons(root)[0].level == "fail"
    p.unlink()
    assert check_apply_lessons(root)[0].level == "pass"


@pytest.mark.parametrize("what,want", [
    ("legal question not in standard answers: Are you subject to a non-compete?", "Are you subject to a non-compete?"),
    ("essay: Why do you want to work at Acme? (limit 500)", "Why do you want to work at Acme?"),
    ('salary_freeform: "What are your salary expectations?"', "What are your salary expectations?"),
    ("Do you have a valid driver's license?", "Do you have a valid driver's license?"),
])
def test_question_from_action(what: str, want: str):
    assert question_from_action(what) == want


def test_company_insert_second_company_quoted_keys_and_odd_names(s: Settings, root: Path):
    p = root / "profile" / "standard_answers.yaml"
    learn_answer(s, question="Q1?", answer="A1", company="Acme")
    learn_answer(s, question="Q2?", answer="A2", company="Big Co")
    p.write_text(p.read_text().replace("  Acme:\n", '  "Acme":\n'))  # a hand-quoted key must not be duplicated
    learn_answer(s, question="Q3?", answer="A3", company="Acme")
    learn_answer(s, question="Q4?", answer="A4", company="Big Co")
    learn_answer(s, question="Q5?", answer="A5", company="Acme, #1")  # needs quoting or `#` starts a comment
    doc = yaml.safe_load(p.read_text())
    assert [e["key"] for e in doc["company_answers"]["Acme"]] == ["q1", "q3"]
    assert [e["key"] for e in doc["company_answers"]["Big Co"]] == ["q2", "q4"]
    assert doc["company_answers"]["Acme, #1"][0]["key"] == "q5"
    assert p.read_text().count('"Acme":') == 1 and "q1" in p.read_text()  # one key, not duplicated


def test_learn_answer_rejects_bad_yaml_bad_eeo_keys_and_bad_job_ids(s: Settings, root: Path):
    p = root / "profile" / "standard_answers.yaml"
    with pytest.raises(ValueError, match="a-z0-9_"):
        learn_answer(s, question="x", answer="y", eeo=True, key="a.b")
    before = p.read_text()
    for bad in ("../x", "a/b", ".hidden"):
        with pytest.raises(ValueError, match="job_id"):
            learn_answer(s, question="Q?", answer="A", job_id=bad)
    assert p.read_text() == before  # nothing written before the refusal
    p.write_text("- a\n- b\n")
    with pytest.raises(ValueError, match="answers:"):
        learn_answer(s, question="Q?", answer="A")
    p.write_text("answers: [\n")
    with pytest.raises(ValueError, match="answers:"):
        learn_answer(s, question="Q?", answer="A")
