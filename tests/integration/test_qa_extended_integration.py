"""Extended QA gate end to end: a rendered job dir (+ outreach.json, contacts.json) -> `python -m careeros.qa`
subprocess -> JSON with the wrong-company, consistency, outreach-policy and PDF-fidelity checks."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import FIXTURES, PY, build_resume_json, personalize_identity, subprocess_env, tectonic_cache
from test_qa import COVER_LETTER

pytestmark = pytest.mark.integration

HAS_ENGINE = bool((shutil.which("tectonic") and tectonic_cache()) or shutil.which("pdflatex"))  # offline only
BULLETS = ["acme.1", "acme.2", "acme.3", "initech_intern.1", "widgetizer.1"]
EXTENDED = ("wrong_company", "letter_experiences_on_resume", "employer_title_consistent", "numbers_consistent",
            "outreach_manual_contacts", "linkedin_draft_only", "linkedin_note_length", "email_autosend_verified",
            "thank_you_manual", "outreach_word_counts", "outreach_cold_limit")
PDF_CHECKS = ("pdf_links_clickable", "pdf_text_matches_resume", "pdf_fonts_embedded", "pdf_metadata")

CONTACTS = {"job_id": "t1", "company": "Ledgerline", "contacts": [
    {"name": "Jordan Sample", "title": "Technical Recruiter", "role": "recruiter", "confidence": "high",
     "email": "jordan.sample@ledgerline.example", "email_confidence": "verified", "linkedin_degree": None,
     "mutuals": None}]}
DRAFT = {
    "contact": "Jordan Sample", "role": "recruiter", "to": "jordan.sample@ledgerline.example",
    "to_confidence": "verified", "kind": "post_apply_outreach", "channel": "email",
    "linkedin_note": "Hi Jordan, I applied to the Backend role at Ledgerline. At Acme I built a FastAPI service "
                     "that ingests Kafka order events into PostgreSQL. Would like to connect.",
    "linkedin_message": None,
    "email": {"subject": "Backend application at Ledgerline",
              "body": "Hi Jordan,\n\nI applied to the Software Engineer, Backend role at Ledgerline today. At Acme "
                      "I built a FastAPI service in Python that ingests Kafka order events into PostgreSQL, "
                      "processing 2 million events per day. Happy to share more.\n\nAlex"},
    "followup_7d": None, "followup_14d": None, "bullet_ids": ["acme.1"], "narrative_ids": [],
    "manual_tailor": False, "manual_reason": None, "send_after": "2026-09-27", "sent": False,
    "sent_by": None, "auto_send": False, "linkedin_send_after": None,
}


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def _run(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], capture_output=True, text=True, cwd=root, env=subprocess_env(root, home),
                          timeout=300)


@pytest.fixture
def job_dir(temp_root: Path, home: Path) -> Path:
    personalize_identity(temp_root)
    d = temp_root / "data" / "jobs" / "t1"
    d.mkdir(parents=True)
    posting = json.loads((FIXTURES / "example_posting.json").read_text())
    posting["job_id"] = "t1"
    (d / "posting.json").write_text(json.dumps(posting))
    (d / "score.json").write_text(json.dumps({"job_id": "t1", "category": "swe_backend", "fit": 80,
                                              "required_skills": ["Python", "SQL", "AWS", "PostgreSQL", "Kafka"]}))
    prof = yaml.safe_load((temp_root / "profile" / "master.yaml").read_text())
    (d / "resume.json").write_text(json.dumps(build_resume_json(prof, BULLETS, job_id="t1"), indent=2))
    args = ["templates/resume/render.py", str(d / "resume.json")] + ([] if HAS_ENGINE else ["--no-pdf"])
    r = _run(temp_root, home, *args)
    assert r.returncode == 0, r.stderr
    (d / "cover_letter.md").write_text(COVER_LETTER)
    (d / "contacts.json").write_text(json.dumps(CONTACTS))
    (d / "outreach.json").write_text(json.dumps({"job_id": "t1", "company": "Ledgerline", "drafts": [DRAFT],
                                                 "review_required": True}))
    # another job dir: its company is a wrong-company candidate for this one
    other = temp_root / "data" / "jobs" / "t2"
    other.mkdir()
    (other / "posting.json").write_text(json.dumps({**posting, "job_id": "t2", "company": "Brightpeak"}))
    return d


def _qa(root: Path, home: Path, d: Path, *extra: str) -> tuple[int, dict]:
    r = _run(root, home, "-m", "careeros.qa", str(d), *extra)
    return r.returncode, json.loads(r.stdout)


def test_clean_job_runs_every_extended_check(temp_root: Path, home: Path, job_dir: Path):
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert res["fail_reasons"] == [] and res["pass"] is True and code == 0, res["fail_reasons"]
    checks = {c["check"]: c for c in res["checks"]}
    for name in EXTENDED:
        assert name in checks and checks[name]["ok"], (name, checks.get(name))
        assert not checks[name].get("skipped"), (name, checks[name]["detail"])
    assert res["wrong_company_hits"] == []
    assert res["outreach_policy"]["present"] is True and res["outreach_policy"]["violations"] == []
    assert res["consistency"]["number_mismatches"] == [] and "outreach.json#0" in res["consistency"]["docs"]
    assert res["artifacts"]["outreach.json"] is True
    for name in PDF_CHECKS:
        if HAS_ENGINE:
            assert checks[name]["ok"] and not checks[name].get("skipped"), (name, checks[name]["detail"])
        else:
            assert checks[name].get("skipped")


def test_wrong_company_letter_fails_strict(temp_root: Path, home: Path, job_dir: Path):
    cover = (job_dir / "cover_letter.md").read_text()
    (job_dir / "cover_letter.md").write_text(cover.replace("Happy to walk through the code.",
                                                           "Brightpeak's ledger is where I want to build next."))
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert code == 1 and res["pass"] is False
    assert [(h["file"], h["name"]) for h in res["wrong_company_hits"]] == [("cover_letter.md", "Brightpeak")]
    assert any(r.startswith("wrong_company: ") for r in res["fail_reasons"])
    assert _qa(temp_root, home, job_dir)[0] == 0  # report mode still exits 0


def test_outreach_policy_violations_fail(temp_root: Path, home: Path, job_dir: Path):
    bad = {**DRAFT, "linkedin_note": "x" * 301, "channel": "linkedin", "linkedin_send_after": "2026-09-27"}
    (job_dir / "outreach.json").write_text(json.dumps({"drafts": [bad]}))
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert code == 1
    failed = {r.split(":")[0] for r in res["fail_reasons"]}
    assert {"linkedin_note_length", "linkedin_draft_only"} <= failed
