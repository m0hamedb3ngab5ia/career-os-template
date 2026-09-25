"""Full job dir (posting + score + resume.json rendered by templates/resume/render.py + cover_letter.md)
-> `python -m careeros.qa <dir>` subprocess -> JSON verdict."""
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
    personalize_identity(temp_root)  # the untouched example identity is a hard QA fail (example_identity)
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
                                                 "answer": "Yes", "type": "standard", "standard_key": "work_authorization",
                                                 "needs_review": False}]))
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


def test_rewritten_bullet_and_contradicted_standard_answer_fail_strict(temp_root: Path, home: Path, job_dir: Path):
    """Valid ids with fabricated text, and a legal answer contradicting profile/standard_answers.yaml."""
    rj = json.loads((job_dir / "resume.json").read_text())
    rj["experience"][0]["bullets"][0]["text"] = "Led company-wide hiring strategy and managed executive stakeholders"
    rj["skills"]["tools"] = list(rj["skills"].get("tools") or []) + ["terraform"]
    rj["experience"][0]["company"] = "Google"  # fabricated employer on a real entry id
    (job_dir / "resume.json").write_text(json.dumps(rj))
    ans = json.loads((job_dir / "answers.json").read_text())
    ans[0]["answer"] = "No"
    (job_dir / "answers.json").write_text(json.dumps(ans))
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert code == 1 and res["pass"] is False
    failed = {r.split(":")[0] for r in res["fail_reasons"]}
    assert {"bullet_fidelity", "entry_headers", "skills_traced", "standard_answers"} <= failed


def test_untouched_example_identity_fails_strict(temp_root: Path, home: Path, job_dir: Path):
    """Same job dir, but the resume still carries Alex Example's name/email (a copy nobody filled in)."""
    txt = (job_dir / "resume.txt").read_text()
    prof = yaml.safe_load((temp_root / "profile" / "master.yaml").read_text())
    (job_dir / "resume.txt").write_text(txt.replace(prof["identity"]["name"], "Alex Example"))
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert code == 1 and res["pass"] is False
    assert any(r.startswith("example_identity:") and "Alex Example" in r for r in res["fail_reasons"])


def test_weak_bullet_is_a_soft_bullet_shape_warning(temp_root: Path, home: Path, job_dir: Path):
    """A real profile bullet with a weak opener and no metric renders, passes every hard check (it is true),
    and shows up only as a bullet_shape warning naming its id."""
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert code == 0 and {c["check"]: c for c in res["checks"]}["bullet_shape"]["ok"]

    weak = "Worked on the reconciliation job for the finance group"
    prof_path = temp_root / "profile" / "master.yaml"
    prof = yaml.safe_load(prof_path.read_text())
    prof["experience"][0]["bullets"].append({"id": "acme.5", "text": weak, "weak": True})
    prof_path.write_text(yaml.safe_dump(prof, sort_keys=False))
    rj = json.loads((job_dir / "resume.json").read_text())
    rj["experience"][0]["bullets"].append({"id": "acme.5", "text": weak})
    (job_dir / "resume.json").write_text(json.dumps(rj))
    assert _run(temp_root, home, "templates/resume/render.py", str(job_dir / "resume.json"), "--txt-only").returncode == 0
    assert f"- {weak}" in (job_dir / "resume.txt").read_text()

    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert code == 0 and res["pass"] is True, res["fail_reasons"]
    shape = {c["check"]: c for c in res["checks"]}["bullet_shape"]
    assert shape["level"] == "soft" and not shape["ok"] and "acme.5: weak_opener, no_metric" in shape["detail"]
    assert res["bullet_shape"] == [{"id": "acme.5", "line": weak, "issues": ["weak_opener", "no_metric"]}]


def test_candidate_estimate_keeps_its_tilde_through_render_and_qa(temp_root: Path, home: Path, job_dir: Path):
    """An `estimate: true` bullet ("~40") renders with its "~" and passes; the same résumé with the "~" dropped
    passes bullet_fidelity and number_audit (both ignore "~") but hard-fails estimate_marked."""
    prof_path = temp_root / "profile" / "master.yaml"
    prof = yaml.safe_load(prof_path.read_text())
    b = prof["experience"][0]["bullets"][1]
    b.update(text=b["text"].replace("40 analysts", "~40 analysts"), metrics=["~40"], estimate=True)
    b.pop("variants", None)
    prof_path.write_text(yaml.safe_dump(prof, sort_keys=False))
    (job_dir / "resume.json").write_text(json.dumps(build_resume_json(prof, BULLETS, job_id="t1"), indent=2))
    assert _run(temp_root, home, "templates/resume/render.py", str(job_dir / "resume.json"), "--txt-only").returncode == 0
    assert "~40 analysts" in (job_dir / "resume.txt").read_text()
    code, res = _qa(temp_root, home, job_dir, "--strict")
    assert code == 0 and res["pass"] is True, res["fail_reasons"]

    (job_dir / "resume.txt").write_text((job_dir / "resume.txt").read_text().replace("~40 analysts", "40 analysts"))
    code, res = _qa(temp_root, home, job_dir, "--strict")
    checks = {c["check"]: c for c in res["checks"]}
    assert code == 1 and res["pass"] is False
    assert checks["bullet_fidelity"]["ok"] and checks["number_audit:resume.txt"]["ok"]
    assert any(r.startswith("estimate_marked: resume.txt: acme.2 estimate 40 shown without ~") for r in res["fail_reasons"])
