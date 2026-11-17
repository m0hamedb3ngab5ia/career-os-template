"""Deterministic skill-evidence post-pass: a missing skill moves to matched only with a real profile evidence id."""
from __future__ import annotations

import json

import pytest

from careeros import skill_evidence as se

pytestmark = pytest.mark.unit

PROFILE = {
    "skills": {"programming": ["Python", "Java"], "tools": ["Docker"]},
    "skill_groups": [{"label": "Cloud & DevOps", "items": ["Linux", "Bash"]}],
    "experience": [{"id": "acme", "stack": ["Kafka", "Spring Boot"], "bullets": [
        {"id": "acme.1", "text": "Built a **REST** service for trade events."},
        {"id": "acme.2", "text": "Added monitoring dashboards in Kibana for batch jobs."},
        {"id": "acme.3", "text": "[FILL IN: monitoring with Grafana]"},
    ]}],
    "projects": [{"id": "proj", "stack": ["Python"], "bullets": [
        {"id": "proj.1", "text": "Ran nightly jobs on RHEL hosts."}]}],
}
IMPLIES = {
    "distributed systems": ["kafka", "event-driven", "microservices"],
    "observability": ["monitoring", "kibana", "grafana", "splunk", "geneos"],
    "linux": ["rhel", "ubuntu"],
}
SYN = {"kubernetes": ["k8s"]}


def _score(required, matched, **kw):
    s = {"required_skills": required, "matched_skills": matched,
         "missing_skills": [x for x in required if x not in matched], "skill_evidence": {m: "skills.programming" for m in matched},
         "fit": 66, "fit_breakdown": {"skills_overlap": round(40 * len(matched) / len(required)), "experience_relevance": 22,
                                      "seniority_match": 15, "location_pref": 10, "industry_boost": 0, "prestige_bonus": 0},
         "fit_reasons": ["Skills: old sentence.", "Seniority: early-career role, a match."],
         "tier": "C", "decision": "skip", "skip_reason": "below_min_fit", "hard_filter_fails": []}
    s.update(kw)
    s["fit"] = sum(s["fit_breakdown"].values())
    return s


def test_skill_listed_only_in_skill_groups_is_credited():
    # root cause: Linux sits in skill_groups, which the scorer's evidence ids never covered
    out = se.credit(["Linux"], PROFILE, SYN, {})
    assert out == {"Linux": "skill_groups.Cloud & DevOps"}


def test_distributed_systems_implied_by_kafka_stack():
    assert se.credit(["Distributed Systems"], PROFILE, SYN, IMPLIES) == {"Distributed Systems": "acme.stack"}


def test_observability_implied_by_monitoring_bullet():
    assert se.credit(["Observability"], PROFILE, SYN, IMPLIES) == {"Observability": "acme.2"}


def test_linux_implied_by_rhel_bullet_when_not_listed():
    prof = {**PROFILE, "skill_groups": []}
    assert se.credit(["Linux"], prof, SYN, IMPLIES) == {"Linux": "proj.1"}


def test_no_evidence_stays_missing():
    prof = {"skills": {"programming": ["Python"]}, "experience": [{"id": "x", "stack": ["Go"], "bullets": [
        {"id": "x.1", "text": "Wrote a CLI."}]}]}
    assert se.credit(["Distributed Systems", "Observability", "Linux", "Rust"], prof, SYN, IMPLIES) == {}


def test_placeholder_bullet_is_never_evidence():
    prof = {"experience": [PROFILE["experience"][0] | {"stack": [], "bullets": [PROFILE["experience"][0]["bullets"][2]]}]}
    assert se.credit(["Observability"], prof, SYN, IMPLIES) == {}


def test_implication_is_one_way():
    # "distributed systems" in the profile never evidences Kafka
    prof = {"skills": {"concepts": ["Distributed Systems"]}}
    assert se.credit(["Kafka"], prof, SYN, IMPLIES) == {}


