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
from careeros.qa_ext.consistency import check_cross_doc, parse_numbers

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


# --- review fixes (#22) -----------------------------------------------------------------------------

ACME1 = ("At Acme I built a FastAPI service in Python that ingests Kafka order events into PostgreSQL, "
         "processing 2 million events per day.")


def _cover_with(sentence: str, facts: list[str] | None = None) -> str:
    cover = COVER_LETTER.replace(ACME1, sentence)
    for f in facts or []:
        cover = cover.replace("facts_used:\n", f'facts_used:\n  - {{fact: "{f}", source: posting}}\n', 1)
    return cover


def test_company_number_in_other_clause_is_not_compared(tmp_path: Path) -> None:
    sentence = ("Your platform ingests 40 million order events per day, and at Acme I built a FastAPI service in "
                "Python that ingests Kafka order events into PostgreSQL, processing 2 million events per day.")
    chk = by_name(run(make_job(tmp_path, cover=_cover_with(sentence))), "numbers_consistent")
    assert chk["ok"], chk["detail"]


def test_mismatch_in_bullet_clause_still_fails(tmp_path: Path) -> None:
    sentence = ("Your platform ingests 40 million order events per day, and at Acme I built a FastAPI service in "
                "Python that ingests Kafka order events into PostgreSQL, processing 3 million events per day.")
    chk = by_name(run(make_job(tmp_path, cover=_cover_with(sentence))), "numbers_consistent")
    assert chk["ok"] is False and "3 million" in chk["detail"] and "40 million" not in chk["detail"]


def test_number_from_facts_used_is_ignored(tmp_path: Path) -> None:
    sentence = ("Like your platform, which handles 40 million order events per day, at Acme I built a FastAPI "
                "service in Python that ingests Kafka order events into PostgreSQL, processing 2 million events per day.")
    chk = by_name(run(make_job(tmp_path, cover=_cover_with(sentence))), "numbers_consistent")
    assert chk["ok"] is False  # without the fact, 40 million is read as a restatement of the bullet
    cover = _cover_with(sentence, facts=["The platform handles 40 million order events per day"])
    chk = by_name(run(make_job(tmp_path / "b", cover=cover)), "numbers_consistent")
    assert chk["ok"], chk["detail"]


def test_number_from_posting_text_is_ignored(tmp_path: Path) -> None:
    sentence = ("Like your platform, which handles 40 million order events per day, at Acme I built a FastAPI "
                "service in Python that ingests Kafka order events into PostgreSQL, processing 2 million events per day.")
    ck = make_job(tmp_path, cover=_cover_with(sentence))
    ck.posting = {"company": "Ledgerline", "title": "Software Engineer, Backend",
                  "description_text": "Our ledger ingests 40 million order events per day."}
    chk = by_name(run(ck), "numbers_consistent")
    assert chk["ok"], chk["detail"]


def test_list_form_outreach_is_checked(tmp_path: Path) -> None:
    drafts = json.loads(json.dumps(OUTREACH["drafts"]))
    drafts[0]["linkedin_note"] = ("I built a FastAPI service that ingests Kafka order events into PostgreSQL, "
                                  "processing 5 million events per day.")
    ck = run(make_job(tmp_path, outreach=drafts))
    chk = by_name(ck, "numbers_consistent")
    assert chk["ok"] is False and "outreach.json#0" in chk["detail"]


def test_list_form_outreach_title_is_checked(tmp_path: Path) -> None:
    drafts = json.loads(json.dumps(OUTREACH["drafts"]))
    drafts[0]["linkedin_note"] = "Hi Jane, I'm a Senior Software Engineer at Acme."
    chk = by_name(run(make_job(tmp_path, outreach=drafts)), "employer_title_consistent")
    assert chk["ok"] is False and "outreach.json#0" in chk["detail"]


def test_top_level_followups_are_checked(tmp_path: Path) -> None:
    out = json.loads(json.dumps(OUTREACH))
    out["followups"] = [{"contact": "Jane Doe", "kind": "post_interview_thanks", "bullet_ids": ["acme.1"],
                         "email": {"subject": "Thanks", "body": "Thanks again. I built a FastAPI service that "
                                   "ingests Kafka order events into PostgreSQL, processing 9 million events per day."}}]
    ck = run(make_job(tmp_path, outreach=out))
    chk = by_name(ck, "numbers_consistent")
    assert chk["ok"] is False and "followups" in chk["detail"]


