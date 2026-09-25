"""Full job dir (posting + score + resume.json rendered by templates/resume/render.py + cover_letter.md)
-> `python -m careeros.qa <dir>` subprocess -> JSON verdict."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import FIXTURES, PY, build_resume_json, subprocess_env
from test_qa import COVER_LETTER

pytestmark = pytest.mark.integration

HAS_ENGINE = bool(shutil.which("tectonic") or shutil.which("pdflatex"))
BULLETS = ["acme.1", "acme.2", "acme.3", "initech_intern.1", "widgetizer.1"]


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
    (d / "answers.json").write_text(json.dumps([{"question": "Are you legally authorized to work in the US?",
                                                 "answer": "Yes", "type": "standard", "needs_review": False}]))
    return d


def _qa(root: Path, home: Path, d: Path, *extra: str) -> tuple[int, dict]:
    r = _run(root, home, "-m", "careeros.qa", str(d), *extra)
    return r.returncode, json.loads(r.stdout)


def test_rendered_job_dir_passes(temp_root: Path, home: Path, job_dir: Path):
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert res["fail_reasons"] == [] and res["pass"] is True, res["fail_reasons"]
    assert code == 0
    assert all(res["artifacts"][k] for k in ("posting.json", "score.json", "resume.json", "resume.txt", "cover_letter.md"))
    checks = {c["check"]: c for c in res["checks"]}
    assert checks["truth_trace"]["ok"] and not checks["truth_trace"].get("skipped")
    assert checks["tool_audit"]["ok"] and checks["number_audit:resume.txt"]["ok"]
    assert res["keyword_coverage"] == 1.0
    if HAS_ENGINE:
        assert checks["pdf_page_count"]["ok"] and checks["contact_intact:resume.pdf"]["ok"], checks["contact_intact:resume.pdf"]
    else:
        assert checks["pdf"].get("skipped")


def test_fabricated_number_fails_with_orphan(temp_root: Path, home: Path, job_dir: Path):
    rj = json.loads((job_dir / "resume.json").read_text())
    b = rj["experience"][0]["bullets"][1]
    assert "40 analysts" in b["text"]
    b["text"] = b["text"].replace("40 analysts", "45 analysts")  # fabricated metric
    (job_dir / "resume.json").write_text(json.dumps(rj))
    assert _run(temp_root, home, "templates/resume/render.py", str(job_dir / "resume.json"), "--txt-only").returncode == 0

    code, res = _qa(temp_root, home, job_dir)
    assert code == 0  # report-only mode
    assert res["pass"] is False
    assert {"file": "resume.txt", "number": "45"} in res["orphan_numbers"]
    assert any(r.startswith("number_audit:resume.txt: orphan numbers: 45") for r in res["fail_reasons"])
    assert _qa(temp_root, home, job_dir, "--strict")[0] == 1


def test_confidential_term_in_outreach_fails_strict(temp_root: Path, home: Path, job_dir: Path):
    """Candidate's own profile/confidential_terms.yaml (loaded from the temp root) gates every artifact."""
    (temp_root / "profile" / "confidential_terms.yaml").write_text(
        "employer: Acme\nterms: [Nightjar]\npatterns: ['\\bNJ-\\d{4}\\b']\n")
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert code == 0 and res["pass"] is True
    (job_dir / "outreach.json").write_text(json.dumps([{"contact": "Pat", "linkedin_note": "I worked on NIGHTJAR"}]))
    (job_dir / "resume.txt").write_text((job_dir / "resume.txt").read_text() + "- see NJ-4821\n")
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert code == 1 and res["pass"] is False
    assert res["confidential_hits"] == ["resume.txt: patterns[0]", "outreach.json: term 'Nightjar'"]
    assert any(r.startswith("confidential_terms: confidential content") for r in res["fail_reasons"])
