"""Unit tests for careeros.qa deterministic checks (fixture repo: fake candidate Alex Example)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO, FIXTURES

from careeros.qa import ProfileIndex, collect_ids, number_tokens, run_deterministic, split_frontmatter
from careeros.qa import main as qa_main

pytestmark = pytest.mark.unit

ROOT = EXAMPLE_REPO

RESUME_TXT = """Alex Example
Springfield, NY | 555-010-0199 | alex@example.com
https://linkedin.com/in/alex-example | https://github.com/alex-example

EXPERIENCE
Acme | Jun 2026 - Present
Software Engineer | New York, NY
- Built a FastAPI service in Python that ingests Kafka order events into PostgreSQL, processing 2 million events per day
- Shipped a React and TypeScript dashboard used by 40 analysts to review reconciliation breaks
- Containerized three services with Docker and deployed them to AWS

Initech | Jun 2025 - Aug 2025
Data Engineering Intern | Boston, MA
- Wrote 12 Airflow DAGs in Python moving SQL reports into a warehouse, cutting manual prep by 5 hours per week

PROJECTS
Widgetizer | Nov 2025
Swift, SwiftUI, Supabase
- Built an iOS app in Swift and SwiftUI with a Supabase backend, reaching 300 beta users

EDUCATION
Springfield State University | Aug 2022 - May 2026
Bachelor of Science, Computer Science, GPA 3.6

SKILLS
Programming: Python, SQL, TypeScript, Swift
Tools & Platforms: PostgreSQL, Kafka, Docker, AWS, Airflow, Git
"""

RESUME_JSON = {
    "experience": [
        {"id": "acme", "bullets": [{"id": "acme.1"}, {"id": "acme.2"}, {"id": "acme.3"}]},
        {"id": "initech_intern", "bullets": [{"id": "initech_intern.1"}]},
    ],
    "projects": [{"id": "widgetizer", "bullets": [{"id": "widgetizer.1"}]}],
    "education": [{"id": "state_u"}],
    "meta": {"job_id": "t1", "category": "swe_backend"},
}

COVER_LETTER = """---
company: Ledgerline
role: Software Engineer, Backend
word_count: 100
facts_used:
  - {fact: "Payments Platform team owns the double-entry ledger and settlement engine", source: posting}
  - {fact: "ETL jobs on AWS (Glue, Athena, S3) feed customer reporting", source: posting}
bullet_ids_used: [acme.1, initech_intern.1, widgetizer.1]
narrative_ids_used: [n.data]
voice_verified: false
---
Hi Payments Platform team,

Your posting says the Payments Platform team owns the double-entry ledger and the settlement engine that reconciles card-network files every night. The Software Engineer, Backend role at Ledgerline is the closest match to the work I do now.

At Acme I built a FastAPI service in Python that ingests Kafka order events into PostgreSQL, processing 2 million events per day. Before that, at Initech, I wrote 12 Airflow DAGs moving SQL reports into a warehouse and cut manual prep by 5 hours per week. Both jobs were about the data being right, not just present.

Outside work I built Widgetizer, an iOS app in Swift with a Supabase backend that reached 300 beta users. I like making messy data trustworthy, and a ledger is where that matters most.

Happy to walk through the code.

