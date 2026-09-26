"""Which jobs a run takes first, and why. Pure: candidates in, ranked dicts out, `now` passed in. No LLM.

score = freshness_weight * freshness            (1.0 under fresh_hours, then linear down to 0 at stale_days)
      + dream_bonus        if the company is on the dream list
      + deadline_bonus     if the posting closes within deadline_days (and has not closed)
      + fit_weight * fit   prepare runs only (score runs have no fit yet)
      + retry_bonus        a job whose last attempt failed (retried once, then an Action Item)

Ties break by job id, so the same inputs always give the same order. Every item carries `why`, a short
human reason ("posted 20h ago (+60); dream company (+25)") that `careeros run status` and the UI show.
Within one company, prepare runs then keep the company gate's fit-first order (`fit_first_within_company`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass
class Candidate:
    job_id: str
    company: str
    title: str
    status: str
    posted_at: datetime | None
    closes_at: date | None = None
    dream: bool = False
    fit: int | None = None
    retry: bool = False


def _age(hours: float) -> str:
    return f"{hours:.0f}h" if hours < 48 else f"{hours / 24:.0f}d"


def _fmt(points: float) -> str:
    return f"+{points:g}"


def score_candidate(c: Candidate, w: dict[str, float], now: datetime, stage: str) -> tuple[float, list[str]]:
    total, why = 0.0, []
    if c.posted_at is not None:
        hours = max(0.0, (now - c.posted_at).total_seconds() / 3600)
        full, zero = float(w["fresh_hours"]), float(w["stale_days"]) * 24
        if hours <= full:
            f = 1.0
        elif hours >= zero or zero <= full:
            f = 0.0
        else:
            f = 1 - (hours - full) / (zero - full)
        pts = round(w["freshness_weight"] * f, 2)
        total += pts
        why.append(f"posted {_age(hours)} ago ({_fmt(pts)})")
    else:
        why.append("posting date unknown (+0)")
    if c.dream and w["dream_bonus"]:
        total += w["dream_bonus"]
        why.append(f"dream company ({_fmt(w['dream_bonus'])})")
    if c.closes_at is not None and w["deadline_bonus"]:
        days = (c.closes_at - now.date()).days
        if 0 <= days <= w["deadline_days"]:
            total += w["deadline_bonus"]
            why.append(f"closes {c.closes_at.isoformat()} ({_fmt(w['deadline_bonus'])})")
    if stage == "prepare" and c.fit is not None and w["fit_weight"]:
        pts = round(c.fit * w["fit_weight"], 2)
        total += pts
        why.append(f"fit {c.fit} ({_fmt(pts)})")
    if c.retry and w.get("retry_bonus"):
        total += w["retry_bonus"]
        why.append(f"retry after a failed attempt ({_fmt(w['retry_bonus'])})")
    return round(total, 2), why


def rank(cands: list[Candidate], weights: dict[str, float], now: datetime, stage: str) -> list[dict[str, Any]]:
    out = []
    for c in cands:
        s, why = score_candidate(c, weights, now, stage)
        out.append({"job_id": c.job_id, "company": c.company, "title": c.title, "status": c.status, "fit": c.fit,
                    "score": s, "why": "; ".join(why)})
    out.sort(key=lambda r: (-r["score"], r["job_id"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def fit_first_within_company(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep each company's positions in the global order, but fill them with that company's jobs by fit
    (highest first), the same order the company gate hands out slots in. No-op when no job has a fit."""
    if not any(r.get("fit") is not None for r in ranked):
        return ranked
    by_co: dict[str, list[dict[str, Any]]] = {}
    for r in ranked:
        by_co.setdefault(r["company"], []).append(r)
    for rows in by_co.values():
        rows.sort(key=lambda r: (-(r.get("fit") or 0), r["rank"] if "rank" in r else 0, r["job_id"]))
    taken = {co: iter(rows) for co, rows in by_co.items()}
    out = []
    for r in ranked:
        nxt = dict(next(taken[r["company"]]))
        if nxt["job_id"] != r["job_id"]:
            nxt["why"] = (nxt.get("why", "") + f"; fit-first within {r['company']}").lstrip("; ")
        out.append(nxt)
    for i, r in enumerate(out, 1):
        if "rank" in r:
            r["rank"] = i
    return out
