"""careeros.ui.services.job_pipeline.compute_state / review_reasons: pure, one case per job state."""
from __future__ import annotations

import re

import pytest

from careeros.ui.services.job_pipeline import APPLY_STAGED, STAGE_NOTE, TIER_A_NOTE, compute_state, review_reasons

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


def test_tier_a_offers_an_assisted_apply_in_review_and_when_queued():
    """Tier A is not refused: the apply stage is offered as fill & stage for review, with a note; the runner passes
    CAREEROS_AUTO_SUBMIT=0 so the run never submits it."""
    for status, action in (("needs_review", "approve_continue"), ("queued", "continue"), ("prepared", "continue")):
        st = compute_state(status, SCORE_A, PREPARED, {"pass": True})
        assert (st["next_action"], st["next_kind"], st["blocked_reason"]) == (action, "apply", None), status
        assert st["next_label"] == "Prepare & stage for review" and st["note"] == TIER_A_NOTE, status
    b = compute_state("queued", SCORE_B, PREPARED, {"pass": True}, auto_submit=True)
    assert b["note"] is None and b["next_label"] == "Continue pipeline"
    staged = compute_state("needs_review", SCORE_A, PREPARED, {"pass": True}, apply_session={"outcome": "staged"})
    assert staged["next_action"] is None and staged["blocked_reason"] == APPLY_STAGED and staged["note"] is None


def test_apply_is_labelled_stage_for_review_for_every_tier_while_auto_submit_is_off():
    off = compute_state("queued", SCORE_B, PREPARED, {"pass": True})
    assert (off["next_label"], off["note"]) == ("Prepare & stage for review", STAGE_NOTE)
    on = compute_state("queued", SCORE_B, PREPARED, {"pass": True}, auto_submit=True)
    assert (on["next_label"], on["note"]) == ("Continue pipeline", None)
    gate = compute_state("needs_review", SCORE_B, PREPARED, {"pass": True})  # the Approve gate keeps its label
    assert (gate["next_label"], gate["note"]) == ("Approve & continue", STAGE_NOTE)
    tier_a = compute_state("queued", SCORE_A, PREPARED, {"pass": True}, auto_submit=True)  # never submitted
    assert (tier_a["next_label"], tier_a["note"]) == ("Prepare & stage for review", TIER_A_NOTE)


def test_a_staged_session_blocks_a_queued_job_too():
    st = compute_state("queued", SCORE_B, PREPARED, {"pass": True}, apply_session={"outcome": "staged"})
    assert (st["next_action"], st["blocked_reason"]) == (None, APPLY_STAGED)
    st = compute_state("prepared", SCORE_B, PREPARED, {"pass": True}, apply_session={"outcome": "submitted"})
    assert st["next_action"] is None and st["blocked_reason"].startswith("Application submitted in the browser")


def test_auto_submit_switch_is_reported_so_the_ui_only_chains_into_apply_while_it_is_off():
    assert compute_state("queued", SCORE_B, PREPARED, {"pass": True})["auto_submit"] is False
    assert compute_state("queued", SCORE_B, PREPARED, {"pass": True}, auto_submit=True)["auto_submit"] is True
    assert compute_state("found", None, None, None)["auto_submit"] is False


def test_queued_with_qa_pass_offers_continue_apply_and_without_it_a_re_prepare():
    st = compute_state("queued", SCORE_B, PREPARED, {"pass": True}, auto_submit=True)
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


def test_review_reasons_are_structured_code_text_detail_deduplicated():
    qa = {"pass": False, "fail_reasons": ["fabricated metric in bullet x3"], "warnings": ["long letter"],
          "deterministic": {"checks": [{"check": "keyword_coverage", "ok": False, "detail": "3 missing"},
                                       {"check": "pdf", "ok": True}, {"check": "tex", "ok": False, "skipped": True}]}}
    prep = {"qa_pass": False, "action_items": ["tier_a_review: review resume", "tier_a_review: review resume"],
            "flags": ["doctor failed"], "notes": "  "}
    opened = [{"type": "salary", "what": "Answer the salary question"},
              {"type": "other", "what": "careeros run: /prepare-job failed (see `careeros run show r1`)"}]
    got = review_reasons(qa, prep, opened)
    assert [(r["code"], r["detail"]) for r in got] == [
        ("qa_fail", "fabricated metric in bullet x3"), ("qa_keyword_coverage", "keyword_coverage: 3 missing"),
        ("qa_warning", "long letter"), ("prepare_action", "tier_a_review: review resume"),
        ("prepare_flag", "doctor failed"), ("action_salary", "Answer the salary question"),
        ("action_other", "careeros run: /prepare-job failed (see `careeros run show r1`)")]
    assert got[1]["text"] == "Resume misses key skills from this role"
    for r in got:  # human text: no CLI commands, backticks or snake_case internal ids
        assert r["text"] and "careeros" not in r["text"] and "`" not in r["text"], r
        assert not re.search(r"[a-z]_[a-z]", r["text"]), r
    assert review_reasons(None, None, []) == [] and review_reasons({"checks": "junk"}, {"flags": 3}, []) == []


