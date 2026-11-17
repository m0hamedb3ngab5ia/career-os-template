"""resume.pdf / title checks that keep Greenhouse-style résumé parsing clean (research: greenhouse.md s3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import EXAMPLE_REPO

from careeros.qa import Checker
from careeros.qa_ext.ats_parse import check_ats_parse

pytestmark = pytest.mark.unit


def job(tmp_path: Path, titles=("Software Engineer",), pdf_bytes: int | None = 1000) -> Path:
    jd = tmp_path / "j"
    jd.mkdir()
    (jd / "resume.json").write_text(json.dumps({"experience": [{"id": f"e{i}", "title": t} for i, t in enumerate(titles)]}))
    if pdf_bytes is not None:
        (jd / "resume.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * pdf_bytes)
    return jd


def run(jd: Path) -> dict:
    ck = Checker(jd, EXAMPLE_REPO)
    check_ats_parse(ck)
    return {c["check"]: c for c in ck.checks}


def test_clean(tmp_path):
    c = run(job(tmp_path))
    assert c["pdf_size"]["ok"] and c["abbreviated_titles"]["ok"]
    assert c["pdf_size"]["level"] == "hard" and c["abbreviated_titles"]["level"] == "soft"


def test_pdf_over_limit_fails(tmp_path):
    c = run(job(tmp_path, pdf_bytes=int(2.6 * 1024 * 1024)))
    assert not c["pdf_size"]["ok"] and "2.5" in c["pdf_size"]["detail"]


def test_no_pdf_skips_size(tmp_path):
    assert run(job(tmp_path, pdf_bytes=None))["pdf_size"].get("skipped")


@pytest.mark.parametrize("title", ["Sr. Software Engineer", "SWE Intern", "Software Eng.", "Eng. Mgr", "Jr Developer"])
def test_abbreviated_titles_warn(tmp_path, title):
    c = run(job(tmp_path, titles=(title,)))["abbreviated_titles"]
    assert not c["ok"] and title in c["detail"]


def test_full_words_not_flagged(tmp_path):
    assert run(job(tmp_path, titles=("Senior Engineering Manager",)))["abbreviated_titles"]["ok"]


def test_outreach_guidance_asks_for_referral_form():
    """Employee referral asks name the applicant-system referral form (research: greenhouse.md s5)."""
    root = Path(__file__).resolve().parent.parent
    for rel in (".claude/skills/draft-outreach/SKILL.md", "templates/outreach/cold_email.md",
                "templates/outreach/linkedin_message.md"):
        assert "referral form" in (root / rel).read_text(encoding="utf-8"), rel


def test_outreach_priority_claim_is_greenhouse_only():
    """The priority-queue claim is documented for Greenhouse only (Codex #197): the skill gates it on posting.ats."""
    root = Path(__file__).resolve().parents[1]
    text = (root / ".claude/skills/draft-outreach/SKILL.md").read_text(encoding="utf-8")
    assert "ats" in text and "greenhouse" in text.lower()
    assert "Other ATS" in text
