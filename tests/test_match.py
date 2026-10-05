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
