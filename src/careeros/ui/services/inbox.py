"""GET /api/inbox and /api/inbox/{job_id}: the Inbox & follow-ups screen.

Jobs after applying (applied, screening, interview, offer) from the index, with what the files already say about
them: the inbox-sync skill's log lines in log.md (`[inbox-sync] <class> from <from> <date> -> status <s> (<link>)`),
its fallback `data/sync_updates.json`, the draft-outreach skill's outreach.json, and the status history. The next
follow-up and its due date are computed from `pipeline.yaml: ui.followup_*_days`. Nothing here sends anything:
sending follow-ups and starting inbox sync from the UI are not built, and the payload says so (`sync`, `sending`).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from careeros.ui.config import load_ui_config
from careeros.ui.services.jobs import job_dir_for
from careeros.ui.services.status import POST_APPLY

PLACEHOLDER_RE = re.compile(r"\[[^\[\]\n]{1,120}\]")
_LOG_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[inbox-sync\] (\w+) from (.+?) -> status (\S+) "
                     r"\((\S+)\)\s*$")
_DATE_TAIL = re.compile(r"\s+\d{4}-\d{2}-\d{2}(?:[T ][\d:]+)?$")
THANKS = "post_interview_thanks"
FOLLOWUP_KINDS = ("followup_7d", "followup_14d")
_FOLLOWUP, _PARENT_SENT = "_ui_followup", "_ui_parent_sent"  # internal markers set by _outreach_items
SYNC_OFF = "Inbox sync isn't set up yet"
SYNC_NO_BUTTON = "Inbox sync runs on its schedule; starting it from here isn't built yet"
SENDING_OFF = "Follow-up sending isn't built yet"


def placeholders(text: str | None) -> list[str]:
    """The `[VARIABLE]`s a draft still carries (templates/followup_email: never send one with a bracket left)."""
    out: list[str] = []
    for m in PLACEHOLDER_RE.findall(text or ""):
        if m not in out:
            out.append(m)
    return out


def _parse(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.astimezone()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def parse_inbox_log(log: str) -> list[dict[str, Any]]:
    """The inbox-sync skill's lines in a job's log.md, oldest first. Lines that don't match are skipped."""
    out = []
    for line in (log or "").splitlines():
        m = _LOG_RE.match(line.strip())
        if not m:
            continue
        ts, cls, sender, status, link = m.groups()
        at = _parse(ts.replace(" ", "T"))
        out.append({"at": _iso(at), "class": cls, "from": _DATE_TAIL.sub("", sender).strip(), "status": status,
                    "link": link if link.startswith(("https://", "http://")) else None})
    return out


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _words(text: str | None) -> int:
    return len((text or "").split())


