"""Résumé match score (REQ-111, DEC-003): deterministic weighted term coverage."""
from __future__ import annotations

import pytest

from careeros import match

pytestmark = pytest.mark.unit

REQ = ["Python", "Go", "Kubernetes", "PostgreSQL", "Kafka", "Terraform", "AWS", "Docker", "gRPC", "Redis"]
TEXT = "Built Python and Go services on AWS with Docker, gRPC, Redis and PostgreSQL. Governance lead."


def test_accept_111_same_score_every_run_lists_missing():
    a = match.score(TEXT, REQ, [], "")
    assert a == match.score(TEXT, REQ, [], "")
    assert a["score"] == 70
    assert a["missing"] == ["Kubernetes", "Kafka", "Terraform"]


def test_weights_renormalised_over_groups():
    r = match.score("python", ["Python", "Java"], ["Rust"], "Backend Engineer")
    # req 1/2, pref 0/1, title 0/2 -> 100*(0.7*0.5) = 35
    assert r["score"] == 35
    assert r["groups"]["title"]["missing"] == ["backend", "engineer"]
    assert match.score("python", [], [], "")["score"] == 0


def test_title_terms_drop_stopwords_and_dedupe():
    assert match.title_terms("Senior Software Engineer, Backend & Platform (Go) - II") == \
        ["senior", "software", "engineer", "backend", "platform", "go"]


def test_variants_and_synonyms():
    assert match.score("CI CD and nodejs", ["CI-CD", "Node.js"], [], "")["score"] == 100
    syn = {"kubernetes": ["k8s"]}
    assert match.score("ran k8s", ["Kubernetes"], [], "", syn)["score"] == 100
    assert match.score("ran kubernetes", ["K8s"], [], "", syn)["score"] == 100
    assert match.score("ran k8s", ["Kubernetes"], [], "")["score"] == 0


def test_skill_in_both_groups_counted_once():
    r = match.score("java", ["Python", "Go"], ["python", "Rust"], "")
    assert r["missing"] == ["Python", "Go", "Rust"]
    assert r["groups"]["preferred"]["missing"] == ["Rust"]


@pytest.mark.parametrize("score_json", [None, "{}", '{"required_skills": [], "nice_to_have_skills": []}', "not json"])
def test_unscored_job_gives_no_score_and_a_hint(tmp_path, score_json):  # PR #130 MUST: no title-only scoring
    from careeros.config import Settings
    jd = tmp_path / "data" / "jobs" / "j1"
    jd.mkdir(parents=True)
    (jd / "posting.json").write_text('{"title": "Backend Engineer"}')
    if score_json is not None:
        (jd / "score.json").write_text(score_json)
    out = match.matches(Settings(root=tmp_path), jd)
    assert out["scored"] is False and out["best"] is None and out["resumes"] == []
    assert "careeros run score --job j1" in out["hint"]


# --- keyword pre-score (REQ-133, TASK-038; DEC-023) -------------------------------------------------------
def test_accept_133_prescore_six_of_ten_master_skills():
    text = "We use Python, Go, Kafka, AWS, Docker and Redis every day."
    assert match.prescore(text, REQ, []) == 60
    assert match.prescore(text, REQ, []) == match.prescore(text, REQ, [])  # deterministic


def test_prescore_adds_category_title_keywords():
    text = "Backend Engineer. We use Python, Go, Kafka, AWS, Docker and Redis."
    assert match.prescore(text, REQ, ["backend engineer", "sde"]) == 68  # 0.8*0.6 + 0.2*1
    assert match.prescore("Nothing relevant here.", REQ, ["backend engineer"]) == 0
    assert match.prescore("Backend engineer", [], ["backend engineer"]) == 100  # no master skills: keywords only
    assert match.prescore("anything", [], []) == 0


def test_prescore_for_uses_master_skill_groups_category_and_synonyms():
    from types import SimpleNamespace

    s = SimpleNamespace(
        profile={"skills": {"programming": ["Python", "Go"], "tools": ["Kafka", "Docker"]}},
        pipeline={"match": {"synonyms": {"Go": ["Golang"]}}},
        title_keywords=lambda: {"swe_backend": ["backend engineer"], "data": ["data engineer"]})
    posting = {"title": "Backend Engineer", "description_text": "Golang and Python services.",
               "raw": {"prefilter_category": "swe_backend"}}
    assert match.prescore_for(s, posting) == 60  # 0.8*2/4 + 0.2*1
    assert match.prescore_for(s, {**posting, "raw": {"prefilter_category": "data"}}) == 40
    assert match.prescore_for(s, {**posting, "raw": {}}) == 50  # category unknown: skills only
