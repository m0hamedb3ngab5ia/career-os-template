"""Flagged companies and domains (`data/flagged_registry.yaml`), same shape as apply/detection.yaml.

Written by `careeros safety check` on a hard flag and by `careeros safety flag`. Scout drops postings from
a listed company or domain; `check_posting` hard-flags them. Remove an entry by hand to clear it.

entries:
  - company: Quick Hire Co
    domain: quick-hire-now.xyz
    reason: "apply_domain; free_email_contact"
    first_seen: 2026-09-25T14:03:00+00:00
    last_seen: 2026-09-25T14:03:00+00:00
    count: 1
    job_ids: [a1b2c3d4e5f6]
    notes: ""
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from careeros.config import Settings, _fuzzy_eq, normalize_company
from careeros.models import now_iso

HEADER = ("# Flagged companies/domains (scam gate). Scout drops their postings; apply never fills their forms.\n"
          "# Written by `careeros safety check` / `careeros safety flag`. Delete an entry to clear it.\n")


def default_path(settings: Settings) -> Path:
    return settings.paths.get("flagged_registry") or settings.paths["jobs_dir"].parent / "flagged_registry.yaml"


def load(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [e for e in data.get("entries") or [] if isinstance(e, dict)]


def _save(path: Path, entries: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(HEADER + yaml.safe_dump({"entries": entries}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)


def _shared(domain: str) -> bool:
    from careeros.safety.scam import AGGREGATOR_DOMAINS, KNOWN_ATS_DOMAINS

    return domain in KNOWN_ATS_DOMAINS or domain in AGGREGATOR_DOMAINS


def is_flagged(entries: list[dict[str, Any]], company: str, domain_or_url: str = "") -> dict[str, Any] | None:
    """The matching entry (company fuzzy match, or registrable domain equal), else None."""
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


def add_or_bump(path: Path, company: str, domain: str = "", reason: str = "", job_id: str = "",
                notes: str = "") -> dict[str, Any]:
    from careeros.safety.scam import registrable_domain

    entries = load(path)
    now = now_iso()
    if domain and _shared(registrable_domain(domain)):
        domain = ""  # never flag greenhouse.io etc.: that would drop every company on that ATS
    e = is_flagged(entries, company, domain)
    if e is None:
        e = {"company": company, "domain": registrable_domain(domain) if domain else "", "reason": reason,
             "first_seen": now, "last_seen": now, "count": 0, "job_ids": [], "notes": notes}
        entries.append(e)
    else:
        reasons = [r for r in str(e.get("reason") or "").split("; ") if r]
        for r in reason.split("; "):
            if r and r not in reasons:
                reasons.append(r)
        e["reason"] = "; ".join(reasons)
        if domain and not e.get("domain"):
            e["domain"] = registrable_domain(domain)
    e["last_seen"] = now
    e["count"] = int(e.get("count") or 0) + 1
    if job_id and job_id not in (e.setdefault("job_ids", [])):
        e["job_ids"].append(job_id)
    _save(path, entries)
    return e


# --- verified companies (made-up company protection) ------------------------------------------------

def verified_path(settings: Settings) -> Path:
    return settings.paths.get("verified_companies") or settings.paths["jobs_dir"].parent / "verified_companies.yaml"


def add_verified(path: Path, company: str, domain: str = "", evidence: str = "") -> dict[str, Any]:
    """Record that a company outside the curated lists was checked by hand or by /score-job (official site
    resolves and lists the role, real LinkedIn page, not brand new). Its postings then lose
    `company_unverified`."""
    from careeros.safety.scam import registrable_domain

    entries = load(path)
    key = normalize_company(company)
    e = next((x for x in entries if normalize_company(str(x.get("company") or "")) == key), None)
    now = now_iso()
    if e is None:
        e = {"company": company, "domain": "", "evidence": "", "verified_at": now}
        entries.append(e)
    if domain:
        e["domain"] = registrable_domain(domain)
    if evidence:
        parts = [x for x in str(e.get("evidence") or "").split("; ") if x]
        if evidence not in parts:
            parts.append(evidence)
        e["evidence"] = "; ".join(parts)
    e["verified_at"] = now
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Companies verified as real (careeros safety verify). Delete an entry to re-check it.\n"
                    + yaml.safe_dump({"entries": entries}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return e
