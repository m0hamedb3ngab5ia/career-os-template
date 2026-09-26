"""GET /api/contacts and POST /api/contacts/{job_id}/{name}/mark: the Contacts screen.

Rows come from the index (per-job contacts.json, written by find-contacts), joined with the job and with the
draft-outreach skill's outreach.json for that job. The relationship gate is careeros.outreach's own
(`needs_manual_outreach`, same switches as `careeros outreach check`), and the mark write is the same function as
`careeros outreach mark` (`mark_contact`). Nothing here sends or opens LinkedIn.
"""
from __future__ import annotations

from typing import Any

from careeros.outreach import OutreachPolicy, _detail, mark_contact, needs_manual_outreach
from careeros.ui.services.inbox import job_drafts
from careeros.ui.services.jobs import job_dir_for

_FIELDS = ("c.job_id, c.seq, c.name, c.title, c.company, c.linkedin, c.email, c.email_confidence, c.linkedin_degree, "
           "c.mutuals, c.sent, c.replied, j.title AS job_title, j.status AS job_status, j.company AS job_company")


def _mode(contact: dict[str, Any], manual: bool, draft: dict[str, Any] | None) -> str:
    """replied | sent | manual (connected / mutuals: you tailor it) | email_draft (to a verified address) |
    linkedin_draft (you send it on LinkedIn) | no_draft."""
    if contact.get("replied"):
        return "replied"
    if contact.get("sent") or (draft and draft["sent"]):
        return "sent"
    if manual:
        return "manual"
    if draft is None:
        return "no_draft"
    return "email_draft" if draft["mode"] == "verified_email" else "linkedin_draft"


def list_contacts(settings: Any, ix: Any) -> dict[str, Any]:
    from pathlib import Path

    policy = OutreachPolicy.from_settings(settings)
    rows = ix.query(f"SELECT {_FIELDS} FROM contacts c LEFT JOIN jobs j ON j.job_id = c.job_id "
                    "ORDER BY j.company, c.job_id, c.seq")
    drafts: dict[str, dict[str, dict[str, Any]]] = {}
    items = []
    for r in rows:
        jid = r["job_id"]
        if jid not in drafts:
            by: dict[str, dict[str, Any]] = {}
            for d in job_drafts(Path(settings.paths["jobs_dir"]) / jid):
                key = d["contact"].strip().lower()
                if key and key not in by and d["kind"] != "post_interview_thanks":
                    by[key] = d
            drafts[jid] = by
        manual, reason = needs_manual_outreach({"linkedin_degree": r["linkedin_degree"], "mutuals": r["mutuals"]},
                                               policy)
        draft = drafts[jid].get(str(r["name"] or "").strip().lower())
        items.append({
            "job_id": jid, "company": r["company"] or r["job_company"], "job_title": r["job_title"],
            "job_status": r["job_status"], "name": r["name"] or "", "title": r["title"] or "",
            "linkedin": r["linkedin"], "email": r["email"], "email_confidence": r["email_confidence"],
            "linkedin_degree": r["linkedin_degree"], "mutuals": r["mutuals"], "sent": bool(r["sent"]),
            "replied": r["replied"] or None, "manual": manual, "manual_reason": reason,
            "manual_detail": _detail(reason, r["mutuals"]) or None, "draft": draft,
            "mode": _mode(r, manual, draft),
        })
    return {"items": items, "linkedin_drafts": sum(1 for c in items if c["mode"] == "linkedin_draft"),
            "policy": {"manual_if_connected": policy.manual_if_connected,
                       "manual_if_mutuals": policy.manual_if_mutuals}}


def mark(settings: Any, job_id: str, name: str, degree: int | None = None,
         mutuals: int | None = None) -> dict[str, Any]:
    """`careeros outreach mark <job_id> <name> [--degree N] [--mutuals N]`. LookupError: no such job, contacts.json
    or contact; ValueError: nothing to record or a value out of range."""
    if degree is None and mutuals is None:
        raise ValueError("give degree and/or mutuals")
    d = job_dir_for(settings, job_id)
    if d is None:
        raise LookupError(f"no job {job_id!r}")
    f = d / "contacts.json"
    if not f.is_file():
        raise LookupError(f"no contacts.json for job {job_id}; run /find-contacts first")
    try:
        c = mark_contact(f, name, degree=degree, mutuals=mutuals)
    except KeyError:
        raise LookupError(f"no contact named {name!r} for job {job_id}") from None
    return {"job_id": job_id, "name": c.get("name"), "linkedin_degree": c.get("linkedin_degree"),
            "mutuals": c.get("mutuals")}
