"""Flagged companies/domains (`data/flagged_registry.yaml`) and verified companies
(`data/verified_companies.yaml`).

A flag is not forever: each entry carries a reason (reason codes), a confidence (`high` blocks, `medium`
asks for review), evidence URLs, an expiry (`expires_at`, default 180 days) and a review state
(`active` | `cleared`). Only active, unexpired, high-confidence entries make scout drop postings.

entries:
  - company: Quick Hire Co
    domain: quick-hire-now.xyz
    reason: "SCAM_PAYMENT_REQUEST; SCAM_FREE_EMAIL_RECRUITER"
    confidence: high
    state: active
    evidence: [https://quick-hire-now.xyz/job]
    first_seen: 2026-09-25T14:03:00+00:00
    last_seen: 2026-09-25T14:03:00+00:00
    expires_at: 2027-03-24T14:03:00+00:00
    count: 1
    job_ids: [a1b2c3d4e5f6]
    review_note: ""
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from careeros.config import Settings, _fuzzy_eq, normalize_company
from careeros.models import now_iso

DEFAULT_EXPIRY_DAYS = 180
HEADER = ("# Flagged companies/domains (scam gate). high = blocked (scout drops them), medium = review.\n"
          "# Written by `careeros safety check|flag`; `careeros safety clear <company>` after review. Entries expire.\n")
VERIFIED_HEADER = "# Companies checked with `careeros safety verify` (risk low | medium | high + signals + evidence).\n"


def default_path(settings: Settings) -> Path:
    return settings.paths.get("flagged_registry") or settings.paths["jobs_dir"].parent / "flagged_registry.yaml"


def verified_path(settings: Settings) -> Path:
    return settings.paths.get("verified_companies") or settings.paths["jobs_dir"].parent / "verified_companies.yaml"


def load(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [e for e in data.get("entries") or [] if isinstance(e, dict)]


def _save(path: Path, entries: list[dict[str, Any]], header: str = HEADER) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(header + yaml.safe_dump({"entries": entries}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)


def _shared(domain: str) -> bool:
    from careeros.safety.scam import AGGREGATOR_DOMAINS, KNOWN_ATS_DOMAINS

    return domain in KNOWN_ATS_DOMAINS or domain in AGGREGATOR_DOMAINS


def is_active(e: dict[str, Any], now: datetime | None = None) -> bool:
    if str(e.get("state") or "active") != "active":
        return False
    exp = e.get("expires_at")
    if exp:
        try:
            when = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return when > (now or datetime.now(timezone.utc))
        except ValueError:
            return True
    return True


def _find(entries: list[dict[str, Any]], company: str, domain_or_url: str = "") -> dict[str, Any] | None:
    from careeros.safety.scam import registrable_domain

    key = normalize_company(company or "")
    dom = registrable_domain(domain_or_url) if domain_or_url else ""
    for e in entries:
        ek = normalize_company(str(e.get("company") or ""))
        if key and ek and _fuzzy_eq(key, ek):
            return e
        ed = registrable_domain(str(e.get("domain") or ""))
        if dom and ed and dom == ed and not _shared(ed):
            return e
    return None


def is_flagged(entries: list[dict[str, Any]], company: str, domain_or_url: str = "") -> dict[str, Any] | None:
    """The matching active, unexpired entry (company fuzzy match, or same registrable domain), else None."""
    return _find([e for e in entries if is_active(e)], company, domain_or_url)


def add_or_bump(path: Path, company: str, domain: str = "", reason: str = "", job_id: str = "",
                notes: str = "", confidence: str = "high", evidence: list[str] | None = None,
                days: int = DEFAULT_EXPIRY_DAYS) -> dict[str, Any]:
    from careeros.safety.scam import registrable_domain

    entries = load(path)
    now = now_iso()
    if domain and _shared(registrable_domain(domain)):
        domain = ""  # never flag greenhouse.io etc.: that would drop every company on that ATS
    e = _find(entries, company, domain)
    if e is None:
        e = {"company": company, "domain": registrable_domain(domain) if domain else "", "reason": "",
             "confidence": confidence, "state": "active", "evidence": [], "first_seen": now, "last_seen": now,
             "expires_at": "", "count": 0, "job_ids": [], "review_note": notes}
        entries.append(e)
    reasons = [r for r in str(e.get("reason") or "").split("; ") if r]
    for r in reason.split("; "):
        if r and r not in reasons:
            reasons.append(r)
    e["reason"] = "; ".join(reasons)
    if domain and not e.get("domain"):
        e["domain"] = registrable_domain(domain)
    if e.get("confidence") != "high":
        e["confidence"] = confidence            # medium -> high on new evidence, never high -> medium
    for u in evidence or []:
        if u and u not in e.setdefault("evidence", []):
            e["evidence"].append(u)
    e["state"] = "active"
    e["last_seen"] = now
    e["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()
    e["count"] = int(e.get("count") or 0) + 1
    if job_id and job_id not in e.setdefault("job_ids", []):
        e["job_ids"].append(job_id)
    _save(path, entries)
    return e


def clear(path: Path, company: str, note: str = "") -> dict[str, Any] | None:
    """Mark an entry reviewed and cleared (kept for history; no longer matches)."""
    entries = load(path)
    e = _find(entries, company)
    if e is None:
        return None
    e["state"] = "cleared"
    e["review_note"] = f"{now_iso()[:10]}: {note}" if note else now_iso()[:10]
    _save(path, entries)
    return e


# --- verified companies (made-up company protection) ------------------------------------------------

RISKS = ("low", "medium", "high")


def add_verified(path: Path, company: str, risk: str, domain: str = "", signals: list[str] | None = None,
                 evidence: list[str] | None = None) -> dict[str, Any]:
    """Record a company check from several independent signals (official site, careers page or ATS listing,
    LinkedIn with identifiable people, consistent domains, external references). `low` needs at least two
    signals in total. Signals accumulate across calls; the latest risk wins."""
    from careeros.safety.scam import registrable_domain

    if risk not in RISKS:
        raise ValueError(f"risk must be one of {RISKS}")
    entries = load(path)
    key = normalize_company(company)
    e = next((x for x in entries if normalize_company(str(x.get("company") or "")) == key), None)
    have = list((e or {}).get("signals") or [])
    new_signals = [s for s in signals or [] if s and s not in have]
    if risk == "low" and len(have) + len(new_signals) < 2:
        raise ValueError("risk low needs at least two independent signals (--signal ... --signal ...)")
    if e is None:
        e = {"company": company, "domain": "", "risk": risk, "signals": [], "evidence": [], "checked_at": ""}
        entries.append(e)
    e["risk"] = risk
    if domain:
        e["domain"] = registrable_domain(domain)
    e["signals"] = have + new_signals
    for u in evidence or []:
        if u and u not in e.setdefault("evidence", []):
            e["evidence"].append(u)
    e["checked_at"] = now_iso()
    _save(path, entries, VERIFIED_HEADER)
    return e
