"""Follow-up nudges (yield model step 4). One open `follow_up` Action Item per applied job with no reply after
`follow_ups.after_days` (pipeline.yaml, default 7), and one per job whose sent outreach has had no answer for as
long. Deduped by job + kind (a marker in Detail). Closed when the job's status moves past `applied` or the contact
replied. Runs in `careeros tick`; suggest-only, nothing is sent."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

from careeros.config import Settings
from careeros.store import Store
from careeros.tracker import Tracker

TYPE = "follow_up"
APPLIED, OUTREACH, OUTREACH14 = "follow_up:applied", "follow_up:outreach", "follow_up:outreach14"


def after_days(s: Settings) -> int:
    try:
        return max(1, int((s.pipeline.get("follow_ups") or {}).get("after_days", 7)))
    except (TypeError, ValueError):
        return 7


def _day(v: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(v)[:10]).date() if v else None
    except ValueError:
        return None


def _json(path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d if isinstance(d, dict) else {}


def _outreach_wait(store: Store, job_id: str) -> tuple[str, date, int] | None:
    """Next outreach nudge for this job as (marker, send date, days after the send), else None. A sent, unanswered
    message wants the 7d nudge until `followup_7d_sent_at` is set, then (if a 14d text exists) the 14d one."""
    d = store.job_dir(job_id)
    drafts = [x for x in _json(d / "outreach.json").get("drafts") or [] if isinstance(x, dict) and x.get("sent") is True]
    contacts = [c for c in _json(d / "contacts.json").get("contacts") or [] if isinstance(c, dict)]
    if not drafts or any(x.get("replied") for x in drafts) or any(c.get("replied") for c in contacts):
        return None
    first = [x for x in drafts if not x.get("followup_7d_sent_at")]
    late = [x for x in drafts if x.get("followup_7d_sent_at") and x.get("followup_14d") and not x.get("followup_14d_sent_at")]
    stage, pool, days = (OUTREACH, first, 0) if first else (OUTREACH14, late, 14)
    when = [_day(x.get("sent_at") or x.get("sent_date")) for x in pool]
    since = min((x for x in when if x), default=None)
    return (stage, since, days) if since else None


def contact_rows(store: Store, s: Settings) -> list[dict[str, Any]]:
    """Contacts-sheet rows from every outreach.json (user 2026-11-19): who was reached, did the email land, when to
    follow up. Rows are keyed by sheet headers; `Tracker.sync_contacts` writes them."""
    n, out = after_days(s), []
    for f in sorted(store.jobs_dir.glob("*/outreach.json")):
        company = _json(f.parent / "posting.json").get("company") or ""
        for d in _json(f).get("drafts") or []:
            if not isinstance(d, dict) or not d.get("contact"):
                continue
            bounces, sent, reason = len(d.get("bounced") or []), d.get("sent") is True, str(d.get("hold_reason") or "")
            when = _day(d.get("sent_at") or d.get("sent_date"))
            due = when + timedelta(days=n) if sent and when and not d.get("followup_7d_sent_at") else None
            if sent and d.get("followup_7d_sent_at"):  # next one: 14d after the send, only if its text exists
                due = when + timedelta(days=14) if when and d.get("followup_14d") and not d.get("followup_14d_sent_at") else None
            if sent:
                who = "replied" if d.get("replied") else "contacted"
                mail = "delivered" + (f" after {bounces} bounce{'s' * (bounces > 1)}" if bounces else "")
                fu = d.get("followup_14d_sent_at") or d.get("followup_7d_sent_at")
                if fu:
                    mail += f"; followed up {str(fu)[:10]}"
            elif d.get("hold"):
                who, mail = ("left company" if "left" in reason or "inactive" in reason else "not contacted"), f"held: {reason}"
            elif bounces:
                who, mail = "not reached", f"bounced; next try {d.get('to')}"
            else:
                who, mail = "not contacted", "draft"
            if not d.get("to") and not d.get("hold"):  # LinkedIn-only draft: no email to deliver or bounce
                mail = "LinkedIn, no email"
            out.append({"JobID": f.parent.name, "Company": company, "Name": d["contact"],
                        "Email": d.get("to") or "", "EmailConfidence": d.get("to_confidence") or "",
                        "Sent": "Y" if sent else "N", "SentDate": when.isoformat() if sent and when else "",
                        "ContactStatus": who, "EmailStatus": mail,
                        "FollowUpDue": due.isoformat() if due and who != "replied" else ""})
    return out


def raise_follow_ups(s: Settings, today: date | None = None) -> list[str]:
    today, n = today or date.today(), after_days(s)
    tr, store = Tracker(settings=s), Store(s)
    jobs = {str(j["JobID"]): j for j in tr.list_jobs()}
    want: dict[tuple[str, str], tuple[str, date]] = {}
    for jid, j in jobs.items():
        if j.get("Status") != "applied":
            continue
        since = _day(j.get("DateApplied"))
        if since and (today - since).days >= n:
            want[(jid, APPLIED)] = (f"No reply in {(today - since).days} days. Send a short follow-up.", since)
        wait = _outreach_wait(store, jid)
        if wait and (today - wait[1]).days >= (wait[2] or n):
            what = ("Your follow-up got no answer either" if wait[0] == OUTREACH14 else "Your message got no answer")
            want[(jid, wait[0])] = (f"{what} in {(today - wait[1]).days} days. Send a nudge.", wait[1])
    have: set[tuple[str, str]] = set()  # open AND done keys: Done sticks
    for it in tr.list_action_items(open_only=False):
        if it.get("Type") != TYPE or str(it.get("Detail") or "").split("\n")[0] in (REACH, "reach_first"):
            continue
        key = (str(it.get("JobID") or ""), str(it.get("Detail") or "").split("\n")[0])
        if key in want:
            have.add(key)
        elif str(it.get("Done") or "N").upper() != "Y":
            tr.mark_action_done(str(it["ID"]), note="Closed: the job moved on or the contact replied.")
    from careeros.tracker import add_action

    lines = []
    for key, (what, _since) in want.items():
        if key not in have:
            lines.append(add_action(s, what, TYPE, job_id=key[0], detail=key[1],
                                   id=hashlib.sha1("|".join(key).encode()).hexdigest()[:8]))
    return lines


REACH = "reach_out"  # Detail marker; Action Item Type stays `follow_up` (no UI/schema change)


def reach_out_window(s: Settings) -> int:
    try:
        return max(1, int((s.pipeline.get("follow_ups") or {}).get("reach_out_window_days", 14)))
    except (TypeError, ValueError):
        return 14


def raise_reach_outs(s: Settings, today: date | None = None) -> list[str]:
    """REQ-156: one high-priority `reach_out` item per job applied in the last `reach_out_window_days`, due the day
    it is raised. Closed once a draft is marked sent (`careeros outreach sent`) or the job leaves `applied`; a done
    or dismissed item is never re-raised."""
    from careeros.tracker import add_action

    today, win = today or date.today(), reach_out_window(s)
    tr, store = Tracker(settings=s), Store(s)
    jobs = {str(j["JobID"]): j for j in tr.list_jobs()}

    def sent(jid: str) -> bool:
        return any(isinstance(x, dict) and x.get("sent") is True
                   for x in _json(store.job_dir(jid) / "outreach.json").get("drafts") or [])

    have: set[str] = set()
    for it in tr.list_action_items(open_only=False):
        if it.get("Type") != TYPE or str(it.get("Detail") or "").split("\n")[0] != REACH:
            continue
        jid = str(it.get("JobID") or "")
        have.add(jid)
        if str(it.get("Done") or "N").upper() != "Y" and ((jobs.get(jid) or {}).get("Status") != "applied" or sent(jid)):
            tr.mark_action_done(str(it["ID"]), note="Closed: outreach sent or the job moved on.")
    lines = []
    for jid, j in jobs.items():
        since = _day(j.get("DateApplied"))
        if j.get("Status") != "applied" or jid in have or not since or (today - since).days > win or sent(jid):
            continue
        p = store.load_posting(jid)
        what = (f"Reach out to the recruiter or hiring manager for {p.title} at {p.company}" if p
                else "Reach out to the recruiter or hiring manager for this job")
        lines.append(add_action(s, what, TYPE, job_id=jid, detail=REACH, priority="H", due=today.isoformat(),
                                due_reason="Early outreach doubles the odds of a reply",
                                id=hashlib.sha1(f"{jid}|{REACH}".encode()).hexdigest()[:8]))
    return lines
