"""Yield-model data (docs/YIELD_MODEL.md §6): per-application channel + outcome, Wilson intervals."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from careeros.models import CHANNELS

WINDOW_DAYS = 45
INTERVIEW = ("interview", "offer")  # screening = assessment/recruiter screen: reported apart


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials; (0, 1) when n == 0."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def outcome(history: list[dict[str, Any]], posted_at: str | None, channel: str, now: datetime) -> dict[str, Any] | None:
    """One application's yield record, None if never applied. Start = first applied/screening/interview/offer entry
    (sourced jobs may skip `applied`). interview = any interview/offer entry (even if rejected later); screening is
    flagged apart, not counted; rejected = rejected, no interview; open = no interview after 45 days;
    censored = no interview or rejection yet, started under 45 days ago."""
    applied = next((e for e in history if e.get("status") in ("applied", "screening", *INTERVIEW)), None)
    if not applied:
        return None
    a = _dt(applied.get("at"))
    iv = next((e for e in history if e.get("status") in INTERVIEW), None)
    screened = any(e.get("status") == "screening" for e in history)
    posted = _dt(posted_at)
    if iv:
        out = "interview"
    elif any(e.get("status") == "rejected" for e in history):
        out = "rejected"
    elif a and (now - a).days < WINDOW_DAYS:
        out = "censored"
    else:
        out = "open"
    return {
        "channel": channel,
        "applied_at": applied.get("at"),
        "posting_age_days_at_apply": (a - posted).days if a and posted else None,
        "first_interview_at": iv.get("at") if iv else None,
        "screening": screened,
        "outcome": out,
    }


def yield_rows(store: Any, now: datetime | None = None) -> list[dict[str, Any]]:
    """Per-channel counts. n = resolved applications (interview, rejected, open); censored are listed apart
    and left out of the rate."""
    now = now or datetime.now(timezone.utc)
    rows = {c: {"channel": c, "n": 0, "interviews": 0, "screenings": 0, "censored": 0} for c in CHANNELS}
    for jid in store.iter_job_ids():
        st = store._read(jid, "status.json") or {}
        p = store.load_posting(jid)
        o = outcome(st.get("history", []), p.posted_at if p else None, store.get_channel(jid)[0], now)
        if not o:
            continue
        r = rows[o["channel"]]
        r["screenings"] += o["screening"]
        if o["outcome"] == "censored":
            r["censored"] += 1
            continue
        r["n"] += 1
        r["interviews"] += o["outcome"] == "interview"
    for r in rows.values():
        r["rate"] = r["interviews"] / r["n"] if r["n"] else None
        r["ci95"] = wilson(r["interviews"], r["n"])
    return list(rows.values())
