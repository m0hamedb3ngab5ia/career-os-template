"""Unit tests for careeros.qa_ext.company: wrong-company leftovers in the letter, answers and outreach."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import FIXTURES, make_temp_root

from careeros.qa import Checker
from careeros.qa_ext.company import check_wrong_company

pytestmark = pytest.mark.unit

LETTER = """---
company: Ledgerline
bullet_ids_used: [acme.1]
---
Hi Payments Platform team,

The Software Engineer, Backend role at Ledgerline is the closest match to the work I do now.

At Acme I built a FastAPI service in Python that ingests Kafka order events into PostgreSQL. Outside work I
built Widgetizer, an iOS app in Swift with a Supabase backend. I studied at Springfield State University.

{extra}

Alex
"""


def letter(extra: str = "", company_line: bool = True) -> str:
    text = LETTER.format(extra=extra)
    if not company_line:
        text = text.replace("The Software Engineer, Backend role at Ledgerline", "This role")
    return text


def edit_companies(root: Path, fn) -> None:
    p = root / "config" / "companies.yaml"
    data = yaml.safe_load(p.read_text())
    fn(data)
    p.write_text(yaml.safe_dump(data, sort_keys=False))


def write_posting(d: Path, company: str, description: str | None = None) -> None:
    d.mkdir(parents=True, exist_ok=True)
    posting = json.loads((FIXTURES / "example_posting.json").read_text())
    posting["company"] = company
    posting["job_id"] = d.name
    if description is not None:
        posting["description_text"] = description
    (d / "posting.json").write_text(json.dumps(posting))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = make_temp_root(tmp_path / "repo")
    # the example companies.yaml carries Stripe/Databricks/Anthropic (dream list), Supabase/Two Sigma/... in
    # prestige_tiers; the conftest boards are Acme, Lever Co, Ashby Co, Custom Co
    edit_companies(r, lambda d: d["boards"].extend([
        {"company": "Supabase", "ats": "ashby", "slug": "supabase"},
        {"company": "Scale", "ats": "greenhouse", "slug": "scale"},
        {"company": "Square", "ats": "greenhouse", "slug": "square"},
        {"company": "Two Sigma", "ats": "custom", "url": "https://x"},
        {"company": "Linear", "ats": "ashby", "slug": "linear"},
    ]))
    return r


def make(root: Path, cover: str | None = None, answers=None, outreach=None, company: str = "Ledgerline",
         description: str | None = None, qa: dict | None = None, name: str = "j1") -> Checker:
    job = root / "data" / "jobs" / name
    write_posting(job, company, description)
    if cover is not None:
        (job / "cover_letter.md").write_text(cover)
    if answers is not None:
        (job / "answers.json").write_text(json.dumps(answers))
    if outreach is not None:
        (job / "outreach.json").write_text(outreach if isinstance(outreach, str) else json.dumps(outreach))
    ck = Checker(job, root)
    if qa is not None:
        ck.qa_cfg = dict(ck.qa_cfg or {}, consistency=qa)
    return ck


def run(ck: Checker) -> Checker:
    check_wrong_company(ck)
    return ck


def check(ck: Checker, name: str) -> dict:
    hits = [c for c in ck.checks if c["check"] == name]
    assert hits, f"{name} not in {[c['check'] for c in ck.checks]}"
    return hits[-1]


def names(ck: Checker) -> list[str]:
    return [h["name"] for h in ck.extras["wrong_company_hits"]]


# --- clean / basic hits -----------------------------------------------------------------------------

def test_clean_letter_passes(root: Path) -> None:
    ck = run(make(root, cover=letter()))
    c = check(ck, "wrong_company")
    assert c["level"] == "hard" and c["ok"], c
    assert ck.extras["wrong_company_hits"] == []
    assert not [c for c in ck.checks if c["check"] == "company_named:cover_letter"]  # merged into the hard check


def test_dream_list_company_in_letter_fails(root: Path) -> None:
    ck = run(make(root, cover=letter("I have wanted to work at Stripe since college.")))
    c = check(ck, "wrong_company")
    assert not c["ok"] and "cover_letter.md" in c["detail"] and "Stripe" in c["detail"]
    hit = ck.extras["wrong_company_hits"][0]
    assert hit["file"] == "cover_letter.md" and hit["name"] == "Stripe" and "Stripe" in hit["context"]


def test_frontmatter_is_not_scanned(root: Path) -> None:
    cover = letter().replace("company: Ledgerline", "company: Ledgerline\nnote: was Stripe draft")
    assert check(run(make(root, cover=cover)), "wrong_company")["ok"]


@pytest.mark.parametrize("source", ["prestige", "domains", "applied_dict", "applied_str", "dream_dict"])
def test_candidate_sources(root: Path, source: str) -> None:
    def fn(d):
        if source == "prestige":
            d["prestige_tiers"]["a"].append("Quorvex")
        elif source == "domains":
            d["company_domains"] = {"Quorvex": "quorvex.io"}
        elif source == "applied_dict":
            d["already_applied"] = [{"company": "Quorvex", "role": "SWE", "date": "2026-07"}]
        elif source == "applied_str":
            d["already_applied"] = ["Quorvex"]
        else:
            d["dream_list"] = [{"company": "Quorvex"}]
    edit_companies(root, fn)
    assert names(run(make(root, cover=letter("Quorvex taught me a lot.")))) == ["Quorvex"]


def test_other_job_dir_company_is_a_candidate(root: Path) -> None:
    write_posting(root / "data" / "jobs" / "other1", "Brightpeak")
    write_posting(root / "data" / "jobs" / "other1 2", "Finderdup")  # Finder duplicate: ignored
    ck = run(make(root, cover=letter("I admire Brightpeak and Finderdup.")))
    assert names(ck) == ["Brightpeak"]


def test_other_job_dir_same_company_is_not_a_candidate(root: Path) -> None:
    write_posting(root / "data" / "jobs" / "other1", "Ledgerline Inc.")
    assert check(run(make(root, cover=letter())), "wrong_company")["ok"]


def test_scan_job_dirs_can_be_disabled(root: Path) -> None:
    write_posting(root / "data" / "jobs" / "other1", "Brightpeak")
    ck = run(make(root, cover=letter("I admire Brightpeak."), qa={"scan_job_dirs": False}))
    assert check(ck, "wrong_company")["ok"]


# --- exclusions -----------------------------------------------------------------------------------

def test_profile_employer_school_project_and_tools_excluded(root: Path) -> None:
    edit_companies(root, lambda d: d["dream_list"].extend(["Initech", "Widgetizer", "Springfield State University"]))
    ck = run(make(root, cover=letter("At Initech I learned SQL; Widgetizer and Springfield State University too.")))
    # Acme (profile employer and a board), Supabase (profile stack and a board) also appear in the letter
    assert check(ck, "wrong_company")["ok"], ck.extras["wrong_company_hits"]


def test_this_company_aliases_and_variants_excluded(root: Path) -> None:
    edit_companies(root, lambda d: (
        d["boards"].extend([{"company": "Ledgerline Inc", "ats": "greenhouse", "slug": "ledgerline"},
                            {"company": "Ledgerline Payments", "ats": "greenhouse", "slug": "llp"},
                            {"company": "LedgerLine", "ats": "greenhouse", "slug": "ll2"},
                            {"company": "Ledger HQ", "ats": "greenhouse", "slug": "lhq"}]),
        d.update(company_domains={"Ledgerline": ["ledgerhq.com"]})))
    ck = run(make(root, cover=letter("Ledgerline Inc, Ledgerline Payments, LedgerLine and Ledger HQ are one team.")))
    assert check(ck, "wrong_company")["ok"], ck.extras["wrong_company_hits"]


def test_configured_alias_excluded(root: Path) -> None:
    edit_companies(root, lambda d: d["dream_list"].append("LL Corp"))
    ck = run(make(root, cover=letter("LL Corp ships fast."), qa={"company_aliases": {"Ledgerline": ["LL Corp"]}}))
    assert check(ck, "wrong_company")["ok"]


def test_shorter_parent_name_of_this_company_excluded(root: Path) -> None:
    edit_companies(root, lambda d: d["dream_list"].append("Citadel"))
    ck = run(make(root, cover=letter("Citadel Securities and Citadel both.").replace("Ledgerline", "Citadel Securities"),
                  company="Citadel Securities"))
    assert check(ck, "wrong_company")["ok"]


def test_name_in_posting_is_allowed_by_default(root: Path) -> None:
    desc = "We settle card payments and integrate with Stripe for payouts."
    ck = run(make(root, cover=letter("I have used Stripe payouts."), description=desc))
    assert check(ck, "wrong_company")["ok"]
    ck = run(make(root, cover=letter("I have used Stripe payouts."), description=desc,
                  qa={"allow_posting_mentions": False}, name="j2"))
    assert names(ck) == ["Stripe"]


def test_linkedin_github_ignored_by_default_and_ignore_names_config(root: Path) -> None:
    edit_companies(root, lambda d: d["prestige_tiers"]["b_plus"].append("Anthropic"))
    ck = run(make(root, cover=letter("Find me on LinkedIn and GitHub.")))
    assert check(ck, "wrong_company")["ok"]
    ck = run(make(root, cover=letter("Anthropic is great."), qa={"ignore_names": ["Anthropic"]}, name="j2"))
    assert check(ck, "wrong_company")["ok"]


def test_min_name_length(root: Path) -> None:
    edit_companies(root, lambda d: d["prestige_tiers"]["b_plus"].extend(["X", "IMC"]))
    ck = run(make(root, cover=letter("Axis X marks the spot, IMC too.")))
    assert names(ck) == ["IMC"]
    ck = run(make(root, cover=letter("IMC too."), qa={"min_name_length": 4}, name="j2"))
    assert check(ck, "wrong_company")["ok"]


# --- case and common-word rules -------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "I care about scale and a clean stripe of work.",       # lowercase common words
    "Scale matters in payments.",                           # common-word name at sentence start
    "It was a two sigma event.",                            # multi-word name, lower case
    "My linear algebra is solid.",
    "- Square roots and logs were daily work.",             # bullet start
])
def test_common_words_not_flagged(root: Path, text: str) -> None:
    ck = run(make(root, cover=letter(text)))
    assert check(ck, "wrong_company")["ok"], ck.extras["wrong_company_hits"]


@pytest.mark.parametrize("text,name", [
    ("Hi Scale team, I am applying.", "Scale"),
    ("I would love to build at Square next.", "Square"),
    ("I also applied to Two Sigma.", "Two Sigma"),
    ("Stripe is where I learned this.", "Stripe"),           # not a common word: sentence start still counts
    ("Your team at Linear ships fast.", "Linear"),
])
def test_proper_noun_hits(root: Path, text: str, name: str) -> None:
    assert names(run(make(root, cover=letter(text)))) == [name]


def test_title_case_line_skips_common_word_names(root: Path) -> None:
    out = {"company": "Ledgerline", "drafts": [{"contact": "Jane Doe", "email": {
        "subject": "Question About Payments At Scale", "body": "Hi Jane, quick note about Ledgerline."}}]}
    assert check(run(make(root, outreach=out)), "wrong_company")["ok"]


def test_common_word_names_config_extends(root: Path) -> None:
    edit_companies(root, lambda d: d["dream_list"].append("Harbor"))
    assert names(run(make(root, cover=letter("Harbor matters.")))) == ["Harbor"]
    ck = run(make(root, cover=letter("Harbor matters."), qa={"common_word_names": ["Harbor"]}, name="j2"))
    assert check(ck, "wrong_company")["ok"]


def test_longest_name_wins_on_overlap(root: Path) -> None:
    edit_companies(root, lambda d: d["dream_list"].extend(["Citadel", "Citadel Securities"]))
    assert names(run(make(root, cover=letter("I interned near Citadel Securities.")))) == ["Citadel Securities"]


def test_possessive_and_hyphen(root: Path) -> None:
    assert names(run(make(root, cover=letter("I like Databricks's notebooks.")))) == ["Databricks"]
    assert check(run(make(root, cover=letter("I like Databricksy vibes."), name="j2")), "wrong_company")["ok"]


def test_same_name_reported_once_per_artifact(root: Path) -> None:
    ck = run(make(root, cover=letter("Stripe here. And at Stripe again.")))
    assert names(ck) == ["Stripe"]


# --- answers.json ---------------------------------------------------------------------------------

def test_generated_answers_scanned_standard_and_eeo_not(root: Path) -> None:
    answers = [
        {"question": "Current employer?", "answer": "Stripe", "type": "standard", "standard_key": "employer"},
        {"question": "Why us?", "answer": "I want to build at Databricks.", "type": "generated", "class": "essay"},
        {"question": "Gender", "answer": "Anthropic", "type": "generated", "class": "standard",
         "standard_key": "eeo.gender"},
        {"question": "Other?", "answer": None, "type": "generated"},
        "junk",
    ]
    ck = run(make(root, answers=answers))
    assert [(h["file"], h["name"]) for h in ck.extras["wrong_company_hits"]] == [("answers.json#1", "Databricks")]


# --- outreach.json --------------------------------------------------------------------------------

def test_outreach_draft_text_scanned_contact_fields_not(root: Path) -> None:
    out = {"company": "Ledgerline", "drafts": [{
        "contact": "Jane Doe", "role": "recruiter", "to": "jane@stripe.com", "linkedin": "https://linkedin.com/in/x",
        "linkedin_note": "Hi Jane, loved your Ledgerline talk.", "linkedin_message": "Thanks!",
        "email": {"subject": "Ledgerline backend role", "body": "Hi Jane, I am excited about Anthropic."},
        "followup_7d": "Following up.", "followup_14d": "Last note."}]}
    ck = run(make(root, outreach=out))
    hits = ck.extras["wrong_company_hits"]
    assert [(h["file"], h["name"]) for h in hits] == [("outreach.json:drafts[0].email.body", "Anthropic")]


def test_outreach_unparseable_scanned_raw(root: Path) -> None:
    ck = run(make(root, outreach='{"drafts": [{"linkedin_note": "Hi from Anthropic fan" '))
    assert [(h["file"], h["name"]) for h in ck.extras["wrong_company_hits"]] == [("outreach.json", "Anthropic")]


def test_all_three_artifacts_listed_in_detail(root: Path) -> None:
    ck = run(make(root, cover=letter("Stripe."), answers=[{"question": "q", "answer": "Databricks", "type": "generated"}],
                  outreach={"drafts": [{"linkedin_note": "Anthropic"}]}))
    d = check(ck, "wrong_company")["detail"]
    assert "cover_letter.md: 'Stripe'" in d and "answers.json#0: 'Databricks'" in d and "Anthropic" in d


# --- cover_letter_names_company (hard, in careeros.qa) accepts this company's spellings ---------------

def names_company(ck: Checker) -> dict:
    ck.check_cover_letter_structure()
    return check(ck, "cover_letter_names_company")


def test_letter_never_naming_company_is_hard_fail(root: Path) -> None:
    c = names_company(make(root, cover=letter(company_line=False)))
    assert c["level"] == "hard" and not c["ok"]


def test_letter_naming_company_any_case(root: Path) -> None:
    body = letter(company_line=False) + "\nI like LEDGERLINE's ledger.\n"
    assert names_company(make(root, cover=body))["ok"]


def test_letter_naming_company_by_configured_alias(root: Path) -> None:
    body = letter(company_line=False) + "\nLL Corp rocks.\n"
    assert not names_company(make(root, cover=body))["ok"]
    ck = make(root, cover=body, qa={"company_aliases": {"Ledgerline": ["LL Corp"]}}, name="j2")
    c = names_company(ck)
    assert c["ok"] and "LL Corp" in c["detail"]


def test_letter_naming_company_by_domain_stem(root: Path) -> None:
    edit_companies(root, lambda d: d.update(company_domains={"Ledgerline": ["ledgerlinehq.com"]}))
    body = letter(company_line=False) + "\nI read the Ledgerlinehq engineering blog.\n"
    assert names_company(make(root, cover=body))["ok"]


def test_company_spellings_helper(root: Path) -> None:
    from careeros.qa_ext.company import company_spellings, names_company as named

    edit_companies(root, lambda d: d.update(company_domains={"Ledgerline": "ledgerlinehq.com"}))
    ck = make(root, cover=letter(), qa={"company_aliases": {"Ledgerline": ["LL Corp"]}})
    sp = company_spellings(ck, "Ledgerline")
    assert sp[0] == "Ledgerline" and "LL Corp" in sp and "ledgerlinehq" in sp
    assert named("we love ll corp", sp) == "LL Corp"
    assert named("Ledger-Line", sp) == "Ledgerline"   # compact form, >= 4 chars
    assert named("nothing here", sp) is None


# --- skips / config ---------------------------------------------------------------------------------

def test_no_text_artifacts_skips(root: Path) -> None:
    ck = run(make(root))
    c = check(ck, "wrong_company")
    assert c.get("skipped") and c["ok"]
    assert ck.extras["wrong_company_hits"] == []


def test_unknown_company_skips(root: Path) -> None:
    ck = make(root, cover=letter("Stripe."))
    ck.posting = None
    ck.cover_fm = {}
    run(ck)
    assert check(ck, "wrong_company").get("skipped")


def test_company_from_letter_frontmatter_when_no_posting(root: Path) -> None:
    ck = make(root, cover=letter("Stripe."))
    ck.posting = None
    run(ck)
    assert names(ck) == ["Stripe"]


def test_disabled_by_config(root: Path) -> None:
    ck = run(make(root, cover=letter("Stripe."), qa={"wrong_company": False}))
    assert check(ck, "wrong_company").get("skipped")


def test_missing_companies_yaml_still_uses_job_dirs(root: Path) -> None:
    (root / "config" / "companies.yaml").unlink()
    write_posting(root / "data" / "jobs" / "other1", "Brightpeak")
    assert names(run(make(root, cover=letter("Stripe and Brightpeak.")))) == ["Brightpeak"]


def test_malformed_config_values_do_not_crash(root: Path) -> None:
    edit_companies(root, lambda d: d.update(dream_list="Stripe", prestige_tiers=["x"], boards=[None, {"company": 3}],
                                            company_domains=None, already_applied={"a": 1}))
    ck = run(make(root, cover=letter("Stripe."), qa={"ignore_names": "nope", "min_name_length": "x",
                                                     "company_aliases": ["bad"]}))
    assert check(ck, "wrong_company")["level"] == "hard"


def test_own_names_are_masked_inside_longer_spans(root: Path) -> None:
    edit_companies(root, lambda d: d["dream_list"].append("State University"))
    # a candidate that is part of the candidate's own school name is never a leftover
    ck = run(make(root, cover=letter("State University called.")))
    assert check(ck, "wrong_company")["ok"], ck.extras["wrong_company_hits"]
