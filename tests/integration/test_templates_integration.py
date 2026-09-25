"""resume.json / cover_letter.md built from the fixture profile -> render.py subprocess -> .tex/.pdf/.txt."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import PY, build_resume_json, subprocess_env, tectonic_cache

pytestmark = pytest.mark.integration

# Offline only: tectonic with a local bundle cache (run with CAREEROS_LATEX_OFFLINE=1), or pdflatex.
HAS_ENGINE = bool((shutil.which("tectonic") and tectonic_cache()) or shutil.which("pdflatex"))
needs_engine = pytest.mark.skipif(not HAS_ENGINE, reason="no offline LaTeX engine (cached tectonic or pdflatex)")

BULLETS = ["acme.1", "acme.2", "acme.3", "initech_intern.1", "initech_intern.2", "widgetizer.1", "widgetizer.2"]


def _job_dir(root: Path) -> Path:
    d = root / "data" / "jobs" / "job000000001"
    d.mkdir(parents=True)
    return d


def _run(root: Path, home: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(root / script), *args], capture_output=True, text=True, cwd=root,
                          env=subprocess_env(root, home), timeout=300)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def resume_json(temp_root: Path) -> Path:
    prof = yaml.safe_load((temp_root / "profile" / "master.yaml").read_text())
    data = build_resume_json(prof, BULLETS)
    data["experience"][0]["bullets"][0]["text"] += " (R&D, 100% on-call_rotation #1)"  # specials survive LaTeX
    p = _job_dir(temp_root) / "resume.json"
    p.write_text(json.dumps(data, indent=2))
    return p


def _pdf_pages_and_text(pdf: Path) -> tuple[int, str]:
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(str(pdf))
    return len(reader.pages), "\n".join(p.extract_text() or "" for p in reader.pages)


def test_resume_no_pdf_writes_tex_and_txt(temp_root: Path, home: Path, resume_json: Path):
    r = _run(temp_root, home, "templates/resume/render.py", str(resume_json), "--no-pdf")
    assert r.returncode == 0, r.stderr
    d = resume_json.parent
    tex = (d / "resume.tex").read_text()
    assert r"\begin{document}" in tex and r"{\Large\bfseries Alex Example}" in tex
    assert r"R\&D, 100\% on-call\_rotation \#1" in tex
    assert tex.index(r"\section{Experience}") < tex.index(r"\section{Projects}") < tex.index(r"\section{Education}")
    assert not (d / "resume.pdf").exists()
    txt = (d / "resume.txt").read_text()
    for s in ("Alex Example", "alex@example.com", "555-010-0199", "linkedin.com/in/alex-example", "github.com/alex-example"):
        assert s in txt
    assert txt.index("EXPERIENCE") < txt.index("PROJECTS") < txt.index("EDUCATION") < txt.index("SKILLS")


@needs_engine
def test_resume_compiles_to_one_page_pdf(temp_root: Path, home: Path, resume_json: Path):
    r = _run(temp_root, home, "templates/resume/render.py", str(resume_json))
    assert r.returncode == 0, r.stderr
    d = resume_json.parent
    pdf = d / "resume.pdf"
    assert pdf.exists(), r.stderr
    pages, text = _pdf_pages_and_text(pdf)
    assert pages == 1
    squashed = text.replace(" ", "")
    for s in ("AlexExample", "alex@example.com", "555-010-0199"):
        assert s in squashed
    assert not list(d.glob("*.aux")) and not list(d.glob("*.log"))  # build artefacts cleaned


def test_resume_placeholder_exits_nonzero(temp_root: Path, home: Path, resume_json: Path):
    data = json.loads(resume_json.read_text())
    data["experience"][0]["bullets"].append({"id": "acme.4", "text": "[OPEN: on-call story — add when it happens]"})
    resume_json.write_text(json.dumps(data))
    r = _run(temp_root, home, "templates/resume/render.py", str(resume_json), "--no-pdf")
    assert r.returncode == 1 and "placeholder" in r.stderr
    assert not (resume_json.parent / "resume.tex").exists()


COVER = """---
job_id: job000000001
company: Initech
role: Software Engineer, Backend
team: Payments
greeting: "Hi Payments team,"
date: 2026-09-24
sign_off: "Alex"
bullet_ids: [acme.1, initech_intern.1]
narrative_ids: [n.data]
company_facts:
  - {fact: "Payments runs on Kafka", source: posting}
  - {fact: "Team publishes an engineering blog", source: posting}
---

Your Payments team runs its ledger on Kafka, and I built a FastAPI service at Acme that ingests Kafka order events into PostgreSQL, processing 2 million events per day.

At Initech I wrote 12 Airflow DAGs in Python and cut manual prep by 5 hours per week. I care about **data you can trust**.

Happy to walk through the code.
"""


@pytest.mark.parametrize("pdf", [False, pytest.param(True, marks=needs_engine)], ids=["no_pdf", "pdf"])
def test_cover_letter_render(temp_root: Path, home: Path, pdf: bool):
    d = _job_dir(temp_root)
    md = d / "cover_letter.md"
    md.write_text(COVER)
    args = [str(md)] + ([] if pdf else ["--no-pdf"])
    r = _run(temp_root, home, "templates/cover_letter/render.py", *args)
    assert r.returncode == 0, r.stderr
    tex = (d / "cover_letter.tex").read_text()
    # identity comes from the (fixture) profile next to templates/, not from the real repo
    assert r"\textbf{Alex Example}" in tex and "alex@example.com" in tex
    assert r"Initech \textbar{} Software Engineer, Backend" in tex and r"\textbf{data you can trust}" in tex
    paras = (d / "cover_letter.txt").read_text().strip().split("\n\n")
    assert paras[0] == "Hi Payments team," and paras[-1] == "Alex" and len(paras) == 5
    assert "**" not in "".join(paras)
    if pdf:
        pages, text = _pdf_pages_and_text(d / "cover_letter.pdf")
        assert pages == 1 and "Alex Example" in text


def test_rerender_with_failing_engine_exits_1_and_leaves_no_stale_pdf(temp_root: Path, home: Path, resume_json: Path,
                                                                       tmp_path: Path):
    """A second render whose LaTeX step fails must not leave the first run's resume.pdf to be uploaded."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "tectonic").write_text("#!/bin/sh\necho '! LaTeX Error: boom'\nexit 1\n")
    (fake_bin / "tectonic").chmod(0o755)
    (resume_json.parent / "resume.pdf").write_text("OLD RUN")
    env = subprocess_env(temp_root, home)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    r = subprocess.run([PY, str(temp_root / "templates/resume/render.py"), str(resume_json)], capture_output=True,
                       text=True, cwd=temp_root, env=env, timeout=120)
    assert r.returncode == 1 and "tectonic failed" in r.stderr
    assert not (resume_json.parent / "resume.pdf").exists()
    assert (resume_json.parent / "resume.tex").exists()
