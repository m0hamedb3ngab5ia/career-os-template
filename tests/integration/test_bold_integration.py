"""The example résumé with **bold** markers in bullet text -> render.py subprocess -> .tex (\\textbf), plain
resume.txt, PDF text without markers -> `python -m careeros.qa`: same hard verdict as the unmarked résumé."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import FIXTURES, PY, build_resume_json, personalize_identity, subprocess_env, tectonic_cache
from test_qa import COVER_LETTER

from careeros.markup import bold_spans, strip_bold

pytestmark = pytest.mark.integration

HAS_ENGINE = bool((shutil.which("tectonic") and tectonic_cache()) or shutil.which("pdflatex"))  # offline only
BULLETS = ["acme.1", "acme.2", "acme.3", "initech_intern.1", "widgetizer.1"]


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def _run(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], capture_output=True, text=True, cwd=root, env=subprocess_env(root, home),
                          timeout=300)


def _prepare(root: Path, home: Path) -> Path:
    d = root / "data" / "jobs" / "t1"
    d.mkdir(parents=True, exist_ok=True)
    posting = json.loads((FIXTURES / "example_posting.json").read_text())
    posting["job_id"] = "t1"
    (d / "posting.json").write_text(json.dumps(posting))
    (d / "score.json").write_text(json.dumps({"job_id": "t1", "category": "swe_backend", "fit": 80,
                                              "required_skills": ["Python", "SQL", "AWS", "PostgreSQL", "Kafka"]}))
    prof = yaml.safe_load((root / "profile" / "master.yaml").read_text())
    (d / "resume.json").write_text(json.dumps(build_resume_json(prof, BULLETS, job_id="t1"), indent=2))
    r = _run(root, home, "templates/resume/render.py", str(d / "resume.json"), *([] if HAS_ENGINE else ["--no-pdf"]))
    assert r.returncode == 0, r.stderr
    (d / "cover_letter.md").write_text(COVER_LETTER)
    (d / "answers.json").write_text(json.dumps([{"question": "Are you legally authorized to work in the US?",
                                                 "answer": "Yes", "type": "standard", "standard_key": "work_authorization",
                                                 "needs_review": False}]))
    return d


def _qa(root: Path, home: Path, d: Path) -> dict:
    return json.loads(_run(root, home, "-m", "careeros.qa", str(d)).stdout)


def _strip_profile(root: Path) -> None:
    p = root / "profile" / "master.yaml"
    m = yaml.safe_load(p.read_text())
    for sec in ("experience", "projects", "leadership"):
        for e in m.get(sec) or []:
            for b in e.get("bullets") or []:
                b["text"] = strip_bold(b["text"])
                if isinstance(b.get("variants"), dict):
                    b["variants"] = {k: strip_bold(v) for k, v in b["variants"].items()}
    p.write_text(yaml.safe_dump(m, sort_keys=False))


def test_marked_example_renders_bold_and_qa_matches_unmarked(temp_root: Path, home: Path):
    personalize_identity(temp_root)  # the untouched example identity is a hard QA fail (example_identity)
    prof = yaml.safe_load((temp_root / "profile" / "master.yaml").read_text())
    spans = [s for e in prof["experience"] for b in e["bullets"] if b["id"] in BULLETS for s in bold_spans(b["text"])]
    assert "FastAPI" in spans and "2 million events per day" in spans  # the example shows the style

    d = _prepare(temp_root, home)
    assert "**FastAPI**" in (d / "resume.json").read_text()
    tex = (d / "resume.tex").read_text()
    assert r"\textbf{FastAPI}" in tex and r"\textbf{2 million events per day}" in tex
    assert "**" not in tex
    txt = (d / "resume.txt").read_text()
    assert "**" not in txt and "- Built a FastAPI service in Python that ingests Kafka" in txt
    if HAS_ENGINE:
        pypdf = pytest.importorskip("pypdf")
        text = "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(str(d / "resume.pdf")).pages)
        assert "*" not in text and "FastAPI" in text

    marked = _qa(temp_root, home, d)
    assert marked["pass"] is True, marked["fail_reasons"]
    checks = {c["check"]: c for c in marked["checks"]}
    for name in ("bold_markup", "no_markdown_bold", "bullet_fidelity", "tool_audit", "number_audit:resume.txt"):
        assert checks[name]["ok"] and not checks[name].get("skipped"), (name, checks[name]["detail"])
    if HAS_ENGINE:
        assert checks["pdf_text_matches_resume"]["ok"], checks["pdf_text_matches_resume"]["detail"]
        assert "pdf_hidden_text" not in checks, checks.get("pdf_hidden_text")

    # the same job with every marker removed from profile + resume.json: identical hard verdicts
    _strip_profile(temp_root)
    shutil.rmtree(d)
    d = _prepare(temp_root, home)
    assert "**" not in (d / "resume.json").read_text()
    assert (d / "resume.txt").read_text() == txt
    plain = _qa(temp_root, home, d)
    hard = lambda res: {c["check"]: c["ok"] for c in res["checks"] if c["level"] == "hard"}  # noqa: E731
    assert hard(marked) == hard(plain)
    assert marked["keyword_coverage"] == plain["keyword_coverage"] == 1.0
    assert marked["bullet_shape"] == plain["bullet_shape"]