def draft_view(d: dict[str, Any], contact: dict[str, Any] | None = None, policy: Any = None) -> dict[str, Any]:
    """One outreach.json draft (drafts[] or followups[]) as the UI shows it. `mode`: sent | always_manual (thank-you
    notes) | manual (connected / mutuals) | verified_email | email_draft (an email follow-up: never auto-sent) |
    linkedin (LinkedIn is always draft-only). `due`: a follow-up's `send_after`, once the note it follows is sent.

    Manual comes from the saved `manual_tailor` flag OR, with a `policy`, from the contact's current degree / mutuals
    (careeros.outreach.needs_manual_outreach): a person marked Connected after the draft was written is never
    treated as automatable."""
    def _str(x: Any) -> str | None:
        return x if isinstance(x, str) else None

    manual_reason = _str(d.get("manual_reason"))
    manual = bool(d.get("manual_tailor"))
    if contact is not None and policy is not None:
        from careeros.outreach import needs_manual_outreach

        now_manual, reason = needs_manual_outreach(contact, policy)
        if now_manual:
            manual, manual_reason = True, manual_reason or reason
    followup = bool(d.get(_FOLLOWUP)) or d.get("kind") in FOLLOWUP_KINDS
    email = d.get("email") if isinstance(d.get("email"), dict) else None
    linkedin_note = _str(d.get("linkedin_note"))
    linkedin_message = _str(d.get("linkedin_message"))
    channel = _str(d.get("channel")) or ("email" if email else "linkedin")
    if channel == "linkedin" and (linkedin_message or linkedin_note):
        email = None  # a LinkedIn first touch shows (and is blocked by) its LinkedIn variant, not the email block
    to = _str(d.get("to"))
    verified = channel != "linkedin" and bool(to) and (d.get("to_confidence") == "verified" or bool(
        contact and contact.get("email_confidence") == "verified" and contact.get("email") == to))
    body = _str((email or {}).get("body")) or linkedin_message or linkedin_note or _str(d.get("body")) or ""
    if d.get("sent"):
        mode = "sent"
    elif d.get("kind") == THANKS:
        mode = "always_manual"
    elif manual:
        mode = "manual"
    elif followup:  # follow-ups are never auto-sent: the candidate sends them on their own channel
        mode = "linkedin" if channel == "linkedin" else "email_draft"
    elif verified and email:
        mode = "verified_email"
    else:
        mode = "linkedin"
    # a scheduled follow-up (send_after) is due once the note it follows up on has gone out
    due = _str(d.get("send_after")) if not d.get("sent") and d.get(_PARENT_SENT, True) else None
    subject = _str((email or {}).get("subject"))
    texts = [subject, body, linkedin_note, linkedin_message]
    ph: list[str] = []
    for t in texts:
        for p in placeholders(t):
            if p not in ph:
                ph.append(p)
    return {
        "contact": _str(d.get("contact")) or "", "role": _str(d.get("role")) or "", "kind": _str(d.get("kind")) or "",
        "channel": channel, "to": to, "verified": verified,
        "subject": subject, "body": body, "linkedin_note": linkedin_note,
        "linkedin_message": linkedin_message, "manual_tailor": manual,
        "manual_reason": manual_reason, "sent": bool(d.get("sent")), "sent_by": d.get("sent_by"),
        "sent_date": d.get("sent_date"), "mode": mode, "followup": followup, "due": due, "placeholders": ph, "words": _words(body),
    }


def _outreach_items(data: Any) -> list[dict[str, Any]]:
    """Every outreach item in reading order, normalized like careeros.qa_ext.outreach_data()/outreach_texts(): a
    bare list is read as `drafts`, and each draft's own `followup_7d` / `followup_14d` (draft-outreach skill) and
    `followups[]` come right after it, inheriting its contact, role, channel and recipient (a plain-string follow-up
    becomes its body)."""
    if isinstance(data, list):
        data = {"drafts": data}
    if not isinstance(data, dict):
        return []
    out: list[dict[str, Any]] = []
    for key in ("drafts", "followups"):
        items = data.get(key)
        for d in items if isinstance(items, list) else []:
            if not isinstance(d, dict):
                continue
            out.append({**d, _FOLLOWUP: True} if key == "followups" else d)
            inherit = {k: d.get(k) for k in ("contact", "role", "channel", "to", "to_confidence", "manual_tailor",
                                             "manual_reason")}
            inherit.update({_FOLLOWUP: True, _PARENT_SENT: bool(d.get("sent"))})
            for k in ("followup_7d", "followup_14d"):
                text = d.get(k)
                if isinstance(text, str) and text.strip():
                    out.append({**inherit, "kind": k, "body": text})
            nested = d.get("followups")
            for f in nested if isinstance(nested, list) else []:
                if isinstance(f, str) and f.strip():
                    f = {"body": f}
                if isinstance(f, dict):
                    out.append({**inherit, "kind": None, **f, _FOLLOWUP: True, _PARENT_SENT: bool(d.get("sent"))})
    return out


def job_drafts(job_dir: Path, contacts: list[dict[str, Any]] | None = None, policy: Any = None
               ) -> list[dict[str, Any]]:
    """Every draft in the job's outreach.json (drafts[], each with its own followups[], then top-level followups[]);
    none when the file is missing or broken. Pass the job's contacts and the OutreachPolicy so the relationship gate
    applies to each draft."""
    by_name = {str(c.get("name", "")).strip().lower(): c for c in contacts or [] if isinstance(c, dict)}
    return [draft_view(d, by_name.get(str(d.get("contact", "")).strip().lower()), policy)
            for d in _outreach_items(_json(job_dir / "outreach.json"))]


def _contacts(job_dir: Path) -> list[dict[str, Any]]:
    got = _json(job_dir / "contacts.json")
    items = got.get("contacts") if isinstance(got, dict) else None
    return [c for c in items if isinstance(c, dict)] if isinstance(items, list) else []


