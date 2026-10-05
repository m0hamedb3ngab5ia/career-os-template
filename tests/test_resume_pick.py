"""TASK-011 / REQ-112, REQ-113, DEC-007: résumé pick (reuse / tweak / tailor) before prepare-job."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_temp_root

from careeros import match, resumes
from careeros.config import Settings
from careeros.qa import Checker

pytestmark = pytest.mark.unit

PDF = b"%PDF-1.4\nnot really a pdf\n"
SKILLS = ["Python", "Kafka", "PostgreSQL", "React", "TypeScript"]


def _job(root: Path, jid: str, required: list[str] | None = SKILLS) -> Path:
    d = root / "data" / "jobs" / jid
    d.mkdir(parents=True)
    (d / "posting.json").write_text(json.dumps({"job_id": jid, "company": "Acme", "title": "Backend Engineer"}))
    (d / "score.json").write_text(json.dumps({"required_skills": required or [], "category": "swe_backend"}))
    return d


def _resume(root: Path, name: str, text: str) -> str:
    rid = resumes.add(root, "cv.pdf", PDF, name=name)["rid"]
    resumes.add_text(root, rid, text, author="user", source="edit")
    return rid


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_temp_root(tmp_path / "repo")


def test_req_112_best_above_threshold_is_reused_and_linked(root):
    _resume(root, "Main", "Python backend engineer")
    rid = _resume(root, "Backend", "Python Kafka PostgreSQL React TypeScript backend engineer")
    d = _job(root, "j1")
    c = match.pick(Settings.load(root), d)
    assert c["action"] == "reuse" and c["rid"] == rid and c["score"] == 100 and c["author"] == "user"
    assert json.loads((d / "resume_choice.json").read_text()) == c
    assert "Kafka" in (d / "resume.txt").read_text()
    assert json.loads((d / "resume.json").read_text())["reused"]["rid"] == rid


def test_req_113_tweak_when_worth_it_then_saved_variant_is_reused(root):
    _resume(root, "Main", "Python backend engineer")  # 30 vs threshold 70
    s = Settings.load(root)
    d1 = _job(root, "j1")
    c = match.pick(s, d1)
    assert c["action"] == "tweak" and c["score"] == 30 and c["estimate"] == 100
    assert sorted(c["add_bullet_ids"]) == ["acme.1", "acme.2"]  # master.yaml ids only, <= 3
    (d1 / "resume.txt").write_text("Python Kafka PostgreSQL React TypeScript backend engineer")
    meta = match.save_tailored(s, d1)
    assert meta["type"] == "tailored" and meta["category"] == "swe_backend"
    assert meta["versions"][0]["author"] == "ai" and meta["versions"][0]["source"] == "job:j1"
    c2 = match.pick(s, _job(root, "j2"))
    assert c2["action"] == "reuse" and c2["rid"] == meta["rid"] and c2["author"] == "ai"


def test_tailor_when_no_bullet_helps_and_when_unscored(root):
    _resume(root, "Main", "Python backend engineer")
    s = Settings.load(root)
    c = match.pick(s, _job(root, "j1", ["Rust", "Haskell"]))
    assert c["action"] == "tailor" and "tweak" in c["reason"]
    u = match.pick(s, _job(root, "j2", None))
    assert u["action"] == "tailor" and u["scored"] is False


def test_save_tailored_only_for_tailor_or_tweak(root):
    _resume(root, "Backend", "Python Kafka PostgreSQL React TypeScript backend engineer")
    s = Settings.load(root)
    d = _job(root, "j1")
    match.pick(s, d)  # reuse
    assert match.save_tailored(s, d) is None


def test_dec_007_user_reuse_skips_bullet_trace_checks(root):
    _resume(root, "Backend", "Python Kafka PostgreSQL React TypeScript backend engineer, 7 years")
    d = _job(root, "j1")
    match.pick(Settings.load(root), d)
    ck = Checker(d, root)
    ck.check_bullet_fidelity()
    ck.check_numbers()
    by = {x["check"]: x for x in ck.checks}
    assert by["bullet_fidelity"].get("skipped")
    assert "number_audit:resume.txt" not in by
    assert "resume.json" not in ck._cited_ids()