# --- **bold** markers in bullet text never change the comparison -----------------------------------------

def _marked_profile() -> dict:
    prof = json.loads(json.dumps(PROFILE))
    b = prof["experience"][0]["bullets"][0]
    assert b["id"] == "acme.1"
    b["text"] = ("Built a **FastAPI** service in **Python** that ingests **Kafka** order events into **PostgreSQL**, "
                 "processing **2 million** events per day")
    return prof


def test_marked_reference_same_number_ok(tmp_path: Path) -> None:
    ck = run(make_job(tmp_path, profile=_marked_profile()))
    assert by_name(ck, "numbers_consistent")["ok"], by_name(ck, "numbers_consistent")["detail"]


def test_marked_reference_changed_number_is_hard_and_plain(tmp_path: Path) -> None:
    cover = COVER_LETTER.replace("processing 2 million events per day.", "processing 3 million events per day.")
    ck = run(make_job(tmp_path, cover=cover, profile=_marked_profile()))
    chk = by_name(ck, "numbers_consistent")
    assert chk["ok"] is False and "acme.1" in chk["detail"] and "2 million" in chk["detail"]
    assert "**" not in chk["detail"]


# --- hedged bullet numbers --------------------------------------------------------------------------
def _hedged_root(tmp_path: Path, bullet_phrase: str) -> tuple[Path, dict]:
    root = make_temp_root(tmp_path / "repo")
    prof = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    prof["experience"][0]["bullets"].append({
        "id": "acme.6",
        "text": f"Deployed the reconciliation dashboard to production {bullet_phrase} of joining, running on Kubernetes"})
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(prof, sort_keys=False))
    return root, prof


def _hedged_job(tmp_path: Path, bullet_phrase: str, restated: str) -> Checker:
    root, prof = _hedged_root(tmp_path, bullet_phrase)
    text = f"At Acme I deployed the reconciliation dashboard to production {restated}, running on Kubernetes."
    return run(make_job(tmp_path, root=root, profile=prof, resume_ids=RESUME_IDS + ["acme.6"],
                        answers=answer(text, ids=("acme.6",))))


@pytest.mark.parametrize("restated", ["in about 2 months", "within roughly 2 months"])
def test_hedge_copied_from_bullet_is_not_a_paraphrase(tmp_path: Path, restated: str) -> None:
    # the bullet itself says "about 2 months": repeating that hedge is the bullet's own wording
    ck = _hedged_job(tmp_path, "within about 2 months", restated)
    assert by_name(ck, "numbers_consistent")["ok"]
    assert "numbers_paraphrased" not in names(ck), by_name(ck, "numbers_paraphrased")["detail"]


def test_hedging_an_exact_bullet_number_still_warns_and_names_the_hedge(tmp_path: Path) -> None:
    ck = _hedged_job(tmp_path, "within 2 months", "in about 2 months")
    chk = by_name(ck, "numbers_paraphrased")
    assert chk["ok"] is False and "'about 2'" in chk["detail"]
    assert ck.extras["consistency"]["number_paraphrases"][0]["found"] == "about 2"


def test_hedged_bullet_with_changed_number_is_still_hard(tmp_path: Path) -> None:
    ck = _hedged_job(tmp_path, "within about 2 months", "in about 3 months")
    assert by_name(ck, "numbers_consistent")["ok"] is False


@pytest.mark.parametrize("text", ["AWS (Glue, Athena, S3)", "EC2 and K8s", "Web3 and OAuth2", "TLS1.3", "v2.3 API",
                                  "Python3.12", "OAuth2.0", "H100 GPUs"])
def test_product_names_are_flagged_glued(text: str) -> None:
    nums = parse_numbers(text)
    assert nums and all(p["glued"] for p in nums)


@pytest.mark.parametrize("text,value", [("ran on 3 nodes", 3.0), ("Python 3.12", 3.12), ("cut latency 10x", 10.0),
                                        ("2M events", 2_000_000.0)])
def test_plain_numbers_still_parse(text: str, value: float) -> None:
    assert [p["value"] for p in parse_numbers(text)] == [value]


# --- review fixes (#25) -----------------------------------------------------------------------------
@pytest.mark.parametrize("text,value", [("sub-100ms latency", 100.0), ("cut p99 latency", 99.0),
                                        ("top-10 customers", 10.0), ("Top-5 accounts", 5.0)])
