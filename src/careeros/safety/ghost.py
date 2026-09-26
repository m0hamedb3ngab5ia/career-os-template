"""Ghost-job detection: signs a posting may not be a real, open hiring need. Levels (see scam.verdict):

- GHOST_OLD_POST: `old_post_days`+ = info (lower confidence). `very_old_post_days`+ = review.
- GHOST_STALE_NO_ACTIVITY (skip): very old AND not updated within `recent_update_days` AND no sign the
  company is still hiring (no other role published recently) AND not an evergreen / senior role.
- GHOST_REPOSTED (review): the same role under `repost_flag_count`+ different requisition ids within
  `repost_window_days`. Edits to one requisition are not reposts (history counts them separately).
- GHOST_AGGREGATOR_ONLY (review): found on an aggregator, not yet on the company's own site or ATS board.
- GHOST_HIRING_FREEZE: a freeze reported within `freeze_window_days` = review when its scope covers this
  role (company-wide, or a scope word in the title/department/location), else info.
- GHOST_RECENT_LAYOFFS (info): layoffs lower confidence; they do not make a role fake.
Company priority: a dream-list company is never skipped (skip -> review). Thresholds: targets.yaml
`safety.ghost`; any code's level can be overridden in `safety.levels`.
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
    "old_post_days": 30,
    "very_old_post_days": 45,
    "recent_update_days": 30,
    "repost_window_days": 90,
    "repost_flag_count": 3,
    "freeze_window_days": 180,
    "layoff_window_days": 180,
}

_REQ_RE = re.compile(r"\b(r|req|jr|job)?[-# ]?\d{3,}\b|\(\s*\d{4}\s*\)|\b20\d\d\b", re.I)
_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
EVERGREEN_RE = re.compile(
    r"\b(evergreen|rolling basis|talent (community|pool|network)|general application|always hiring|"
    r"future opportunit|pipeline (role|req))", re.I)
SENIOR_RE = re.compile(r"\b(senior|sr\.?|staff|principal|lead|director|manager|head of|architect|vp)\b", re.I)


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
    """{normalized company: {kind: freeze|layoffs|none, date, scope, source_url, checked_at}}. The data file
    is written by `careeros safety signal` (score-job's web check); `companies.yaml: hiring_signals` wins."""
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
                "kind": e.get("kind", "none"), "date": str(e.get("date") or ""), "scope": e.get("scope") or "",
                "source_url": e.get("source") or e.get("source_url") or "config"}
    return out


def save_signal(settings: Settings, company: str, kind: str, when: str, source: str, scope: str = "",
                path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else default_signals_path(settings)
    data: dict[str, Any] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            data = {}
    entry = {"kind": kind, "date": when, "scope": scope, "source_url": source, "checked_at": date.today().isoformat()}
    data[normalize_company(company)] = entry
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return entry


def _scope_covers(scope: str, p: Posting) -> bool:
    words = [w.strip().lower() for w in re.split(r"[;,]", scope or "") if w.strip()]
    if not words or any(w in ("company-wide", "company wide", "all", "global") for w in words):
        return True
    hay = " ".join([p.title or "", " ".join(p.departments or []), p.location or ""]).lower()
    return any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", hay) for w in words)


def _still_hiring(p: Posting, company_history: dict[str, dict[str, Any]], since: date) -> bool:
    """Another role at the same company was published (or first seen) since `since`."""
    prefix = normalize_company(p.company) + "|"
    own = history_key(p.company, p.title, p.location)
    for key, e in company_history.items():
        if key.startswith(prefix) and key != own:
            d = _d(e.get("first_published")) or _d((e.get("sightings") or [None])[-1])
            if d and d >= since:
                return True
    return False


def check_ghost(p: Posting, hist: dict[str, Any] | None, signals: dict[str, dict[str, Any]], settings: Settings,
                today: date | None = None, company_history: dict[str, dict[str, Any]] | None = None) -> list[Flag]:
    """`hist` = this role's posting_history entry; `company_history` = the whole history (None = unknown,
    which never allows a skip)."""
    g = ghost_settings(settings)
    today = today or date.today()
    ev = tuple(u for u in (p.url,) if u)
    flags: list[Flag] = []

    # Age: the posting's own dates; history dates only when this role was never reposted (a fresh repost
    # is its own posting; the repost itself is flagged below).
    dates = [_d(p.posted_at), _d(p.first_published)]
    if hist and len(hist.get("ats_job_ids") or []) <= 1:
        dates += [_d(hist.get("first_published")), _d(hist.get("first_seen"))]
    known = [d for d in dates if d]
    if known:
        age = (today - min(known)).days
        if age >= g["very_old_post_days"]:
            since = today - timedelta(days=g["recent_update_days"])
            updated = [d for d in (_d(p.last_updated), _d((hist or {}).get("last_updated"))) if d]
            recently_updated = any(d >= since for d in updated)
            evergreen = bool(EVERGREEN_RE.search(f"{p.title} {p.description_text}"))
            senior = bool(SENIOR_RE.search(p.title or ""))
            hiring = company_history is None or _still_hiring(p, company_history, since)
            why = [w for w, on in (("updated recently", recently_updated), ("company still posting roles", hiring),
                                   ("evergreen role", evergreen), ("senior role (stays open longer)", senior)) if on]
            if why:
                flags.append(Flag("GHOST_OLD_POST", "review", f"posted {age} days ago; but {', '.join(why)}", ev))
            else:
                flags.append(Flag("GHOST_STALE_NO_ACTIVITY", "skip",
                                  f"posted {age} days ago, not updated in {g['recent_update_days']} days, "
                                  "no other recent roles at the company", ev))
        elif age >= g["old_post_days"]:
            flags.append(Flag("GHOST_OLD_POST", "info", f"posted {age} days ago", ev))

    if hist:
        start = today - timedelta(days=g["repost_window_days"])
        recent = [d for d in (_d(x) for x in hist.get("sightings") or []) if d and d >= start]
        if len(recent) >= g["repost_flag_count"]:
            flags.append(Flag("GHOST_REPOSTED", "review",
                              f"same role posted as {len(recent)} separate requisitions in {g['repost_window_days']} "
                              "days (could be recurring headcount)", ev))

    source = str(p.raw.get("source") or "").lower()
    if source in AGGREGATORS and not p.raw.get("resolved_from"):
        flags.append(Flag("GHOST_AGGREGATOR_ONLY", "review",
                          f"found on {source}; not yet found on {p.company}'s own careers page or ATS board", ev))

    sig = signals.get(normalize_company(p.company))
    when = _d(sig.get("date")) if sig else None
    if sig and when:
        src = tuple(u for u in (sig.get("source_url"),) if u)
        if sig.get("kind") == "freeze" and (today - when).days <= g["freeze_window_days"]:
            covers = _scope_covers(str(sig.get("scope") or ""), p)
            flags.append(Flag("GHOST_HIRING_FREEZE", "review" if covers else "info",
                              f"hiring freeze reported {when} (scope: {sig.get('scope') or 'unspecified'})"
                              + ("" if covers else "; does not cover this role"), src))
        elif sig.get("kind") == "layoffs" and (today - when).days <= g["layoff_window_days"]:
            flags.append(Flag("GHOST_RECENT_LAYOFFS", "info", f"layoffs reported {when}", src))

    if settings.is_dream(p.company):
        flags = [Flag(f.code, "review", f"{f.detail} (dream company: your call)", f.evidence, f.at)
                 if f.level == "skip" else f for f in flags]
    return flags
