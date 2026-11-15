"""Deterministic bullet shortlist (bullet_index.pick): greedy weighted cover of posting keywords by master bullets."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import make_temp_root

from careeros import bullet_index

pytestmark = pytest.mark.unit

PROFILE = {
    "skills": {"programming": ["Python", "Go", "C"], "tools": ["Kafka", "Docker", "Redis"], "concepts": ["Concept X"]},
    "experience": [
        {"id": "e1", "company": "Acme", "start": "2024-01", "end": "present", "tags": ["swe_backend"],
         "stack": ["Python", "Kafka", "Redis"],
         "bullets": [
             {"id": "e1.1", "text": "Built a **Python** service that ingests events, 2 million per day"},
             {"id": "e1.2", "text": "Deployed services with Docker to production"},
             {"id": "e1.3", "text": "Wrote a Go CLI for deploys", "variants": {"short": "Wrote a Go CLI"}},
             {"id": "e1.4", "text": "[OPEN: fill in later]", "placeholder": True},
             {"id": "e1.5", "text": "Python Kafka Redis Docker everything at once", "resume_default": False},
             {"id": "e1.6", "text": "Mentored two interns on team practices"},
         ]},
        {"id": "e2", "company": "Initech", "start": "2022-01", "end": "2023-01", "tags": [],
         "stack": ["Kafka"],
         "bullets": [{"id": "e2.1", "text": "Operated Kafka consumers for billing"},
                     {"id": "e2.2", "text": "Documented runbooks for the team"}]},
        {"id": "e3", "company": "Thin", "start": "2021-01", "end": "2021-06", "tags": [],
         "bullets": [{"id": "e3.1", "text": "Only one real bullet Python"},
                     {"id": "e3.2", "text": "[FILL IN]", "placeholder": True}]},
    ],
    "projects": [
        {"id": "p1", "name": "Proj", "date": "2025-01", "tags": ["swe_backend"], "stack": ["Go"],
         "bullets": [{"id": "p1.1", "text": "Built a Go tool for log search"}]},
    ],
}


def _settings(profile=PROFILE):
    return SimpleNamespace(profile=profile, pipeline={})


def _job(tmp_path: Path, req, pref=(), desc="") -> Path:
    d = tmp_path / f"j{len(list(tmp_path.iterdir()))}"
    d.mkdir()
    (d / "posting.json").write_text(json.dumps({"job_id": "j1", "title": "Backend Engineer", "description_text": desc}))
    (d / "score.json").write_text(json.dumps({"category": "swe_backend", "required_skills": list(req),
                                              "preferred_skills": list(pref)}))
    return d


def _ids(out):
    return [b["id"] for e in out["entries"] for b in e["bullets"]]


def test_python_asked_picks_python_bullet(tmp_path):
    out = bullet_index.pick(_settings(), _job(tmp_path, ["Python"]))
    assert "e1.1" in _ids(out)
    e1 = next(e for e in out["entries"] if e["id"] == "e1")
    assert next(b for b in e1["bullets"] if b["id"] == "e1.1")["covers"] == ["Python"]
    assert out["uncovered"]["required"] == []


def test_placeholders_and_resume_default_false_excluded(tmp_path):
    out = bullet_index.pick(_settings(), _job(tmp_path, ["Python", "Kafka", "Redis", "Docker"]))
    ids = _ids(out)
    assert "e1.4" not in ids and "e3.2" not in ids and "e1.5" not in ids


def test_budget_respected(tmp_path):
    out = bullet_index.pick(_settings(), _job(tmp_path, ["Python", "Go", "Kafka", "Docker"]),
                            max_bullets=3, max_words=550)
    assert len(_ids(out)) <= 3 + out["budget"]["min_overrun"]
    out = bullet_index.pick(_settings(), _job(tmp_path, ["Python"]), max_bullets=14, max_words=12)
    assert out["totals"]["words"] <= 12 + out["budget"]["min_overrun_words"]


def test_uncovered_keywords_reported_with_priority(tmp_path):
    out = bullet_index.pick(_settings(), _job(tmp_path, ["Python", "Rust"], pref=["Terraform"]))
    assert out["uncovered"] == {"required": ["Rust"], "preferred": ["Terraform"]}


def test_required_beats_preferred_when_budget_tight(tmp_path):
    # one slot beyond the minimums: Go (required) must win over Docker (preferred)
    out = bullet_index.pick(_settings(), _job(tmp_path, ["Go"], pref=["Docker"]), max_bullets=5)
    assert "e1.3" in _ids(out) or "p1.1" in _ids(out)


def test_skills_listed_without_evidence_reported(tmp_path):
    # posting mentions Redis and Docker; only Docker has a bullet. Redis is in stack only: not evidence.
    out = bullet_index.pick(_settings(), _job(tmp_path, ["Python"], desc="We use Redis and Docker daily."))
    assert "Redis" in out["skills_without_evidence"]
    assert "Docker" not in out["skills_without_evidence"]
    assert "Docker" in " ".join(b["covers"][0] for e in out["entries"] for b in e["bullets"] if b["covers"])


def test_entry_with_one_eligible_bullet_skipped(tmp_path):
    out = bullet_index.pick(_settings(), _job(tmp_path, ["Python"]))
    assert "e3" not in [e["id"] for e in out["entries"]]
    assert any(s["id"] == "e3" for s in out["skipped_entries"])


def test_experience_min_two_and_only_master_ids(tmp_path):
    out = bullet_index.pick(_settings(), _job(tmp_path, ["Python"]))
    master = {b["id"] for sec in ("experience", "projects") for e in PROFILE[sec] for b in e["bullets"]}
    assert set(_ids(out)) <= master
    for e in out["entries"]:
        assert len(e["bullets"]) >= (2 if e["section"] == "experience" else 1)


def test_write_and_cli_compare(tmp_path, capsys):
    from careeros.cli import main

    root = make_temp_root(tmp_path / "repo")
    d = root / "data" / "jobs" / "j9"
    d.mkdir(parents=True)
    (d / "posting.json").write_text(json.dumps({"job_id": "j9", "title": "Backend Engineer",
                                                "description_text": "Python and Kafka"}))
    (d / "score.json").write_text(json.dumps({"category": "swe_backend", "required_skills": ["Python", "Kafka"]}))
    (d / "qa.json").write_text(json.dumps({"pass": True}))
    (d / "resume.txt").write_text("- Built a Python service\n- Wrote docs\n")
    assert main(["--root", str(root), "resume", "shortlist", "j9", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["uncovered"]["required"] == [] and (d / "bullet_shortlist.json").is_file()
    assert main(["--root", str(root), "resume", "shortlist", "--compare", "--json"]) == 0
    row = json.loads(capsys.readouterr().out)["jobs"][0]
    assert row["job_id"] == "j9" and row["shortlist"] == 1.0 and row["resume"] == 0.5