def test_metric_compounds_still_parse(text: str, value: float) -> None:
    assert [p["value"] for p in parse_numbers(text)] == [value]




def _metric_job(tmp_path: Path, bullet: str, restated: str) -> Checker:
    root = make_temp_root(tmp_path / "repo")
    prof = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    prof["experience"][0]["bullets"].append({"id": "acme.7", "text": bullet})
    (root / "profile" / "master.yaml").write_text(yaml.safe_dump(prof, sort_keys=False))
    out = json.loads(json.dumps(OUTREACH))
    out["drafts"][0]["email"]["body"] = restated
    out["drafts"][0]["bullet_ids"] = ["acme.7"]
    return run(make_job(tmp_path, root=root, profile=prof, resume_ids=RESUME_IDS + ["acme.7"], outreach=out))


@pytest.mark.parametrize("bullet,restated", [
    ("Cut checkout p99 latency by 40ms for the payments API at Acme",
     "At Acme I cut checkout p95 latency by 40ms for the payments API."),
    ("Cut checkout API latency to sub-100ms for payments at Acme",
     "At Acme I cut checkout API latency to sub-500ms for payments."),
])
def test_changed_metric_compound_in_outreach_is_hard(tmp_path: Path, bullet: str, restated: str) -> None:
    chk = by_name(_metric_job(tmp_path, bullet, restated), "numbers_consistent")
    assert chk["ok"] is False and "outreach.json" in chk["detail"]


@pytest.mark.parametrize("bullet_phrase,restated", [
    ("up to 40%", "over 40%"),        # upper bound restated as a lower bound: inflated
    ("over 40%", "under 40%"),
    ("about 40%", "over 40%"),        # approximate restated as a floor
])
def test_flipped_hedge_still_warns(tmp_path: Path, bullet_phrase: str, restated: str) -> None:
    b = f"Cut nightly reconciliation runtime by {bullet_phrase} by batching PostgreSQL writes in the settlement job"
    r = f"At Acme I cut nightly reconciliation runtime by {restated} by batching PostgreSQL writes in the settlement job."
    ck = _metric_job(tmp_path, b, r)
    assert by_name(ck, "numbers_consistent")["ok"]
    assert by_name(ck, "numbers_paraphrased")["ok"] is False


@pytest.mark.parametrize("bullet_phrase,restated", [("about 40%", "roughly 40%"), ("up to 40%", "up to 40%"),
                                                     ("over 40%", "more than 40%"), ("~40%", "about 40%")])
def test_same_class_hedge_is_silent(tmp_path: Path, bullet_phrase: str, restated: str) -> None:
    b = f"Cut nightly reconciliation runtime by {bullet_phrase} by batching PostgreSQL writes in the settlement job"
    r = f"At Acme I cut nightly reconciliation runtime by {restated} by batching PostgreSQL writes in the settlement job."
    ck = _metric_job(tmp_path, b, r)
    assert by_name(ck, "numbers_consistent")["ok"]
    assert "numbers_paraphrased" not in names(ck), by_name(ck, "numbers_paraphrased")["detail"]


# --- review fixes (#25, round 2) --------------------------------------------------------------------


@pytest.mark.parametrize("text,value", [("p99.9 latency", 99.9), ("Python 3.12", 3.12)])
def test_dotted_numbers_still_parse(text: str, value: float) -> None:
    assert [p["value"] for p in parse_numbers(text)] == [value]


def test_glued_version_in_posting_does_not_excuse_changed_number(tmp_path: Path) -> None:
    root, prof = _hedged_root(tmp_path, "within 2 months")
    text = "At Acme I deployed the reconciliation dashboard to production in 3 months, running on Kubernetes."
    ck = make_job(tmp_path, root=root, profile=prof, resume_ids=RESUME_IDS + ["acme.6"],
                  answers=answer(text, ids=("acme.6",)))
    (ck.job_dir / "posting.json").write_text(json.dumps({"company": "Ledgerline", "title": "Backend Engineer",
                                                         "description_text": "Our services speak TLS1.3 only."}))
    ck = run(Checker(ck.job_dir, root))
    assert by_name(ck, "numbers_consistent")["ok"] is False


# --- review fixes (#25, round 3): the tokenizer is main's; glued numbers are only dropped from company facts ----
@pytest.mark.parametrize("text,value,kind", [("USD5M savings", 5_000_000.0, ""), ("Top5% of teams", 5.0, "%"),
                                             ("approx60% faster", 60.0, "%"), ("CAD300k budget", 300_000.0, "")])
