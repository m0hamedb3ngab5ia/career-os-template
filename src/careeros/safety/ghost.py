"""Ghost-job detection: postings that are probably not a real, open hiring need.

Signals (thresholds in `targets.yaml: safety.ghost`):
- stale: posted `stale_flag_days`+ ago = soft, `stale_skip_days`+ = hard (skip)
- reposted: the same role (company + normalized title + location) under `repost_flag_count`+ different ATS
  ids within `repost_window_days` = soft
- unlinked: found on an aggregator and never resolved to the company's own board/careers page = soft
- hiring freeze within `layoff_window_days` = hard; layoffs in that window = soft (costs fit)
Dream-list companies are never hard-skipped: the flag stays, as soft, for the candidate to judge.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from careeros.config import Settings, normalize_company
from careeros.models import Posting
from careeros.safety.scam import AGGREGATORS, Flag

DEFAULTS: dict[str, int] = {
    "stale_flag_days": 30,
    "stale_skip_days": 45,
    "repost_window_days": 90,
    "repost_flag_count": 3,
    "layoff_window_days": 180,
}

_REQ_RE = re.compile(r"\b(r|req|jr|job)?[-# ]?\d{3,}\b|\(\s*\d{4}\s*\)|\b20\d\d\b", re.I)
_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")


def ghost_settings(settings: Settings) -> dict[str, int]:
    raw = ((settings.targets.get("safety") or {}).get("ghost") or {})
    return {k: int(raw.get(k, v)) for k, v in DEFAULTS.items()}


def history_key(company: str, title: str, location: str = "") -> str:
    """Same role across reposts: company | title without req ids / years / punctuation | location."""
    t = _REQ_RE.sub(" ", (title or "").lower())
    t = " ".join(_PUNCT_RE.sub(" ", t).split())
    loc = " ".join(_PUNCT_RE.sub(" ", (location or "").lower()).split())
    return f"{normalize_company(company)}|{t}|{loc}"


def _d(value: Any) -> date | None:
    if not value:
        return None
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None


def default_signals_path(settings: Settings) -> Path:
    return settings.paths.get("company_signals") or settings.paths["jobs_dir"].parent / "company_signals.json"


def load_signals(settings: Settings, path: Path | None = None) -> dict[str, dict[str, Any]]:
    """{normalized company: {kind: freeze|layoffs|none, date, source_url, checked_at}}. The data file is
    written by `careeros safety signal` (score-job's web check); `companies.yaml: hiring_signals` wins."""
    out: dict[str, dict[str, Any]] = {}
    p = Path(path) if path else default_signals_path(settings)
    if p.exists():
        try:
            for k, v in (json.loads(p.read_text(encoding="utf-8")) or {}).items():
                if isinstance(v, dict):
                    out[normalize_company(k)] = v
        except json.JSONDecodeError:
            pass
    for e in settings.companies.get("hiring_signals") or []:
        if isinstance(e, dict) and e.get("company"):
            out[normalize_company(str(e["company"]))] = {
                "kind": e.get("kind", "none"), "date": str(e.get("date") or ""),
                "source_url": e.get("source") or e.get("source_url") or "config"}
    return out


def save_signal(settings: Settings, company: str, kind: str, when: str, source: str,
                path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else default_signals_path(settings)
    data: dict[str, Any] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            data = {}
    entry = {"kind": kind, "date": when, "source_url": source, "checked_at": date.today().isoformat()}
    data[normalize_company(company)] = entry
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return entry


def check_ghost(p: Posting, hist: dict[str, Any] | None, signals: dict[str, dict[str, Any]], settings: Settings,
                today: date | None = None) -> list[Flag]:
    g = ghost_settings(settings)
    today = today or date.today()
    flags: list[Flag] = []

    # Age: the posting's own date; history dates only when this role was never reposted (a fresh repost
    # is its own posting, and the repost itself is flagged below).
    dates = [_d(p.posted_at)]
    if hist and len(hist.get("ats_job_ids") or []) <= 1:
        dates += [_d(hist.get("posted_at_min")), _d(hist.get("first_seen"))]
    known = [d for d in dates if d]
    if known:
        age = (today - min(known)).days
        if age >= g["stale_skip_days"]:
            flags.append(Flag("ghost_stale", "hard", f"posted {age} days ago (skip at {g['stale_skip_days']})"))
        elif age >= g["stale_flag_days"]:
            flags.append(Flag("ghost_stale", "soft", f"posted {age} days ago"))

    if hist:
        start = today - timedelta(days=g["repost_window_days"])
        recent = [d for d in (_d(x) for x in hist.get("sightings") or []) if d and d >= start]
        if len(recent) >= g["repost_flag_count"]:
            flags.append(Flag("ghost_reposted", "soft",
                              f"same role posted {len(recent)} times in {g['repost_window_days']} days"))

    source = str(p.raw.get("source") or "").lower()
    if source in AGGREGATORS and not p.raw.get("resolved_from"):
        flags.append(Flag("ghost_unlinked", "soft",
                          f"found on {source}; not yet found on {p.company}'s own careers page or ATS board"))

    sig = signals.get(normalize_company(p.company))
    when = _d(sig.get("date")) if sig else None
    if sig and when and (today - when).days <= g["layoff_window_days"]:
        src = sig.get("source_url") or "?"
        if sig.get("kind") == "freeze":
            flags.append(Flag("ghost_freeze", "hard", f"hiring freeze reported {when} ({src})"))
        elif sig.get("kind") == "layoffs":
            flags.append(Flag("ghost_layoffs", "soft", f"layoffs reported {when} ({src})"))

    if settings.is_dream(p.company):
        flags = [Flag(f.code, "soft", f"{f.detail} (dream company: your call)") if f.severity == "hard" else f
                 for f in flags]
    return flags
