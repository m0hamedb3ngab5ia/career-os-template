"""careeros.ui.services.job_pipeline.compute_state / review_reasons: pure, one case per job state."""
from __future__ import annotations

import pytest

from careeros.ui.services.job_pipeline import TIER_A_BLOCKED, compute_state, review_reasons

pytestmark = pytest.mark.unit

SCORE_B = {"tier": "B", "decision": "prepare", "fit": 80}
SCORE_A = {"tier": "A", "decision": "prepare", "fit": 91}
PREPARED = {"qa_pass": True, "action_items": []}


def act(st):
    return (st["stage"], st["next_action"], st["next_kind"], st["force"], st["blocked_reason"])


def test_found_starts_with_score_and_scored_continues_with_prepare():
    assert act(compute_state("found", None, None, None)) == ("score", "start", "score", False, None)
    assert act(compute_state("scored", SCORE_B, None, None)) == ("prepare", "continue", "prepare", False, None)
    assert compute_state("found", None, None, None)["next_label"] == "Start pipeline"
    # found with a score.json already there (a rerun after `job status`): prepare it
    assert act(compute_state("found", SCORE_B, None, None)) == ("score", "start", "prepare", False, None)


def test_scored_skip_decision_is_blocked():
    st = compute_state("scored", {"tier": "C", "decision": "skip", "skip_reason": "hard_filter:clearance"}, None, None)
    assert st["next_action"] is None and st["blocked_reason"] == "Score decision: skip (hard_filter:clearance)"


def test_needs_review_with_qa_pass_offers_approve_and_continue_to_apply():
    st = compute_state("needs_review", SCORE_B, PREPARED, {"pass": True})
    assert act(st) == ("review", "approve_continue", "apply", False, None)
    assert st["next_label"] == "Approve & continue"


def test_needs_review_without_qa_pass_offers_a_forced_re_prepare():
    assert act(compute_state("needs_review", SCORE_B, {"qa_pass": False}, {"pass": False})) == \
        ("review", "continue", "prepare", True, None)


def test_tier_a_is_blocked_in_review_and_when_queued():
    for status in ("needs_review", "queued", "prepared"):
        st = compute_state(status, SCORE_A, PREPARED, {"pass": True})
        assert st["next_action"] is None and st["blocked_reason"] == TIER_A_BLOCKED, status


def test_queued_with_qa_pass_offers_continue_apply_and_without_it_a_re_prepare():
    st = compute_state("queued", SCORE_B, PREPARED, {"pass": True})
    assert act(st) == ("apply", "continue", "apply", False, None) and st["next_label"] == "Continue pipeline"
    assert act(compute_state("queued", SCORE_B, None, None)) == ("qa", "continue", "prepare", True, None)


@pytest.mark.parametrize("status", ["applied", "skipped", "withdrawn", "interview", "rejected"])
def test_done_statuses_offer_nothing(status):
    st = compute_state(status, SCORE_B, PREPARED, {"pass": True})
    assert st["next_action"] is None and st["blocked_reason"] is None and st["stage"] == "apply"


def test_an_active_run_blocks_and_is_reported():
    st = compute_state("scored", SCORE_B, None, None, active_run_id="20260927-100000-prepare-ab12")
    assert st["next_action"] is None and st["active_run_id"] == "20260927-100000-prepare-ab12"
    assert st["blocked_reason"] == "A run is working on this job"


def test_review_reasons_collect_qa_prepare_and_open_items_deduplicated():
    qa = {"pass": False, "fail_reasons": ["fabricated metric in bullet x3"], "warnings": ["long letter"],
          "deterministic": {"checks": [{"check": "estimate_marked", "ok": False, "detail": "~ missing"},
                                       {"check": "pdf", "ok": True}, {"check": "tex", "ok": False, "skipped": True}]}}
    prep = {"qa_pass": False, "action_items": ["tier_a_review: review resume", "long letter"], "notes": "  "}
    got = review_reasons(qa, prep, ["tier_a_review: review resume", "Answer the salary question"])
    assert got == ["QA: fabricated metric in bullet x3", "QA check estimate_marked: ~ missing", "QA warning: long letter",
                   "tier_a_review: review resume", "long letter", "Open action item: tier_a_review: review resume",
                   "Open action item: Answer the salary question"]
    assert review_reasons(None, None, []) == [] and review_reasons({"checks": "junk"}, {"flags": 3}, []) == []