def test_synonym_credits():
    prof = {"skills": {"tools": ["K8s"]}}
    assert se.credit(["Kubernetes"], prof, SYN, {}) == {"Kubernetes": "skills.tools"}


def test_apply_recomputes_overlap_and_flips_decision():
    s = _score(["Python", "Linux", "Distributed Systems", "Go"], ["Python"])  # overlap 10 -> fit 57
    th = {"min_fit_to_prepare": 70, "tier_a_min_fit": 50, "min_fit_nonpreferred_location": 80}
    ch = se.apply(s, PROFILE, SYN, IMPLIES, th)
    assert ch["credited"] == {"Linux": "skill_groups.Cloud & DevOps", "Distributed Systems": "acme.stack"}
    assert s["matched_skills"] == ["Python", "Linux", "Distributed Systems"] and s["missing_skills"] == ["Go"]
    assert s["skill_evidence"]["Linux"] == "skill_groups.Cloud & DevOps"
    assert s["fit_breakdown"]["skills_overlap"] == 30 and s["fit"] == 77
    assert (s["decision"], s["skip_reason"]) == ("prepare", None)
    assert s["fit_reasons"][0] == "Skills: 3 of 4 required matched; missing Go."
    assert ch["old_fit"] == 57 and ch["old_decision"] == "skip"


def test_apply_keeps_skip_below_threshold_and_on_hard_fail():
    th = {"min_fit_to_prepare": 90, "tier_a_min_fit": 90, "min_fit_nonpreferred_location": 80}
    s = _score(["Python", "Linux", "Go", "Rust"], ["Python"])
    se.apply(s, PROFILE, SYN, IMPLIES, th)
    assert s["decision"] == "skip" and s["skip_reason"] == "below_min_fit"
    hard = _score(["Python", "Linux", "Go"], ["Python"], skip_reason="visa", hard_filter_fails=["visa"])
    se.apply(hard, PROFILE, SYN, IMPLIES, {"min_fit_to_prepare": 0})
    assert hard["decision"] == "skip" and hard["skip_reason"] == "visa"


def test_apply_location_rule_needs_nonpreferred_threshold():
    th = {"min_fit_to_prepare": 70, "tier_a_min_fit": 50, "min_fit_nonpreferred_location": 85}
    s = _score(["Python", "Linux", "Distributed Systems", "Go"], ["Python"], skip_reason="location_nonpreferred_low_fit")
    se.apply(s, PROFILE, SYN, IMPLIES, th)
    assert s["fit"] == 77 and s["decision"] == "skip" and s["skip_reason"] == "location_nonpreferred_low_fit"


def test_recredit_dry_run_does_not_write(settings):
    jd = settings.paths["jobs_dir"] / "j1"
    jd.mkdir(parents=True)
    s = _score(["Python", "Kafka", "Go"], ["Python"])
    (jd / "score.json").write_text(json.dumps(s))
    rows = se.recredit(settings, min_fit=0, write=False)
    assert [r["job_id"] for r in rows] == ["j1"]
    assert json.loads((jd / "score.json").read_text()) == s