STAGED = {"outcome": "staged", "status": "needs_review", "reason": "assisted: review & submit",
          "action_item": {"type": "review", "what": "Review the staged form and click submit"}}


def test_a_staged_apply_session_is_reviewed_by_hand_and_never_re_approved():
    # The default config path: auto_submit off -> apply-job stages the form, status needs_review, qa_pass true.
    st = compute_state("needs_review", SCORE_B, PREPARED, {"pass": True}, apply_session=STAGED)
    assert st["stage"] == "review" and st["next_action"] is None and st["next_kind"] is None
    assert st["blocked_reason"] == APPLY_STAGED
    got = {r["code"]: r for r in st["review_reasons"]}
    assert got["apply_staged"]["detail"] == "Apply session staged: assisted: review & submit"
    assert got["apply_action"]["detail"] == "Review the staged form and click submit"
    for outcome in ("submitted", "blocked"):
        st = compute_state("needs_review", SCORE_B, PREPARED, {"pass": True}, apply_session={**STAGED, "outcome": outcome})
        assert st["next_action"] is None and st["blocked_reason"], outcome


def test_a_failed_apply_session_allows_a_retry_with_the_reason_shown():
    failed = {"outcome": "failed", "status": "needs_review", "reason": "daily cap", "action_item": None}
    st = compute_state("needs_review", SCORE_B, PREPARED, {"pass": True}, apply_session=failed)
    assert act(st) == ("review", "approve_continue", "apply", False, None)
    assert {"code": "apply_failed", "text": "The application couldn't be filled in",
            "detail": "Apply session failed: daily cap"} in st["review_reasons"]


def test_a_submit_already_clicked_apply_session_stays_hands_off_even_when_outcome_is_failed():
    # submit_clicked=True means the browser click happened even if the recorded outcome is "failed":
    # re-preparing would risk a second submit, so this must stay blocked, not offer "continue prepare (force)".
    session = {"outcome": "failed", "status": "queued", "reason": "network drop", "action_item": None,
               "submit_clicked": True}
    st = compute_state("queued", SCORE_B, PREPARED, {"pass": True}, apply_session=session)
    assert st["next_action"] is None and st["stage"] != "qa"
    assert st["blocked_reason"] == "submit already clicked in an earlier session: check the ATS by hand"


def test_a_job_queued_in_a_batch_is_blocked_without_an_active_run():
    st = compute_state("scored", SCORE_B, None, None, queued_in_run="20260927-100000-prepare-ab12")
    assert st["next_action"] is None and st["active_run_id"] is None
    assert st["queued_in_run"] == "20260927-100000-prepare-ab12"
    assert st["blocked_reason"] == "Queued in batch run 20260927-100000-prepare-ab12"


def test_a_job_out_of_retries_is_blocked_with_the_failures_and_a_reset_hint():
    fails = {"kind": "apply", "count": 2, "max_attempts": 2, "last_outcome": "invalid_result",
             "last_detail": "bad", "last_run": "r2", "excluded": True}
    st = compute_state("queued", {"tier": "B"}, {"qa_pass": True}, None, failures=fails)
    assert st["failures"] == fails and st["next_kind"] == "apply"
    assert st["blocked_reason"] == "Failed 2 times (last: invalid_result): runs skip this job until you reset its failures"
    st = compute_state("queued", {"tier": "B"}, {"qa_pass": True}, None, failures={**fails, "count": 1, "excluded": False})
    assert st["blocked_reason"] is None and st["failures"]["count"] == 1
    assert compute_state("queued", {"tier": "B"}, {"qa_pass": True}, None)["failures"] is None
