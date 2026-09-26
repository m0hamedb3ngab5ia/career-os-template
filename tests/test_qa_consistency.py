"""Unit tests for careeros.qa_ext.consistency: facts agree across one job's documents
(résumé, cover letter, answers, outreach drafts). Fixture candidate: Alex Example (examples/)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import EXAMPLE_REPO, build_resume_json, make_temp_root
from test_qa import COVER_LETTER, RESUME_TXT

from careeros.qa import Checker
from careeros.qa_ext.consistency import check_cross_doc

pytestmark = pytest.mark.unit

PROFILE = yaml.safe_load((EXAMPLE_REPO / "profile" / "master.yaml").read_text())
RESUME_IDS = ["acme.1", "acme.2", "acme.3", "initech_intern.1", "widgetizer.1"]

OUTREACH = {
    "job_id": "t1", "company": "Ledgerline",
    "drafts": [{
        "contact": "Jane Doe", "role": "recruiter",
        "linkedin_note": "Hi Jane, I'm a Software Engineer at Acme. I built a FastAPI service that ingests Kafka "
                         "order events into PostgreSQL, processing 2 million events per day.",
        "linkedin_message": "", "email": {"subject": "Backend role", "body": "Happy to share more."},
        "followup_7d": "", "followup_14d": "",
        "bullet_ids": ["acme.1"], "narrative_ids": [],
    }],
    "review_required": True,
}

ANSWERS = [
    {"question": "Are you authorized to work?", "answer": "Yes", "type": "standard",
     "standard_key": "work_authorization", "bullet_ids": []},
    {"question": "Describe a project you're proud of", "type": "essay", "bullet_ids": ["acme.2"],
     "answer": "At Acme I shipped a React and TypeScript dashboard used by 40 analysts to review reconciliation breaks."},
]


def make_job(tmp_path: Path, *, cover: str | None = COVER_LETTER, answers=ANSWERS, outreach=OUTREACH,
             resume_ids=RESUME_IDS, profile=PROFILE, root: Path = EXAMPLE_REPO) -> Checker:
    job = tmp_path / "jobs" / "t1"
    job.mkdir(parents=True)
    (job / "resume.json").write_text(json.dumps(build_resume_json(profile, list(resume_ids), job_id="t1")))
    (job / "resume.txt").write_text(RESUME_TXT)
    if cover is not None:
        (job / "cover_letter.md").write_text(cover)
    if answers is not None:
        (job / "answers.json").write_text(json.dumps(answers))
    if outreach is not None:
        (job / "outreach.json").write_text(json.dumps(outreach))
    return Checker(job, root)


def run(ck: Checker) -> Checker:
    check_cross_doc(ck)
    return ck


def by_name(ck: Checker, name: str) -> dict:
    for c in ck.checks:
        if c["check"] == name:
            return c
    raise AssertionError(f"check {name} not in {[c['check'] for c in ck.checks]}")


def names(ck: Checker) -> set[str]:
    return {c["check"] for c in ck.checks}


def letter(body_extra: str, ids: str = "[acme.1, initech_intern.1, widgetizer.1]") -> str:
    return (COVER_LETTER.replace("[acme.1, initech_intern.1, widgetizer.1]", ids)
            .replace("Happy to walk through the code.", body_extra + " Happy to walk through the code."))


def answer(text: str, ids=("acme.2",)) -> list[dict]:
    return [{"question": "Tell us about your work", "type": "essay", "bullet_ids": list(ids), "answer": text}]


# --- baseline ---------------------------------------------------------------------------------------

def test_consistent_job_passes_all_checks(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path))
    for name in ("letter_experiences_on_resume", "employer_title_consistent", "numbers_consistent"):
        chk = by_name(ck, name)
        assert chk["ok"] and not chk.get("skipped"), (name, chk["detail"])
    assert not any(not c["ok"] for c in ck.checks), [c for c in ck.checks if not c["ok"]]
    ex = ck.extras["consistency"]
    for key in ("docs", "letter_off_resume", "title_mismatches", "title_uncertain",
                "number_mismatches", "number_paraphrases", "config"):
        assert key in ex
    assert {"resume.json", "cover_letter.md", "answers.json#1", "outreach.json#0"} <= set(ex["docs"])


def test_levels(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path))
    assert by_name(ck, "letter_experiences_on_resume")["level"] == "soft"
    assert by_name(ck, "employer_title_consistent")["level"] == "hard"
    assert by_name(ck, "numbers_consistent")["level"] == "hard"


def test_all_skipped_without_documents(tmp_path: Path) -> None:
    job = tmp_path / "jobs" / "t1"
    job.mkdir(parents=True)
    ck = run(Checker(job, EXAMPLE_REPO))
    for name in ("letter_experiences_on_resume", "employer_title_consistent", "numbers_consistent"):
        assert by_name(ck, name).get("skipped"), name


def test_disabled_by_config(tmp_path: Path) -> None:
    root = make_temp_root(tmp_path / "repo")
    qa = yaml.safe_load((root / "config" / "qa.yaml").read_text())
    qa["consistency"] = {"enabled": False}
    (root / "config" / "qa.yaml").write_text(yaml.safe_dump(qa))
    ck = run(make_job(tmp_path, root=root, cover=letter("I was a Senior Engineer at Acme.")))
    assert all(c.get("skipped") for c in ck.checks if c["check"] in
               ("letter_experiences_on_resume", "employer_title_consistent", "numbers_consistent"))


# --- 1. letter_experiences_on_resume ------------------------------------------------------------------

def test_letter_cites_entry_dropped_from_resume(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, resume_ids=["acme.1", "acme.2", "initech_intern.1"]))
    chk = by_name(ck, "letter_experiences_on_resume")
    assert chk["ok"] is False and chk["level"] == "soft"
    assert "widgetizer.1" in chk["detail"] and "widgetizer" in chk["detail"]
    assert ck.extras["consistency"]["letter_off_resume"] == [{"id": "widgetizer.1", "entry": "widgetizer"}]


def test_letter_bullet_not_on_resume_but_entry_is_ok(tmp_path: Path) -> None:
    # initech_intern.2 is not on the résumé, but the Initech entry is: same experience, more detail
    cover = letter("", ids="[acme.1, initech_intern.2, widgetizer.1]")
    ck = run(make_job(tmp_path, cover=cover))
    assert by_name(ck, "letter_experiences_on_resume")["ok"]


def test_letter_narratives_and_unknown_ids_ignored(tmp_path: Path) -> None:
    # narratives are not résumé entries; unknown ids are truth_trace's job
    cover = letter("", ids="[acme.1, nosuch.9]")
    ck = run(make_job(tmp_path, cover=cover))
    assert by_name(ck, "letter_experiences_on_resume")["ok"]


def test_letter_check_skipped_without_letter(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, cover=None))
    assert by_name(ck, "letter_experiences_on_resume").get("skipped")


# --- 2. employer_title_consistent -----------------------------------------------------------------------

@pytest.mark.parametrize("sentence", [
    "I work as a Senior Software Engineer at Acme.",
    "I'm a Staff Engineer at Acme.",
    "At Acme, where I work as a Lead Engineer, I own the ingest path.",
])
def test_title_with_seniority_mismatch_is_hard(tmp_path: Path, sentence: str) -> None:
    ck = run(make_job(tmp_path, cover=letter(sentence)))
    chk = by_name(ck, "employer_title_consistent")
    assert chk["ok"] is False and chk["level"] == "hard"
    assert "Acme" in chk["detail"] and "Software Engineer" in chk["detail"]
    assert ck.extras["consistency"]["title_mismatches"][0]["doc"] == "cover_letter.md"


@pytest.mark.parametrize("sentence", [
    "I work as a Software Engineer at Acme.",
    "I am a software engineer at Acme.",
    "I spent a summer as an intern at Initech.",
    "I was a Data Engineering Intern at Initech in 2025.",
    "A Staff Engineer at Acme reviewed my design.",  # someone else's title: not anchored to the candidate
])
def test_title_matching_or_unanchored_is_not_hard(tmp_path: Path, sentence: str) -> None:
    ck = run(make_job(tmp_path, cover=letter(sentence)))
    assert by_name(ck, "employer_title_consistent")["ok"], by_name(ck, "employer_title_consistent")["detail"]


def test_title_with_different_descriptor_is_soft(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, cover=letter("I work as a backend engineer at Acme.")))
    assert by_name(ck, "employer_title_consistent")["ok"]
    chk = by_name(ck, "employer_title_uncertain")
    assert chk["ok"] is False and chk["level"] == "soft" and "backend engineer" in chk["detail"]


def test_title_mismatch_in_outreach_and_answers(tmp_path: Path) -> None:
    out = json.loads(json.dumps(OUTREACH))
    out["drafts"][0]["linkedin_note"] = "Hi Jane, I'm a Senior Software Engineer at Acme."
    ck = run(make_job(tmp_path, outreach=out, answers=answer("I was a Principal Engineer at Acme.")))
    docs = {m["doc"] for m in ck.extras["consistency"]["title_mismatches"]}
    assert docs == {"outreach.json#0", "answers.json#0"}
    assert by_name(ck, "employer_title_consistent")["ok"] is False


@pytest.mark.parametrize("sentence,ok", [
    ("I joined Acme in 2024.", False),              # résumé: Acme Jun 2026 - Present
    ("I joined Acme in 2026.", True),
    ("I interned at Initech in 2023.", False),      # résumé: Initech 2025
    ("Before joining Acme in 2026, I interned at Initech in 2025.", True),  # each year belongs to its nearest employer
    ("At Acme we process 2000 events per second.", True),  # not a year
])
def test_employer_years(tmp_path: Path, sentence: str, ok: bool) -> None:
    ck = run(make_job(tmp_path, cover=letter(sentence)))
    chk = by_name(ck, "employer_title_consistent")
    assert chk["ok"] is ok, chk["detail"]


@pytest.mark.parametrize("sentence,ok", [
    ("I earned my Master's in Computer Science at Springfield State University.", False),
    ("I finished a Bachelor's in Computer Science at Springfield State University in 2026.", True),
    ("I graduated from Springfield State University in 2019.", False),
])
def test_school_degree_and_years(tmp_path: Path, sentence: str, ok: bool) -> None:
    ck = run(make_job(tmp_path, cover=letter(sentence)))
    assert by_name(ck, "employer_title_consistent")["ok"] is ok, by_name(ck, "employer_title_consistent")["detail"]


# --- 3. numbers_consistent -------------------------------------------------------------------------------

@pytest.mark.parametrize("sentence", [
    "At Acme I built a FastAPI service in Python that ingests Kafka order events into PostgreSQL, processing 3 million events per day.",
    "At Acme I built a FastAPI service that ingests Kafka order events into PostgreSQL, processing three million events per day.",
])
def test_number_changed_in_letter_is_hard(tmp_path: Path, sentence: str) -> None:
    cover = COVER_LETTER.replace(
        "At Acme I built a FastAPI service in Python that ingests Kafka order events into PostgreSQL, processing 2 million events per day.",
        sentence)
    ck = run(make_job(tmp_path, cover=cover))
    chk = by_name(ck, "numbers_consistent")
    assert chk["ok"] is False and chk["level"] == "hard"
    assert "acme.1" in chk["detail"] and "2 million" in chk["detail"]
    mm = ck.extras["consistency"]["number_mismatches"][0]
    assert mm["id"] == "acme.1" and mm["doc"] == "cover_letter.md" and mm["reference"] == "resume.json"


@pytest.mark.parametrize("text", [
    "At Acme I shipped a React and TypeScript dashboard used by 40 analysts to review reconciliation breaks.",
    "At Acme I shipped a React/TypeScript dashboard for forty analysts reviewing reconciliation breaks.",
])
def test_same_number_in_answer_ok(tmp_path: Path, text: str) -> None:
    ck = run(make_job(tmp_path, answers=answer(text)))
    assert by_name(ck, "numbers_consistent")["ok"], by_name(ck, "numbers_consistent")["detail"]


def test_number_changed_in_answer_is_hard(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, answers=answer(
        "At Acme I shipped a React and TypeScript dashboard used by 45 analysts to review reconciliation breaks.")))
    chk = by_name(ck, "numbers_consistent")
    assert chk["ok"] is False and "answers.json#0" in chk["detail"] and "45" in chk["detail"]


def test_number_changed_in_outreach_is_hard(tmp_path: Path) -> None:
    out = json.loads(json.dumps(OUTREACH))
    out["drafts"][0]["email"]["body"] = ("I built a FastAPI service that ingests Kafka order events into "
                                         "PostgreSQL, processing 2.5M events per day.")
    ck = run(make_job(tmp_path, outreach=out))
    chk = by_name(ck, "numbers_consistent")
    assert chk["ok"] is False and "outreach.json#0" in chk["detail"]


def test_abbreviated_number_is_equal(tmp_path: Path) -> None:
    out = json.loads(json.dumps(OUTREACH))
    out["drafts"][0]["linkedin_note"] = ("I built a FastAPI service that ingests Kafka order events into "
                                         "PostgreSQL, processing 2M events per day.")
    ck = run(make_job(tmp_path, outreach=out))
    assert by_name(ck, "numbers_consistent")["ok"], by_name(ck, "numbers_consistent")["detail"]


@pytest.mark.parametrize("text", [
    "At Acme I shipped a React and TypeScript dashboard used by dozens of analysts to review reconciliation breaks.",
    "At Acme I shipped a React and TypeScript dashboard used by nearly 40 analysts to review reconciliation breaks.",
])
def test_paraphrased_number_is_soft(tmp_path: Path, text: str) -> None:
    ck = run(make_job(tmp_path, answers=answer(text)))
    assert by_name(ck, "numbers_consistent")["ok"]
    chk = by_name(ck, "numbers_paraphrased")
    assert chk["ok"] is False and chk["level"] == "soft" and "acme.2" in chk["detail"]
    assert ck.extras["consistency"]["number_paraphrases"][0]["id"] == "acme.2"


def test_unrelated_sentence_numbers_ignored(tmp_path: Path) -> None:
    # a sentence with little overlap with the bullet is not attributed to it
    ck = run(make_job(tmp_path, answers=answer("I read 45 books last year and I enjoy analysts' reports.")))
    assert by_name(ck, "numbers_consistent")["ok"]


def _percent_root(tmp_path: Path) -> tuple[Path, dict]:
    root = make_temp_root(tmp_path / "repo")
    prof = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    prof["experience"][0]["bullets"].append({
        "id": "acme.5", "metrics": ["40%"],
        "text": "Cut nightly reconciliation runtime by 40% by batching PostgreSQL writes in the settlement job"})
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(prof, sort_keys=False))
    return root, prof


@pytest.mark.parametrize("phrase,hard_ok,soft_fail", [
    ("by 40%", True, False),
    ("by 45%", False, False),
    ("by nearly half", True, True),
])
def test_percent_consistency(tmp_path: Path, phrase: str, hard_ok: bool, soft_fail: bool) -> None:
    root, prof = _percent_root(tmp_path)
    text = f"At Acme I cut nightly reconciliation runtime {phrase} by batching PostgreSQL writes in the settlement job."
    ck = run(make_job(tmp_path, root=root, profile=prof, resume_ids=RESUME_IDS + ["acme.5"],
                      answers=answer(text, ids=("acme.5",))))
    assert by_name(ck, "numbers_consistent")["ok"] is hard_ok
    assert ("numbers_paraphrased" in names(ck) and not by_name(ck, "numbers_paraphrased")["ok"]) is soft_fail


def test_bullet_not_on_resume_uses_profile_reference(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, answers=answer(
        "At Initech I profiled data quality and documented lineage across 31 SQL tables with Python checks.",
        ids=("initech_intern.2",))))
    chk = by_name(ck, "numbers_consistent")
    assert chk["ok"] is False
    assert ck.extras["consistency"]["number_mismatches"][0]["reference"] == "profile"


def test_min_overlap_config(tmp_path: Path) -> None:
    root = make_temp_root(tmp_path / "repo")
    qa = yaml.safe_load((root / "config" / "qa.yaml").read_text())
    qa["consistency"] = {"min_overlap": 12}
    (root / "config" / "qa.yaml").write_text(yaml.safe_dump(qa))
    ck = run(make_job(tmp_path, root=root, answers=answer(
        "At Acme I shipped a React dashboard used by 45 analysts.")))
    assert by_name(ck, "numbers_consistent")["ok"]  # too little overlap to attribute at 12 words
    assert ck.extras["consistency"]["config"]["min_overlap"] == 12