def test_cli_jobs_recredit_dry_run(tmp_path, capsys):
    from careeros.cli import main
    from tests.conftest import make_temp_root

    root = make_temp_root(tmp_path / "repo")
    d = root / "data" / "jobs" / "job000000001"
    d.mkdir(parents=True)
    s = _score(["Python", "Kafka", "Go"], ["Python"])
    (d / "score.json").write_text(json.dumps(s))
    assert main(["--root", str(root), "jobs", "recredit", "--min-fit", "0", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows["jobs"][0]["credited"] == {"Kafka": "skills.tools"} and rows["written"] is False
    assert json.loads((d / "score.json").read_text()) == s


RULES = [{"if": "company_in dream_list", "tier": "A"}, {"if": "fit >= 85", "tier": "B"}, {"if": "fit >= 70", "tier": "C"}]
TH = {"min_fit_to_prepare": 70, "tier_a_min_fit": 50, "min_fit_nonpreferred_location": 80}


def test_apply_recomputes_tier_into_c():
    s = _score(["Python", "Linux", "Distributed Systems", "Go"], ["Python"], tier=None)  # fit 57 -> 77
    se.apply(s, PROFILE, SYN, IMPLIES, TH, RULES, dream=False)
    assert s["fit"] == 77 and s["tier"] == "C"


def test_apply_recomputes_tier_into_b():
    s = _score(["Python", "Linux", "Kafka"], [], tier=None, fit_breakdown={
        "skills_overlap": 0, "experience_relevance": 20, "seniority_match": 15, "location_pref": 10,
        "industry_boost": 0, "prestige_bonus": 0})  # fit 45 -> 85
    se.apply(s, PROFILE, SYN, IMPLIES, TH, RULES, dream=False)
    assert s["fit"] == 85 and s["tier"] == "B"


def test_apply_dream_company_stays_a():
    s = _score(["Python", "Linux", "Distributed Systems", "Go"], ["Python"], tier="A")
    se.apply(s, PROFILE, SYN, IMPLIES, TH, RULES, dream=True)
    assert s["tier"] == "A"


@pytest.mark.integration
def test_recredit_write_updates_status_json_and_tracker(settings):
    from careeros.store import Store
    jd = settings.paths["jobs_dir"] / "j2"
    jd.mkdir(parents=True)
    settings.profile["skills"] = {"programming": ["Python", "Kafka", "Go"]}
    s = _score(["Python", "Kafka", "Go"], ["Python"])
    (jd / "score.json").write_text(json.dumps(s))
    calls = []
    import careeros.tracker as tr
    orig = tr.set_status_both
    tr.set_status_both = lambda *a, **k: (calls.append(a), orig(*a, **k))[1]
    try:
        rows = se.recredit(settings, min_fit=0, write=True)
    finally:
        tr.set_status_both = orig
    assert rows and rows[0]["decision"] == "prepare"
    assert calls and calls[0][1:3] == ("j2", "scored")
    assert Store(settings).get_status("j2") == "scored"


def test_apply_redecides_under_a_lowered_threshold_without_new_evidence():
    s = _score(["Python", "Kafka", "Go"], ["Python"], fit=65)
    ch = se.apply(s, {}, {}, {}, {"min_fit_to_prepare": 60})
    assert ch["credited"] == {} and ch["decision"] == "prepare" and s["skip_reason"] is None


def test_recredit_lists_a_threshold_flip_with_no_credit(settings):
    jd = settings.paths["jobs_dir"] / "j3"
    jd.mkdir(parents=True)
    (jd / "score.json").write_text(json.dumps(_score(["Rust", "Go", "Zig"], [], fit=62)))
    settings.targets.setdefault("thresholds", {})["min_fit_to_prepare"] = 45
    rows = se.recredit(settings, min_fit=0, write=False)
    assert [(r["job_id"], r["decision"]) for r in rows] == [("j3", "prepare")]


def test_cli_recredit_default_reaches_a_cutoff_below_55(tmp_path, capsys):
    from careeros.cli import main
    from tests.conftest import make_temp_root

    root = make_temp_root(tmp_path / "repo")
    t = root / "config" / "targets.yaml"
    t.write_text(t.read_text().replace("min_fit_to_prepare: 70", "min_fit_to_prepare: 45"))
    d = root / "data" / "jobs" / "job000000002"
    d.mkdir(parents=True)
    (d / "score.json").write_text(json.dumps(_score(["Rust", "Go", "Zig"], [])))  # fit 47, nothing creditable
    assert main(["--root", str(root), "jobs", "recredit"]) == 0
    out = capsys.readouterr().out
    assert "skip -> prepare" in out and "0 gain evidenced skills" in out and "1 flip to prepare" in out