def _log(job_dir: Path) -> str:
    try:
        return (job_dir / "log.md").read_text(encoding="utf-8")
    except OSError:
        return ""


def _status_since(ix: Any, job_id: str, status: str) -> datetime | None:
    rows = ix.query("SELECT at FROM status_history WHERE job_id = ? AND status = ? ORDER BY seq DESC LIMIT 1",
                    (job_id, status))
    return _parse(rows[0]["at"]) if rows else None


def _primary(status: str, drafts: list[dict[str, Any]]) -> int | None:
    """The draft the right pane opens first: the one that matches the job's next follow-up, else the first unsent."""
    want = {"applied": ("post_apply_outreach", "cold_email"), "screening": ("status_followup",),
            "interview": (THANKS, "status_followup"), "offer": ()}.get(status, ())
    for kind in want:
        for i, d in enumerate(drafts):
            if d["kind"] == kind and not d["sent"]:
                return i
    for i, d in enumerate(drafts):
        if not d["sent"]:
            return i
    return None


def _status_followup(ix: Any, job: dict[str, Any], cfg: Any, mode: str, last_email: dict[str, Any] | None,
                     status: str, *more: datetime | None) -> dict[str, Any]:
    """A status follow-up due `followup_no_response_days` after the latest of: entering `status`, the last synced
    email, and any extra anchors (a sent thank-you)."""
    anchors = [_status_since(ix, job["job_id"], status), _parse((last_email or {}).get("at")), *more]
    since = max((a for a in anchors if a), default=None)
    due = since + timedelta(days=cfg.followup_no_response_days) if since else None
    return {"kind": "status_followup", "due": _iso(due), "mode": mode}


def _next(job: dict[str, Any], ix: Any, cfg: Any, drafts: list[dict[str, Any]], primary: int | None,
          last_email: dict[str, Any] | None) -> dict[str, Any]:
    status = job["status"]
    draft = drafts[primary] if primary is not None else None
    mode = draft["mode"] if draft else "no_draft"
    if status == "offer":
        return {"kind": "offer_reply", "due": None, "mode": "you_reply"}
    if status == "interview":
        thanks = [d for d in drafts if d["kind"] == THANKS]
        if any(not d["sent"] for d in thanks):
            return {"kind": THANKS, "due": None, "mode": "always_manual"}
        if thanks:  # thank-you sent: next is a status check, counted from the last thing that happened
            sent = [_parse(d["sent_date"]) for d in thanks]
            return _status_followup(ix, job, cfg, mode, last_email, "interview", *sent)
        if last_email and last_email["class"] == "interview_invite":
            return {"kind": "reply_with_slot", "due": None, "mode": "you_reply"}
        return {"kind": THANKS, "due": None, "mode": "always_manual"}
    if status == "screening":
        return _status_followup(ix, job, cfg, mode, last_email, "screening")
    applied = _parse(job["applied_at"])
    # one first touch per contact: the step is done only once every contact's first note has gone out
    firsts = [d for d in drafts if not d["followup"] and d["kind"] not in ("status_followup", THANKS)]
    sent = bool(firsts) and all(d["sent"] for d in firsts)
    due = applied + timedelta(days=cfg.followup_after_apply_days) if applied and not sent else None
    return {"kind": "post_apply_outreach", "due": _iso(due), "mode": "sent" if sent else mode}


def _row(settings: Any, ix: Any, job: dict[str, Any], now: datetime, cfg: Any) -> tuple[dict[str, Any], dict]:
    d = Path(settings.paths["jobs_dir"]) / job["job_id"]
    from careeros.outreach import OutreachPolicy

    contacts = _contacts(d)
    drafts = job_drafts(d, contacts, OutreachPolicy.from_settings(settings))
    emails = parse_inbox_log(_log(d))
    last_email = emails[-1] if emails else None
    primary = _primary(job["status"], drafts)
    applied = _parse(job["applied_at"])
    row = {
        "job_id": job["job_id"], "company": job["company"], "title": job["title"], "status": job["status"],
        "tier": job["tier"], "applied_at": job["applied_at"], "updated_at": job["updated_at"],
        "days_since_applied": (now - applied).days if applied else None,
        "last_email": last_email, "next": _next(job, ix, cfg, drafts, primary, last_email),
        "drafts": len(drafts), "placeholders": len(drafts[primary]["placeholders"]) if primary is not None else 0,
    }
    return row, {"dir": d, "contacts": contacts, "drafts": drafts, "emails": emails, "primary": primary}


