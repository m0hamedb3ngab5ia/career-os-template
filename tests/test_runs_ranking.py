from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from careeros.runs.config import DEFAULT_RANKING
from careeros.runs.ranking import Candidate, fit_first_within_company, rank

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def cand(jid, hours_old=10.0, company="Acme", dream=False, closes=None, fit=None, **kw):
    return Candidate(job_id=jid, company=company, title=f"Engineer {jid}", status="found",
                     posted_at=NOW - timedelta(hours=hours_old), closes_at=closes, dream=dream, fit=fit, **kw)


def test_fresh_posting_beats_old_one():
    out = rank([cand("old", hours_old=24 * 20), cand("new", hours_old=5)], DEFAULT_RANKING, NOW, stage="score")
    assert [r["job_id"] for r in out] == ["new", "old"]
    assert "posted 5h ago" in out[0]["why"]


def test_everything_under_48h_gets_full_freshness_weight():
    w = DEFAULT_RANKING
    a, b = rank([cand("a", hours_old=1), cand("b", hours_old=47)], w, NOW, stage="score")
    assert a["score"] == b["score"] == w["freshness_weight"]


def test_freshness_decays_to_zero_at_stale_days():
    w = {**DEFAULT_RANKING, "stale_days": 10}
    (r,) = rank([cand("x", hours_old=24 * 11)], w, NOW, stage="score")
    assert r["score"] == 0


def test_dream_bonus_and_deadline_bonus_are_explained():
    out = rank([cand("plain", hours_old=5),
                cand("dream", hours_old=24 * 40, dream=True, closes=date(2026, 9, 29))],
               DEFAULT_RANKING, NOW, stage="score")
    d = next(r for r in out if r["job_id"] == "dream")
    assert "dream company" in d["why"] and "closes 2026-09-29" in d["why"]
    assert d["score"] == DEFAULT_RANKING["dream_bonus"] + DEFAULT_RANKING["deadline_bonus"]


def test_past_deadline_gets_no_bonus():
    (r,) = rank([cand("x", hours_old=24 * 40, closes=date(2026, 9, 1))], DEFAULT_RANKING, NOW, stage="score")
    assert r["score"] == 0


def test_fit_counts_only_in_prepare_stage():
    w = {**DEFAULT_RANKING, "fit_weight": 1.0}
    s = rank([cand("x", fit=80)], w, NOW, stage="score")[0]["score"]
    p = rank([cand("x", fit=80)], w, NOW, stage="prepare")[0]["score"]
    assert p - s == 80


def test_weights_come_from_config():
    w = {**DEFAULT_RANKING, "freshness_weight": 0, "dream_bonus": 100}
    out = rank([cand("fresh", hours_old=1), cand("dream", hours_old=24 * 40, dream=True)], w, NOW, stage="score")
    assert out[0]["job_id"] == "dream"


def test_ties_break_by_job_id_for_stable_order():
    out = rank([cand("b"), cand("a")], DEFAULT_RANKING, NOW, stage="score")
    assert [r["job_id"] for r in out] == ["a", "b"]


def test_retry_bonus_moves_a_failed_job_up():
    w = {**DEFAULT_RANKING, "retry_bonus": 1000}
    out = rank([cand("fresh", hours_old=1), cand("retry", hours_old=24 * 40, retry=True)], w, NOW, stage="score")
    assert out[0]["job_id"] == "retry" and "retry" in out[0]["why"]


def test_fit_first_within_company_keeps_company_positions():
    ranked = [{"job_id": "a1", "company": "Acme", "fit": 60}, {"job_id": "b1", "company": "Beta", "fit": 90},
              {"job_id": "a2", "company": "Acme", "fit": 85}]
    out = fit_first_within_company(ranked)
    assert [r["job_id"] for r in out] == ["a2", "b1", "a1"]
    assert "fit-first within Acme" in out[0]["why"]


def test_fit_first_is_a_no_op_without_fit():
    ranked = [{"job_id": "a1", "company": "Acme", "fit": None}, {"job_id": "a2", "company": "Acme", "fit": None}]
    assert fit_first_within_company(ranked) == ranked
