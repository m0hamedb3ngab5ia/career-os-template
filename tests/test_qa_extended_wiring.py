"""Unit tests: the extended QA modules (careeros.qa_ext.*) are wired into Checker.run() and share its inputs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import make_temp_root
from test_qa import COVER_LETTER, by_name, make_job, run

from careeros.qa import Checker, count_words, load_yaml, run_deterministic

pytestmark = pytest.mark.unit

NEW_CHECKS = ("wrong_company", "letter_experiences_on_resume", "employer_title_consistent", "numbers_consistent",
              "outreach_manual_contacts", "linkedin_draft_only", "linkedin_note_length", "email_autosend_verified",
              "thank_you_manual", "outreach_word_counts", "outreach_cold_limit", "pdf_links_clickable",
              "pdf_text_matches_resume", "pdf_fonts_embedded", "pdf_metadata")
NEW_EXTRAS = ("wrong_company_hits", "consistency", "outreach_policy", "pdf_fidelity")


def names(res: dict) -> list[str]:
    return [c["check"] for c in res["checks"]]


def test_run_reports_every_new_check_and_extra(tmp_path: Path) -> None:
    res = run(make_job(tmp_path))
    got = names(res)
    for n in NEW_CHECKS:
        assert n in got, n
    for k in NEW_EXTRAS:
        assert k in res, k
    assert res["pass"] is True, res["fail_reasons"]
    assert by_name(res, "wrong_company")["ok"] and not by_name(res, "wrong_company").get("skipped")
    assert res["wrong_company_hits"] == []
    assert res["outreach_policy"]["present"] is False
    assert res["pdf_fidelity"] == {"skipped": "resume.pdf not built"}
    assert set(res["consistency"]) >= {"letter_off_resume", "title_mismatches", "number_mismatches"}


def test_pdf_fidelity_runs_right_after_check_pdf(tmp_path: Path) -> None:
    got = names(run(make_job(tmp_path)))
    i = got.index("pdf")  # skipped check_pdf record (no resume.pdf)
    assert got[i + 1:i + 5] == ["pdf_links_clickable", "pdf_text_matches_resume", "pdf_fonts_embedded", "pdf_metadata"]


def test_wrong_company_letter_fails_the_gate(tmp_path: Path) -> None:
    job = make_job(tmp_path, cover=COVER_LETTER.replace("Happy to walk through the code.",
                                                        "I have always wanted to work at Stripe."))
    res = run(job)
    assert res["pass"] is False
    assert any(r.startswith("wrong_company:") for r in res["fail_reasons"])
    assert [h["name"] for h in res["wrong_company_hits"]] == ["Stripe"]


def test_company_named_soft_check_is_gone(tmp_path: Path) -> None:
    assert "company_named:cover_letter" not in names(run(make_job(tmp_path)))


def test_outreach_json_is_optional_artifact(tmp_path: Path) -> None:
    job = make_job(tmp_path)
    res = run(job)
    assert res["artifacts"]["outreach.json"] is False
    assert by_name(res, "artifacts_present")["ok"], by_name(res, "artifacts_present")["detail"]
    (job / "outreach.json").write_text(json.dumps({"drafts": []}))
    assert run(job)["artifacts"]["outreach.json"] is True


def test_missing_job_dir_result_has_new_extras(tmp_path: Path) -> None:
    res = run_deterministic(tmp_path / "nope", root=tmp_path)
    for k in NEW_EXTRAS:
        assert k in res, k


# --- shared Checker inputs ---------------------------------------------------------------------------

@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_temp_root(tmp_path / "repo")


def _job(root: Path) -> Path:
    job = root / "data" / "jobs" / "j1"
    job.mkdir(parents=True)
    return job


def test_shared_inputs_loaded_once(root: Path) -> None:
    job = _job(root)
    (job / "outreach.json").write_text(json.dumps({"drafts": [{"contact": "Pat"}]}))
    (job / "contacts.json").write_text(json.dumps({"contacts": [{"name": "Pat"}]}))
    ck = Checker(job, root)
    assert ck.pipeline_cfg == yaml.safe_load((root / "config" / "pipeline.yaml").read_text())
    assert ck.companies_cfg == yaml.safe_load((root / "config" / "companies.yaml").read_text())
    assert ck.jobs_dir == (root / "data" / "jobs").resolve()
    assert ck.outreach == {"drafts": [{"contact": "Pat"}]} and ck.outreach_error is None
    assert ck.contacts == {"contacts": [{"name": "Pat"}]}


def test_shared_inputs_absent_or_broken(root: Path) -> None:
    job = _job(root)
    (root / "config" / "companies.yaml").unlink()
    (job / "outreach.json").write_text("{nope")
    (job / "contacts.json").write_text("[broken")
    ck = Checker(job, root)
    assert ck.companies_cfg == {}
    assert ck.outreach is None and ck.outreach_error and ck.outreach_raw == "{nope"
    assert ck.contacts is None


def test_jobs_dir_absolute_and_default(root: Path, tmp_path: Path) -> None:
    p = root / "config" / "pipeline.yaml"
    cfg = yaml.safe_load(p.read_text())
    cfg["paths"]["jobs_dir"] = str(tmp_path / "elsewhere")
    p.write_text(yaml.safe_dump(cfg))
    assert Checker(_job(root), root).jobs_dir == (tmp_path / "elsewhere").resolve()
    del cfg["paths"]["jobs_dir"]
    p.write_text(yaml.safe_dump(cfg))
    assert Checker(root / "data" / "jobs" / "j1", root).jobs_dir == (root / "data" / "jobs").resolve()


def test_public_helper_aliases(tmp_path: Path) -> None:
    assert count_words("a b  c\nd") == 4
    assert load_yaml(tmp_path / "missing.yaml") == {}