def _sync_state(settings: Any) -> dict[str, Any]:
    from careeros.config import ConfigError
    from careeros.runs.schedule import load_schedule

    try:
        enabled = load_schedule(settings).jobs["inbox_sync"].enabled
    except (ConfigError, KeyError):
        enabled = False
    return {"available": False, "reason": SYNC_NO_BUTTON if enabled else SYNC_OFF}


def _last_sync(ix: Any) -> str | None:
    """When the last inbox sync that ran to the end of its work ended (failed, paused or cancelled runs don't
    count)."""
    from careeros.runs.runner import CLEAN_STOPS

    done = tuple(s for s in CLEAN_STOPS if s not in ("paused", "cancelled"))

    rows = ix.query("SELECT ended_at FROM runs WHERE kind = 'inbox_sync' AND ended_at IS NOT NULL "
                    f"AND stop_reason IN ({','.join('?' * len(done))}) ORDER BY ended_at DESC LIMIT 1", done)
    return rows[0]["ended_at"] if rows else None


def _sort_key(r: dict[str, Any]) -> tuple:
    due = _parse(r["next"]["due"])
    applied = _parse(r["applied_at"])
    return (due is None, due.timestamp() if due else 0, -(applied.timestamp() if applied else 0), r["company"] or "")


def list_inbox(settings: Any, ix: Any, now: datetime) -> dict[str, Any]:
    cfg = load_ui_config(settings)
    jobs = ix.query(f"SELECT job_id, company, title, status, tier, applied_at, updated_at FROM jobs "
                    f"WHERE status IN ({','.join('?' * len(POST_APPLY))})", POST_APPLY)
    rows = sorted((_row(settings, ix, j, now, cfg)[0] for j in jobs), key=_sort_key)
    return {"items": rows, "last_sync": _last_sync(ix), "sync": _sync_state(settings),
            "sending": {"available": False, "reason": SENDING_OFF}}


def _pending_updates(settings: Any, job_id: str) -> list[dict[str, Any]]:
    got = _json(Path(settings.paths["jobs_dir"]).parent / "sync_updates.json")
    out = []
    for u in got if isinstance(got, list) else []:
        if isinstance(u, dict) and u.get("job_id") == job_id and not u.get("applied"):
            out.append({"at": _iso(_parse(u.get("date"))), "type": "pending_update", "status": u.get("status"),
                        "note": u.get("note")})
    return out


def inbox_detail(settings: Any, ix: Any, job_id: str, now: datetime) -> dict[str, Any] | None:
    """One job's thread (status changes, classified emails, pending sync updates, sends) newest first, and its
    drafts. Any job with a posting answers (the Job detail screen reuses it); unknown ids are None."""
    if job_dir_for(settings, job_id) is None:
        return None
    jobs = ix.query("SELECT job_id, company, title, status, tier, applied_at, updated_at FROM jobs WHERE job_id = ?",
                    (job_id,))
    if not jobs:
        return None
    row, extra = _row(settings, ix, jobs[0], now, load_ui_config(settings))
    thread: list[dict[str, Any]] = [
        {"at": _iso(_parse(h["at"])), "type": "status", "status": h["status"], "note": h["note"]}
        for h in ix.query("SELECT status, at, note FROM status_history WHERE job_id = ? ORDER BY seq", (job_id,))]
    thread += [{"at": e["at"], "type": "email", "class": e["class"], "from": e["from"], "link": e["link"],
                "status": e["status"]} for e in extra["emails"]]
    thread += _pending_updates(settings, job_id)
    thread += [{"at": _iso(_parse(d["sent_date"])), "type": "sent", "contact": d["contact"], "kind": d["kind"],
                "sent_by": d["sent_by"]} for d in extra["drafts"] if d["sent"]]
    thread = [e for e in thread if e["at"]]
    thread.sort(key=lambda e: _parse(e["at"]).timestamp(), reverse=True)  # type: ignore[union-attr]
    return {**row, "thread": thread, "drafts": extra["drafts"], "primary": extra["primary"],
            "sync": _sync_state(settings), "sending": {"available": False, "reason": SENDING_OFF}}