Alex
"""


def make_job(tmp_path: Path, resume_txt: str = RESUME_TXT, cover: str | None = COVER_LETTER,
             required=("Python", "SQL", "AWS", "PostgreSQL", "Docker"), answers=None) -> Path:
    job = tmp_path / "jobs" / "t1"
    job.mkdir(parents=True)
    posting = json.loads((FIXTURES / "example_posting.json").read_text())
    posting["job_id"] = "t1"
    (job / "posting.json").write_text(json.dumps(posting))
    (job / "score.json").write_text(json.dumps({"category": "swe_backend", "required_skills": list(required)}))
    (job / "resume.json").write_text(json.dumps(RESUME_JSON))
    (job / "resume.txt").write_text(resume_txt)
    if cover is not None:
        (job / "cover_letter.md").write_text(cover)
    (job / "answers.json").write_text(json.dumps(answers if answers is not None else [
        {"question": "Are you authorized to work?", "answer": "Yes", "type": "standard",
         "standard_key": "work_authorization", "bullet_ids": [], "needs_review": False}]))
    return job


def run(job: Path) -> dict:
    return run_deterministic(job, root=ROOT)


def by_name(result: dict, name: str) -> dict:
    for c in result["checks"]:
        if c["check"] == name:
            return c
    raise AssertionError(f"check {name} not in {[c['check'] for c in result['checks']]}")


# --- pass case -------------------------------------------------------------------

def test_pass_case(tmp_path: Path) -> None:
    res = run(make_job(tmp_path))
    assert res["fail_reasons"] == [], res["fail_reasons"]
    assert res["pass"] is True
    for name in ("truth_trace", "number_audit:resume.txt", "number_audit:cover_letter.md", "tool_audit",
                 "contact_intact:resume.txt", "banned_phrases", "cover_letter_word_count",
                 "cover_letter_company_facts", "cover_letter_names_company", "cover_letter_names_role"):
        assert by_name(res, name)["ok"], (name, by_name(res, name)["detail"])
    assert res["keyword_coverage"] == 1.0
    assert by_name(res, "voice_verified")["ok"] is False  # soft only


# --- banned phrases --------------------------------------------------------------

@pytest.mark.parametrize("phrase", ["I am excited to apply.", "We leveraged Kafka.", "Dear Hiring Manager"])
def test_banned_phrase_fails(tmp_path: Path, phrase: str) -> None:
    cover = COVER_LETTER.replace("Happy to walk through the code.", f"{phrase} Happy to walk through the code.")
    res = run(make_job(tmp_path, cover=cover))
    assert res["pass"] is False and not by_name(res, "banned_phrases")["ok"]
    assert res["banned_hits"][0]["file"] == "cover_letter.md"


def test_banned_phrase_word_boundary(tmp_path: Path) -> None:
    # "dynamic" is banned; "dynamically" / "leverages" substrings inside other words must not hit
    cover = COVER_LETTER.replace("Happy to walk", "It scales dynamically. Happy to walk")
    assert by_name(run(make_job(tmp_path, cover=cover)), "banned_phrases")["ok"]


def test_banned_phrase_in_answers(tmp_path: Path) -> None:
    job = make_job(tmp_path, answers=[{"question": "Why us", "answer": "I am thrilled by payments.", "type": "essay"}])
    assert {"file": "answers.json", "phrase": "thrilled"} in run(job)["banned_hits"]


# --- word counts -----------------------------------------------------------------

def _cover_with_words(n: int) -> str:
    fm, _ = COVER_LETTER.split("---\nHi", 1)
    body = "Hi Ledgerline Software Engineer " + " ".join(["word"] * (n - 4))
    return fm + "---\n" + body + "\n"


@pytest.mark.parametrize("n,ok", [(119, False), (120, True), (250, True), (251, False)])
def test_cover_letter_word_bounds(tmp_path: Path, n: int, ok: bool) -> None:
    res = run(make_job(tmp_path, cover=_cover_with_words(n)))
    chk = by_name(res, "cover_letter_word_count")
    assert chk["ok"] is ok and res["cover_letter_word_count"] == n
    assert f"{n} words" in chk["detail"]


def test_frontmatter_word_count_is_ignored(tmp_path: Path) -> None:
    res = run(make_job(tmp_path, cover=COVER_LETTER.replace("word_count: 100", "word_count: 999")))
    assert res["pass"] is True and res["cover_letter_word_count"] != 999


def test_answer_char_limit(tmp_path: Path) -> None:
    job = make_job(tmp_path, answers=[{"question": "Why", "answer": "x" * 51, "char_limit": 50, "type": "standard"}])
    chk = by_name(run(job), "answers_within_char_limit")
    assert chk["ok"] is False and "51>50" in chk["detail"]


# --- em dashes -------------------------------------------------------------------

@pytest.mark.parametrize("n,ok", [(2, True), (3, False)])
def test_em_dash_limit(tmp_path: Path, n: int, ok: bool) -> None:
    cover = COVER_LETTER.replace("Happy to walk", "a — " * n + "Happy to walk")
    res = run(make_job(tmp_path, cover=cover))
    chk = by_name(res, "em_dashes:cover_letter.md")
    assert chk["ok"] is ok and chk["level"] == "soft"
    assert res["pass"] is True  # soft rule never blocks


# --- truth trace -----------------------------------------------------------------

def _with_resume_ids(job: Path, extra: list[str]) -> Path:
    rj = json.loads((job / "resume.json").read_text())
    rj["experience"][0]["bullets"] += [{"id": i} for i in extra]
    (job / "resume.json").write_text(json.dumps(rj))
    return job


def test_truth_trace_unknown_id(tmp_path: Path) -> None:
    res = run(_with_resume_ids(make_job(tmp_path), ["acme.99"]))
    chk = by_name(res, "truth_trace")
    assert res["pass"] is False and "unknown id 'acme.99'" in chk["detail"]


def test_truth_trace_placeholder_id(tmp_path: Path) -> None:
    res = run(_with_resume_ids(make_job(tmp_path), ["acme.4"]))
    assert res["pass"] is False and "placeholder bullet 'acme.4'" in by_name(res, "truth_trace")["detail"]


def test_truth_trace_cover_letter_ids(tmp_path: Path) -> None:
    res = run(make_job(tmp_path, cover=COVER_LETTER.replace("[n.data]", "[n.invented]")))
    assert "cover_letter.md: unknown id 'n.invented'" in by_name(res, "truth_trace")["detail"]
    cover = COVER_LETTER.replace("bullet_ids_used: [acme.1, initech_intern.1, widgetizer.1]\n", "").replace(
        "narrative_ids_used: [n.data]\n", "")
    res = run(make_job(tmp_path / "b", cover=cover))
    assert not by_name(res, "cover_letter_cites_ids")["ok"]


def test_profile_index_placeholder_markers() -> None:
    idx = ProfileIndex({"experience": [{"id": "x", "bullets": [
        {"id": "x.1", "text": "[OPEN: add later]"}, {"id": "x.2", "text": "[FILL IN metric]"},
        {"id": "x.3", "text": "ok", "placeholder": True}, {"id": "x.4", "text": "Built an open API"}]}]})
    assert [idx.is_placeholder(f"x.{i}") for i in range(1, 5)] == [True, True, True, False]
    assert not idx.is_placeholder("missing")


def test_profile_index_variant_text_counts() -> None:
    """master.yaml stores variants as a mapping ({short: ...}); their text (not the key) must be traceable."""
    idx = ProfileIndex({"experience": [{"id": "x", "bullets": [
        {"id": "x.1", "text": "Built a dashboard", "variants": {"short": "Built a Grafana dashboard for 7 teams"}},
        {"id": "x.2", "text": "Wrote docs", "variants": ["Wrote 3 runbooks"]}]}]})
    assert "Grafana" in idx.bullet_text("x.1") and "7 teams" in idx.bullet_text("x.1")
    assert "short" not in idx.bullet_text("x.1").split()
    assert "3 runbooks" in idx.bullet_text("x.2")


def test_collect_ids_shapes() -> None:
    obj = {"experience": [{"bullet_ids": ["a.1"]}, {"bullets": [{"id": "a.2"}, "a.3"]}],
           "meta": {"narrative_ids": ["n.x"], "extra_ids": ["e.1"]}}
    assert collect_ids(obj) == {"a.1", "a.2", "a.3", "n.x", "e.1"}


# --- number audit ----------------------------------------------------------------

def test_number_audit_orphan_in_resume(tmp_path: Path) -> None:
    res = run(make_job(tmp_path, resume_txt=RESUME_TXT.replace("40 analysts", "400 analysts")))
    assert res["pass"] is False
    assert "400" in by_name(res, "number_audit:resume.txt")["detail"]
    assert {"file": "resume.txt", "number": "400"} in res["orphan_numbers"]


def test_number_audit_orphan_in_cover_letter_but_posting_numbers_allowed(tmp_path: Path) -> None:
    # $40B and 300+ come from the posting text -> allowed; 17% is invented -> orphan
    cover = COVER_LETTER.replace("Happy to walk", "You process $40B for 300+ customers. I cut costs 17%. Happy to walk")
    res = run(make_job(tmp_path, cover=cover))
    assert [o["number"] for o in res["orphan_numbers"]] == ["17%"]


def test_number_audit_uncited_bullet_number_is_orphan(tmp_path: Path) -> None:
    # 15 (widgetizer.2) exists in the profile but that bullet is not cited by resume.json
    txt = RESUME_TXT.replace("reaching 300 beta users", "reaching 300 beta users with 15 XCTest suites")
    res = run(make_job(tmp_path, resume_txt=txt))
    assert {"file": "resume.txt", "number": "15"} in res["orphan_numbers"]


def test_number_audit_skips_standard_answers(tmp_path: Path) -> None:
    job = make_job(tmp_path, answers=[
        {"question": "Years?", "answer": "1", "type": "standard"},
        {"question": "Tell us", "answer": "I shipped 99 features.", "type": "essay", "bullet_ids": ["acme.1"]}])
    res = run(job)
    assert [o["number"] for o in res["orphan_numbers"]] == ["99"]


def test_number_tokens() -> None:
    assert number_tokens("Managed 1,000+ records, 20%. $5,000 prize, 12K LOC, 0-100%") == {
        "1,000+", "20%", "$5,000", "12k", "0", "100%"}


# --- tool audit ------------------------------------------------------------------

def test_tool_audit_unknown_tool(tmp_path: Path) -> None:
    res = run(make_job(tmp_path, resume_txt=RESUME_TXT.replace("Programming: Python", "Programming: Rust, Python")))
    assert res["pass"] is False and res["unknown_tools"] == ["Rust"]


def test_tool_audit_tool_only_in_uncited_bullet(tmp_path: Path) -> None:
    # XCTest is in profile skills -> allowed even though widgetizer.2 is not cited
    txt = RESUME_TXT.replace("Tools & Platforms: PostgreSQL", "Tools & Platforms: XCTest, PostgreSQL")
    assert by_name(run(make_job(tmp_path, resume_txt=txt)), "tool_audit")["ok"]


def test_tool_audit_allowlist(tmp_path: Path) -> None:
    txt = RESUME_TXT.replace("Software Engineer | New York, NY", "Software Engineer | New York, NY (Remote, Hybrid) CI/CD")
    res = run(make_job(tmp_path, resume_txt=txt))
    assert by_name(res, "tool_audit")["ok"], res["unknown_tools"]


def test_tool_audit_sentence_start_ignored(tmp_path: Path) -> None:
    txt = RESUME_TXT + "\n- Mentored two peers. Terraform is not claimed here? No: Terraform appears mid-sentence\n"
    res = run(make_job(tmp_path, resume_txt=txt))
    assert "Mentored" not in res["unknown_tools"] and "Terraform" in res["unknown_tools"]


# --- keyword coverage ------------------------------------------------------------

def test_keyword_coverage_word_boundaries_and_resume_only(tmp_path: Path) -> None:
    job = make_job(tmp_path, required=["Go", "Ruby", "SQL", "Python", "Kafka"])
    rj = json.loads((job / "resume.json").read_text())
    rj["meta"] = {"missing_terms": ["Go", "Ruby"], "keyword_mirror": {"Ruby": "nowhere"}}
    (job / "resume.json").write_text(json.dumps(rj))
    res = run(job)
    chk = by_name(res, "keyword_coverage")
    # "Go" must not match "governance"/"Google"; resume.json meta never counts
    assert res["keyword_coverage"] == 0.6, chk["detail"]
    assert "missing: Go, Ruby" in chk["detail"]


def test_keyword_coverage_cover_letter_mentions_not_counted(tmp_path: Path) -> None:
    cover = COVER_LETTER.replace("Happy to walk", "I haven't used Go or Ruby in production yet. Happy to walk")
    res = run(make_job(tmp_path, cover=cover, required=["Go", "Ruby", "SQL", "Python", "Kafka"]))
    chk = by_name(res, "keyword_coverage")
    assert res["keyword_coverage"] == 0.6
    assert set(res["cover_letter_mentions"]) == {"Go", "Ruby", "SQL", "Python", "Kafka"}
    assert "mentioned only in cover letter (not counted): Go, Ruby" in chk["detail"]


@pytest.mark.parametrize("skill,present", [("C++", False), ("Next.js", False), ("postgresql", True),
                                           ("Type Script", True), ("Air-flow", False)])
def test_keyword_coverage_variants(tmp_path: Path, skill: str, present: bool) -> None:
    res = run(make_job(tmp_path, required=[skill]))
    assert res["keyword_coverage"] == (1.0 if present else 0.0)


def test_keyword_coverage_below_min_is_soft(tmp_path: Path) -> None:
    res = run(make_job(tmp_path, required=["Go", "Rust", "Scala", "Python"]))
    assert not by_name(res, "keyword_coverage")["ok"] and res["pass"] is True


# --- contact ---------------------------------------------------------------------

@pytest.mark.parametrize("old,new,missing", [
    ("alex@example.com", "alex@exmaple.com", "email"),
    ("https://github.com/alex-example", "", "github"),
    ("Alex Example\n", "A. Example\n", "name"),
    ("555-010-0199", "555-010-0198", "phone"),
])
def test_contact_intact_fails(tmp_path: Path, old: str, new: str, missing: str) -> None:
    res = run(make_job(tmp_path, resume_txt=RESUME_TXT.replace(old, new, 1)))
    chk = by_name(res, "contact_intact:resume.txt")
    assert chk["ok"] is False and missing in chk["detail"]


def test_contact_intact_tolerates_formatting(tmp_path: Path) -> None:
    txt = RESUME_TXT.replace("555-010-0199", "(555) 010 0199").replace("https://linkedin.com", "www.linkedin.com")
    assert by_name(run(make_job(tmp_path, resume_txt=txt)), "contact_intact:resume.txt")["ok"]


# --- pdf -------------------------------------------------------------------------

def _blank_pdf(path: Path, pages: int) -> None:
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=612, height=792)
    with path.open("wb") as f:
        w.write(f)


def test_pdf_page_count_and_contact(tmp_path: Path) -> None:
    job = make_job(tmp_path)
    _blank_pdf(job / "resume.pdf", 2)
    res = run(job)
    assert not by_name(res, "pdf_page_count")["ok"] and "2 page(s) (max 1)" in by_name(res, "pdf_page_count")["detail"]
    assert not by_name(res, "contact_intact:resume.pdf")["ok"]  # blank page has no text
    _blank_pdf(job / "resume.pdf", 1)
    assert by_name(run(job), "pdf_page_count")["ok"]


def test_pdf_missing_is_skipped(tmp_path: Path) -> None:
    chk = by_name(run(make_job(tmp_path)), "pdf")
    assert chk["ok"] and chk["skipped"]


# --- structure / robustness ------------------------------------------------------

def test_cover_letter_must_name_company_and_role(tmp_path: Path) -> None:
    cover = COVER_LETTER.replace("The Software Engineer, Backend role at Ledgerline is", "This role is")
    res = run(make_job(tmp_path, cover=cover))
    assert not by_name(res, "cover_letter_names_role")["ok"] and not by_name(res, "cover_letter_names_company")["ok"]


def test_cover_letter_needs_two_facts_and_no_questions(tmp_path: Path) -> None:
    cover = COVER_LETTER.replace(
        '  - {fact: "ETL jobs on AWS (Glue, Athena, S3) feed customer reporting", source: posting}\n', "")
    cover = cover.replace("Happy to walk through the code.", "Want to talk?")
    res = run(make_job(tmp_path, cover=cover))
    assert not by_name(res, "cover_letter_company_facts")["ok"]
    assert not by_name(res, "no_rhetorical_questions")["ok"]


def test_missing_artifacts_graceful(tmp_path: Path) -> None:
    job = tmp_path / "jobs" / "empty"
    job.mkdir(parents=True)
    (job / "posting.json").write_text(json.dumps({"job_id": "empty", "company": "X", "title": "Y"}))
    res = run(job)
    assert res["pass"] is False  # nothing to gate: a posting-only dir never passes
    assert not by_name(res, "resume_present")["ok"]
    assert res["artifacts"]["resume.txt"] is False
    assert res["summary"]["skipped"] > 0
    assert not by_name(res, "artifacts_present")["ok"]


def test_cover_letter_and_answers_stay_optional(tmp_path: Path) -> None:
    job = make_job(tmp_path, cover=None)
    (job / "answers.json").unlink()
    res = run(job)
    assert res["pass"] is True, res["fail_reasons"]
    assert by_name(res, "resume_present")["ok"]


def test_invalid_json_is_hard_fail(tmp_path: Path) -> None:
    job = make_job(tmp_path)
    (job / "score.json").write_text("{nope")
    assert not by_name(run(job), "json_valid:score.json")["ok"]


def test_missing_job_dir(tmp_path: Path) -> None:
    res = run_deterministic(tmp_path / "nope", root=ROOT)
    assert res["pass"] is False and res["checks"][0]["check"] == "job_dir_exists"


def test_split_frontmatter() -> None:
    fm, body = split_frontmatter("---\na: 1\nb: [x, y]\n---\nHello\n")
    assert fm == {"a": 1, "b": ["x", "y"]} and body == "Hello\n"
    assert split_frontmatter("no frontmatter") == ({}, "no frontmatter")
    assert split_frontmatter("---\n: [bad\n---\nx") == ({}, "---\n: [bad\n---\nx")
    assert split_frontmatter("---\n- a list\n---\nx")[0] == {}


def test_main_exit_codes(tmp_path: Path, capsys) -> None:
    job = make_job(tmp_path, resume_txt=RESUME_TXT.replace("40 analysts", "400 analysts"))
    assert qa_main([str(job), "--root", str(ROOT)]) == 0  # report-only by default
    assert json.loads(capsys.readouterr().out)["pass"] is False
    assert qa_main([str(job), "--root", str(ROOT), "--strict"]) == 1
    capsys.readouterr()
    assert qa_main([]) == 2


# --- confidential terms (profile/confidential_terms.yaml) -----------------------------------------

def _root_with_terms(tmp_path: Path, text: str | None) -> Path:
    import shutil

    root = tmp_path / "root"
    shutil.copytree(EXAMPLE_REPO, root)
    ct = root / "profile" / "confidential_terms.yaml"
    if text is None:
        ct.unlink()
    else:
        ct.write_text(text)
    return root


def test_confidential_example_file_is_active_and_clean(tmp_path: Path) -> None:
    c = by_name(run(make_job(tmp_path)), "confidential_terms")
    assert c["ok"] and not c.get("skipped") and "3 terms, 2 patterns" in c["detail"]


@pytest.mark.parametrize("where", ["resume.txt", "cover_letter.md", "answers.json", "outreach.json"])
def test_confidential_term_fails_in_every_artifact(tmp_path: Path, where: str) -> None:
    job = make_job(tmp_path)
    leak = "Migrated the projectzebra ledger"  # case-insensitive whole word
    if where == "outreach.json":
        (job / where).write_text(json.dumps([{"contact": "Pat", "email_body": leak}]))
    elif where == "answers.json":
        (job / where).write_text(json.dumps([{"question": "Tell us", "answer": leak, "type": "essay"}]))
    else:
        (job / where).write_text((job / where).read_text() + "\n" + leak + "\n")
    res = run(job)
    c = by_name(res, "confidential_terms")
    assert c["ok"] is False and c["level"] == "hard" and res["pass"] is False
    assert res["confidential_hits"] == [f"{where}: term 'PROJECTZEBRA'"]


def test_confidential_term_is_whole_word(tmp_path: Path) -> None:
    job = make_job(tmp_path, resume_txt=RESUME_TXT + "- ledgerdemain and projectzebras are fine\n")
    assert by_name(run(job), "confidential_terms")["ok"]


def test_confidential_pattern_reported_without_the_match(tmp_path: Path) -> None:
    job = make_job(tmp_path, resume_txt=RESUME_TXT + "- Fixed ticket ACME-OPS1234 on account 9123456789\n")
    res = run(job)
    assert res["confidential_hits"] == ["resume.txt: patterns[0]", "resume.txt: patterns[1]"]
    detail = by_name(res, "confidential_terms")["detail"]
    assert "9123456789" not in detail and "ACME-OPS1234" not in detail


def test_confidential_employer_name_itself_is_allowed(tmp_path: Path) -> None:
    assert by_name(run(make_job(tmp_path)), "confidential_terms")["ok"]  # resume says "Acme" (employer)


def test_confidential_missing_file_is_skipped(tmp_path: Path) -> None:
    root = _root_with_terms(tmp_path, None)
    c = by_name(run_deterministic(make_job(tmp_path), root=root), "confidential_terms")
    assert c["ok"] and c["skipped"]


@pytest.mark.parametrize("text,msg", [
    ("terms: [unclosed\n", "cannot parse"),
    ("patterns: ['(bad']\n", "not a valid regex"),
])
def test_confidential_bad_file_fails_closed(tmp_path: Path, text: str, msg: str) -> None:
    root = _root_with_terms(tmp_path, text)
    c = by_name(run_deterministic(make_job(tmp_path), root=root), "confidential_terms")
    assert c["ok"] is False and msg in c["detail"]


def test_confidential_empty_file_passes(tmp_path: Path) -> None:
    root = _root_with_terms(tmp_path, "employer: Acme\n")
    assert by_name(run_deterministic(make_job(tmp_path), root=root), "confidential_terms")["ok"]


# --- place names come from the profile, not a hardcoded list ----------------------------------------

def test_place_words_derived_from_profile_locations() -> None:
    idx = ProfileIndex({"identity": {"location": "Springfield, NY"},
                        "experience": [{"id": "a", "location": "Gotham City, NJ"}],
                        "education": [{"id": "u", "location": "Metropolis, OH"}],
                        "projects": [{"id": "p"}]})
    assert idx.place_words() == {"springfield", "ny", "gotham", "city", "nj", "metropolis", "oh"}


def test_tool_audit_allows_profile_places_only(tmp_path: Path) -> None:
    ok = RESUME_TXT.replace("Software Engineer | New York, NY", "Software Engineer | New York, NY / Springfield / Boston")
    assert by_name(run(make_job(tmp_path, resume_txt=ok)), "tool_audit")["ok"]
    bad = RESUME_TXT.replace("Software Engineer | New York, NY", "Software Engineer | New York, NY / Gotham")
    res = run(make_job(tmp_path / "b", resume_txt=bad))
    assert res["unknown_tools"] == ["Gotham"]  # not a profile location -> not whitelisted


# --- bullet fidelity / summary / skills (resume.json text vs master.yaml) -----------------------------

def _resume_with(job: Path, **kw) -> Path:
    data = json.loads((job / "resume.json").read_text())
    data.update(kw)
    (job / "resume.json").write_text(json.dumps(data))
    return job


ACME_1 = "Built a FastAPI service in Python that ingests Kafka order events into PostgreSQL, processing 2 million events per day"


@pytest.mark.parametrize("text,ok", [
    (ACME_1, True),                                                                          # verbatim
    ("Developed a FastAPI service in Python that ingests Kafka order events into PostgreSQL", True),  # verb swap + trim
    ("Built a FastAPI service in Python that ingests Kafka order events", True),             # trailing clause trimmed
    ("Led company-wide hiring strategy and managed executive stakeholders", False),          # fabricated text, valid id
    ("Built a FastAPI service in Python that ingests Kafka order events into Redis", False), # tool swapped
    ("Built a Go service in Python that ingests Kafka order events into PostgreSQL", False),  # word changed mid-bullet
])
def test_bullet_fidelity(tmp_path: Path, text: str, ok: bool) -> None:
    job = _resume_with(make_job(tmp_path), experience=[{"id": "acme", "bullets": [{"id": "acme.1", "text": text}]}])
    assert by_name(run(job), "bullet_fidelity")["ok"] is ok


def test_bullet_fidelity_accepts_declared_variant(tmp_path: Path) -> None:
    prof = ProfileIndex(__import__("yaml").safe_load((EXAMPLE_REPO / "profile" / "master.yaml").read_text()))
    variants = {bid: b.get("variants") for bid, b in prof.bullets.items() if b.get("variants")}
    assert variants, "example profile should declare at least one variant"
    bid, v = next(iter(variants.items()))
    text = next(iter(v.values())) if isinstance(v, dict) else v[0]
    entry = prof.bullet_parent[bid]["id"]
    job = _resume_with(make_job(tmp_path), experience=[{"id": entry, "bullets": [{"id": bid, "text": text}]}])
    assert by_name(run(job), "bullet_fidelity")["ok"]


@pytest.mark.parametrize("summary,ok", [(None, True), ("__variant__", True), ("I am a rockstar 10x engineer.", False)])
def test_summary_must_be_a_profile_variant(tmp_path: Path, summary, ok: bool) -> None:
    prof = __import__("yaml").safe_load((EXAMPLE_REPO / "profile" / "master.yaml").read_text())
    if summary == "__variant__":
        summary = next(iter(prof["summary_variants"].values()))
    job = _resume_with(make_job(tmp_path), summary=summary)
    assert by_name(run(job), "bullet_fidelity")["ok"] is ok


@pytest.mark.parametrize("skills,ok", [
    ({"programming": ["Python", "SQL"], "tools": ["Docker", "AWS"]}, True),
    ({"programming": ["python"], "tools": ["docker"]}, True),          # case-insensitive
    ({"tools": ["terraform"]}, False),                                  # lowercase new tool
    ({"frameworks": ["Kubernetes"]}, False),
])
def test_skills_traced(tmp_path: Path, skills: dict, ok: bool) -> None:
    job = _resume_with(make_job(tmp_path), skills=skills)
    c = by_name(run(job), "skills_traced")
    assert c["ok"] is ok, c["detail"]


# --- standard answers (profile/standard_answers.yaml) ------------------------------------------------

@pytest.mark.parametrize("entry,ok", [
    ({"answer": "Yes", "type": "standard", "standard_key": "work_authorization"}, True),
    ({"answer": "No", "type": "standard", "standard_key": "work_authorization"}, False),     # contradicts config
    ({"answer": "Yes", "type": "standard", "standard_key": "no_such_key"}, False),
    ({"answer": "Yes", "type": "standard"}, False),                                         # no key: unverifiable
    ({"answer": None, "type": "standard", "standard_key": "salary_expectation"}, True),     # null stays null
    ({"answer": "$150k", "type": "standard", "standard_key": "salary_expectation"}, False),
    ({"answer": "Decline", "type": "standard", "standard_key": "eeo.gender"}, True),
    ({"answer": "Female", "type": "standard", "standard_key": "eeo.gender"}, False),
    ({"answer": "About 120k", "type": "generated", "class": "salary_freeform"}, False),      # never answered
    ({"answer": None, "type": "generated", "class": "sensitive", "needs_review": True}, True),
])
def test_standard_answers_match_profile(tmp_path: Path, entry: dict, ok: bool) -> None:
    job = make_job(tmp_path, answers=[{"question": "Q?", "bullet_ids": [], **entry}])
    c = by_name(run(job), "standard_answers")
    assert c["ok"] is ok, c["detail"]
