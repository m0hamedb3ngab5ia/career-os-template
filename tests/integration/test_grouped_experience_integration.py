"""Two adjacent roles at one employer -> render.py subprocess -> one company heading in .tex, resume.txt and the
PDF; `python -m careeros.qa` keeps entry_headers, pdf_fidelity and the new experience-shape checks green."""
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
BULLETS = ["acme.1", "acme.2", "acme.3", "acme.old1", "acme.old2", "widgetizer.1"]


def _run(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], capture_output=True, text=True, cwd=root, env=subprocess_env(root, home),
                          timeout=300)


def _grouped_job(root: Path, home: Path) -> Path:
    personalize_identity(root)
    pm = root / "profile" / "master.yaml"
    prof = yaml.safe_load(pm.read_text())
    acme = next(e for e in prof["experience"] if e["id"] == "acme")
    prof["experience"].insert(1, {
        **{k: acme[k] for k in ("company", "location", "tags", "stack")},
        "id": "acme_old", "title": "Associate Engineer", "start": "2024-01", "end": "2024-12",
        "bullets": [{"id": "acme.old1", "text": "Wrote the order-intake validation rules in Python", "metrics": []},
                    {"id": "acme.old2", "text": "Documented the Kafka topic contracts for three services",
                     "metrics": ["three"]}]})
    pm.write_text(yaml.safe_dump(prof, sort_keys=False))
    d = root / "data" / "jobs" / "t1"
    d.mkdir(parents=True, exist_ok=True)
    posting = json.loads((FIXTURES / "example_posting.json").read_text())
    posting["job_id"] = "t1"
    (d / "posting.json").write_text(json.dumps(posting))
    (d / "score.json").write_text(json.dumps({"job_id": "t1", "category": "swe_backend", "fit": 80,
                                              "required_skills": ["Python", "SQL", "AWS", "PostgreSQL", "Kafka"]}))
    (d / "resume.json").write_text(json.dumps(build_resume_json(prof, BULLETS, job_id="t1"), indent=2))
    r = _run(root, home, "templates/resume/render.py", str(d / "resume.json"), *([] if HAS_ENGINE else ["--no-pdf"]))
    assert r.returncode == 0, r.stderr
    (d / "cover_letter.md").write_text(COVER_LETTER)
    (d / "answers.json").write_text(json.dumps([{"question": "Are you legally authorized to work in the US?",
                                                 "answer": "Yes", "type": "standard", "standard_key": "work_authorization",
                                                 "needs_review": False}]))
    return d


def test_grouped_roles_render_one_heading_and_pass_qa(temp_root: Path, tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    d = _grouped_job(temp_root, home)
    tex = (d / "resume.tex").read_text()
    assert tex.count(r"\employer{Acme}") == 1 and r"\role{Associate Engineer}" in tex
    assert (d / "resume.txt").read_text().count("Acme") == 1
    res = json.loads(_run(temp_root, home, "-m", "careeros.qa", str(d)).stdout)
    checks = {c["check"]: c for c in res["checks"]}
    for name in ("entry_headers", "thin_experience_entry", "repeated_employer"):
        assert checks[name]["ok"], checks[name]["detail"]


@pytest.mark.skipif(not HAS_ENGINE, reason="no offline LaTeX engine")
def test_grouped_roles_real_pdf_shows_company_once_and_passes_fidelity(temp_root: Path, tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    d = _grouped_job(temp_root, home)
    assert (d / "resume.pdf").is_file()
    from pypdf import PdfReader

    from careeros.extract import pdf_page_text
    text = "\n".join(pdf_page_text(pg) for pg in PdfReader(str(d / "resume.pdf")).pages)
    assert text.count("Acme") == 1 and "Associate Engineer" in text
    res = json.loads(_run(temp_root, home, "-m", "careeros.qa", str(d)).stdout)
    bad = [c for c in res["checks"] if c["level"] == "hard" and not c["ok"] and c["check"] != "example_identity"]
    assert not bad, bad