def test_glued_quantities_still_parse(text: str, value: float, kind: str) -> None:
    [p] = parse_numbers(text)
    assert (p["value"], p["kind"]) == (value, kind)


@pytest.mark.parametrize("bullet,restated", [
    ("Saved USD 2M in annual cloud spend at Acme by rightsizing the payments cluster",
     "At Acme I saved USD5M in annual cloud spend by rightsizing the payments cluster."),
    ("Ranked in the top 1% of Acme engineers for payments incident response",
     "At Acme I ranked in the Top5% of engineers for payments incident response."),
])
def test_changed_glued_quantity_is_hard(tmp_path: Path, bullet: str, restated: str) -> None:
    chk = by_name(_metric_job(tmp_path, bullet, restated), "numbers_consistent")
    assert chk["ok"] is False


@pytest.mark.parametrize("posting", ["We store reports in AWS S3.", "EC2 fleet", "Our services speak TLS1.3 only."])
def test_glued_product_numbers_are_not_company_facts(tmp_path: Path, posting: str) -> None:
    root, prof = _hedged_root(tmp_path, "within 2 months")
    restated = "3" if "S3" in posting or "TLS" in posting else "2"
    if restated == "2":  # EC2: restate a changed 2 -> must still fail when the bullet says a different number
        root, prof = _hedged_root(tmp_path / "b", "within 4 months")
    text = f"At Acme I deployed the reconciliation dashboard to production in {restated} months, running on Kubernetes."
    ck = make_job(tmp_path / "j", root=root, profile=prof, resume_ids=RESUME_IDS + ["acme.6"],
                  answers=answer(text, ids=("acme.6",)))
    (ck.job_dir / "posting.json").write_text(json.dumps({"company": "Ledgerline", "title": "Backend Engineer",
                                                         "description_text": posting}))
    assert by_name(run(Checker(ck.job_dir, root)), "numbers_consistent")["ok"] is False


# --- review fixes (#25, round 4): currency / hedge-glued amounts in the posting are still company facts ------
@pytest.mark.parametrize("text,glued", [("USD5M", False), ("EUR2M", False), ("CAD300k", False), ("Top5%", False),
                                        ("approx60%", False), ("USD5000", False), ("S3", True), ("EC2", True),
                                        ("TLS1.3", True), ("H100", True)])
def test_glued_flag_is_only_for_product_names(text: str, glued: bool) -> None:
    [p] = parse_numbers(text)
    assert p["glued"] is glued


@pytest.mark.parametrize("posting,bullet,restated", [
    ("We manage USD5M in annual cloud spend.",
     "Saved USD 2M in annual cloud spend at Acme by rightsizing the payments cluster",
     "At Acme I saved USD 2M in annual cloud spend by rightsizing the payments cluster, useful for a team "
     "managing USD 5M in cloud spend."),
    ("Nightly settlement runtime grew approx60% last year.",
     "Cut nightly settlement runtime by 40% by batching PostgreSQL writes at Acme",
     "At Acme I cut nightly settlement runtime by 40% by batching PostgreSQL writes; your settlement runtime "
     "grew 60%."),
])
def test_currency_glued_posting_amount_is_a_company_fact(tmp_path: Path, posting: str, bullet: str,
                                                          restated: str) -> None:
    ck = _metric_job(tmp_path, bullet, restated)
    (ck.job_dir / "posting.json").write_text(json.dumps({"company": "Ledgerline", "title": "Backend Engineer",
                                                         "description_text": posting}))
    chk = by_name(run(Checker(ck.job_dir, ck.root)), "numbers_consistent")
    assert chk["ok"], chk["detail"]


# --- review fixes (#25, round 5): non-ASCII letters before a digit never crash -------------------------------
@pytest.mark.parametrize("text", ["β2 service", "経験3年以上", "Zürich office, café3 perks"])
def test_non_ascii_letter_before_digit_does_not_crash(text: str) -> None:
    parse_numbers(text)


def test_non_ascii_posting_runs_cross_doc(tmp_path: Path) -> None:
    ck = make_job(tmp_path)
    (ck.job_dir / "posting.json").write_text(json.dumps({"company": "Ledgerline", "title": "Backend Engineer",
                                                         "description_text": "Tokyo team: 経験3年以上, café3 perks"}))
    run(Checker(ck.job_dir, EXAMPLE_REPO))
