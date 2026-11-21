"""Send panel for outreach drafts (user 2026-11-18). Per draft, four options in chat: read it, open it in the Mail app (iPhone or Mac)
(mailto, no attachment), open a Gmail draft with the résumé attached (IMAP append to the candidate's own
Drafts; the candidate presses Send), or send it now on the candidate's explicit request (SMTP, with a bounce warning).
The app password is the one `careeros notify setup` stored in the Keychain; nothing here runs on a schedule."""
from __future__ import annotations

import email
import email.policy
import html
import imaplib
import re
import smtplib
import time
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from careeros.high_odds import final_body

WARNING = ("Auto-send sends right away from your Gmail. Addresses are guesses at each company's email format; a "
           "bounce hurts how Gmail treats your mail, so send only the ones you approve, one at a time.")


class SendError(RuntimeError):
    pass


def check(d: dict[str, Any]) -> None:
    """Every route (Mail link, Gmail draft, send) refuses a held draft or one that has not passed the outreach gate."""
    if d.get("hold"):
        raise SendError(f"{d.get('contact')}: held ({d.get('hold_reason') or 'unverified'}); fix the draft first")
    if d.get("qa_pass") is not True:
        raise SendError(f"{d.get('contact')}: has not passed outreach QA ({'; '.join(d.get('qa_problems') or []) or 'run `careeros outreach qa`'})")


def build_message(frm: str, d: dict[str, Any], resume: Path | None, name: str,
                  message_id: str | None = None) -> EmailMessage:
    """The email with the résumé attached. Refuses without the PDF: every draft says the résumé is attached."""
    check(d)
    if not resume or not resume.exists():
        raise SendError(f"{d.get('contact')}: no résumé PDF for this job (resume.pdf or submitted/*/resume.pdf)")
    em = d.get("email") or {}
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = frm, str(d["to"]), str(em.get("subject") or "")
    if message_id:
        m["Message-ID"] = message_id
    m.set_content(final_body(d))
    if d.get("links"):  # {"text in body": url}: Gmail shows the HTML part, so the role name links to the posting
        h = html.escape(final_body(d), quote=False)
        for text, url in d["links"].items():
            h = h.replace(html.escape(text, quote=False), f'<a href="{html.escape(url)}">{html.escape(text, quote=False)}</a>')
        m.add_alternative(f"<div>{h.replace(chr(10), '<br>')}</div>", subtype="html")
    m.add_attachment(resume.read_bytes(), maintype="application", subtype="pdf",
                     filename=f"{name.replace(' ', '_')}_Resume.pdf")
    return m


def mail_link(d: dict[str, Any]) -> str | None:
    """mailto: link (Mail app on iPhone or Mac); None for a held or not-QA-passed draft."""
    try:
        check(d)
    except SendError:
        return None
    em = d.get("email") or {}
    return f"mailto:{quote(str(d['to']))}?subject={quote(str(em.get('subject') or ''))}&body={quote(final_body(d))}"


def gmail_draft(frm: str, password: str, d: dict[str, Any], resume: Path | None, name: str, *,
                imap: Callable[[str], Any] = imaplib.IMAP4_SSL) -> str:
    """Puts the email, résumé attached, in the candidate's Gmail Drafts; returns a link that finds it."""
    msg = build_message(frm, d, resume, name)
    box = imap("imap.gmail.com")
    box.login(frm, password)
    try:
        typ, data = box.append('"[Gmail]/Drafts"', "\\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if typ != "OK":  # a rejected APPEND returns NO without raising
            raise SendError(f"Gmail refused the draft: {data!r}")
        # Gmail opens a draft by its X-GM-MSGID in hex; a search link only lands on the list (user 2026-11-19)
        uid = re.search(rb"APPENDUID \d+ (\d+)", b" ".join(x for x in data if isinstance(x, bytes)))
        if uid:
            box.select('"[Gmail]/Drafts"')
            _, got = box.uid("FETCH", uid.group(1).decode(), "(X-GM-MSGID)")
            mid = re.search(rb"X-GM-MSGID (\d+)", got[0] if got and isinstance(got[0], bytes) else b"")
            if mid:
                return f"https://mail.google.com/mail/u/0/#drafts?compose={int(mid.group(1)):x}"
    finally:
        box.logout()
    return "https://mail.google.com/mail/u/0/#search/" + quote(f"in:drafts to:{d['to']}")


def _smtp(frm: str, password: str, m: EmailMessage) -> None:
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as sm:
        sm.starttls()
        sm.login(frm, password)
        sm.send_message(m)


def send_now(frm: str, password: str, d: dict[str, Any], resume: Path | None, name: str, *, yes: bool,
             smtp: Callable[..., None] = _smtp, today: str | None = None) -> None:
    """Sends one draft the candidate approved in chat. Refuses without `yes` or when already sent."""
    if d.get("sent"):
        raise SendError(f"{d.get('contact')}: already sent")
    check(d)
    if not yes:
        raise SendError(f"{WARNING} Re-run with --yes to send.")
    mid = d.get("message_id") or make_msgid(domain=frm.partition("@")[2] or None)  # stored so a follow-up can thread
    m = build_message(frm, d, resume, name, mid)
    smtp(frm, password, m)
    d.update(sent=True, sent_by="candidate", sent_via="careeros", sent_at=today or date.today().isoformat(),
             message_id=mid, sent_subject=m["Subject"])


KINDS = ("7d", "14d")


def followup_due(d: dict[str, Any], kind: str, after_days: int = 7) -> date | None:
    """Day a follow-up is due: the 7d one `after_days` after the send, the 14d one 14 days after the send."""
    try:
        sent = datetime.fromisoformat(str(d.get("sent_at") or d.get("sent_date"))[:10]).date()
    except ValueError:
        return None
    return sent + timedelta(days=14 if kind == "14d" else after_days)


def followup_check(d: dict[str, Any], kind: str, *, replied: bool = False, after_days: int = 7,
                   today: date | None = None) -> list[str]:
    """Refuses (SendError) a follow-up that should not go out; returns warnings (e.g. sent before the due date)."""
    who = d.get("contact")
    if not d.get("sent"):
        raise SendError(f"{who}: the first email has not been sent yet")
    if d.get("bounced") and d["bounced"][-1].get("to") == d.get("to"):
        raise SendError(f"{who}: the latest attempt to {d.get('to')} bounced; no follow-up to an address that failed")
    if replied or d.get("replied"):
        raise SendError(f"{who}: already replied; no follow-up")
    if d.get(f"followup_{kind}_sent_at"):
        raise SendError(f"{who}: the {kind} follow-up was already sent on {d[f'followup_{kind}_sent_at']}")
    if not str(d.get(f"followup_{kind}") or "").strip():
        raise SendError(f"{who}: no {kind} follow-up text; run /draft-outreach follow-ups for this job")
    if not d.get("to"):
        raise SendError(f"{who}: no email address on the draft")
    due = followup_due(d, kind, after_days)
    if due and (today or date.today()) < due:
        return [f"sent before the due date ({due.isoformat()})"]
    return []


def window_hint(now: datetime | None = None) -> str | None:
    """One-line hint (never blocks) when it is outside the best cold-email window: Tue-Thu, 8am-12pm recipient time."""
    now = now or datetime.now()
    if now.weekday() in (1, 2, 3) and 8 <= now.hour < 12:
        return None
    return "best send window is Tue-Thu 8am-12pm in the recipient's time zone (hint only; sent anyway)"


def find_message_id(frm: str, password: str, d: dict[str, Any], *, imap: Callable[[str], Any] = imaplib.IMAP4_SSL) -> str | None:
    """Message-ID of the original email in the candidate's Sent Mail, for drafts sent before the id was stored. Searches
    by To (ASCII) and matches the decoded Subject here, so subjects with accents or dashes work."""
    want = str((d.get("email") or {}).get("subject") or "").strip().lower()
    box = imap("imap.gmail.com")
    box.login(frm, password)
    try:
        box.select('"[Gmail]/Sent Mail"', readonly=True)
        typ, ids = box.search(None, "TO", f'"{d["to"]}"')
        for num in reversed(ids[0].split() if typ == "OK" and ids and ids[0] else []):
            typ, got = box.fetch(num, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT)])")
            raw = got[0][1] if typ == "OK" and got and isinstance(got[0], tuple) else b""
            h = email.message_from_bytes(raw, policy=email.policy.default)
            if str(h["Subject"] or "").strip().lower() == want and h["Message-ID"]:
                return str(h["Message-ID"]).strip()
        return None
    finally:
        box.logout()


def build_followup(frm: str, d: dict[str, Any], kind: str, message_id: str | None, subject: str | None = None) -> EmailMessage:
    """Plain-text follow-up, no attachment; with `message_id` it replies in the original Gmail thread."""
    orig = str(subject or d.get("sent_subject") or (d.get("email") or {}).get("subject") or "").strip()
    m = EmailMessage()
    m["From"], m["To"] = frm, str(d["to"])
    m["Subject"] = orig if orig.lower().startswith("re:") else f"Re: {orig}"
    if message_id:
        m["In-Reply-To"] = m["References"] = message_id
    m.set_content(str(d[f"followup_{kind}"]).strip())
    return m


def send_followup(frm: str, password: str, d: dict[str, Any], kind: str, *, yes: bool, replied: bool = False,
                  after_days: int = 7, smtp: Callable[..., None] | None = None, today: date | None = None,
                  imap: Callable[[str], Any] = imaplib.IMAP4_SSL, now: datetime | None = None) -> list[str]:
    """Sends the follow-up as a reply in the original thread; records `followup_<kind>_sent_at`. Returns notes."""
    notes = followup_check(d, kind, replied=replied, after_days=after_days, today=today)
    if not yes:
        raise SendError(f"{WARNING} Re-run with --yes to send.")
    hint = window_hint(now)
    if hint:
        notes.append(hint)
    mid = d.get("message_id")
    if not mid:
        mid = find_message_id(frm, password, d, imap=imap)
        if mid:
            d["message_id"] = mid
        else:
            notes.append("original not found in Sent Mail: sent without threading headers (Re: subject only)")
    (smtp or _smtp)(frm, password, build_followup(frm, d, kind, mid))
    d[f"followup_{kind}_sent_at"] = (today or date.today()).isoformat()
    return notes


def panel(rows: list[dict[str, Any]]) -> str:
    """Markdown: one table row per draft with Read / Mail / Gmail / Auto-send, then each draft in full."""
    out = ["| # | To | Company, role | Address | Read | Mail app | Gmail | Auto-send |", "|---|---|---|---|---|---|---|---|"]
    full = []
    for r in rows:
        d, n = r["draft"], r["n"]
        role = str(d.get("role") or "").replace("_", " ")
        who = f"{d.get('contact')} ({role})" if role and role != "other" else str(d.get("contact"))
        job = f"{r['company']}, [{r['title']}]({r['url']})"
        addr = f"{d.get('to')} ({d.get('to_confidence') or '?'})"
        if d.get("hold"):
            out.append(f"| {n} | {who} | {job} | {addr} | [Read](#d{n}) | held: {d.get('hold_reason') or 'unverified'} | | |")
        else:
            gm = f"[Gmail]({r['gmail']})" if r.get("gmail") else "reply `gmail " + str(n) + "`"
            ml = mail_link(d)
            mail = f"[Mail]({ml})" if ml else "fails QA"
            out.append(f"| {n} | {who} | {job} | {addr} | [Read](#d{n}) | {mail} | {gm} | `send {n}` |")
        em = d.get("email") or {}
        full.append(f'<a id="d{n}"></a>\n### {n}. {d.get("contact")}, {r["company"]}\n\n**Subject:** {em.get("subject")}\n\n'
                    f'{em.get("body")}\n')
    legend = ("**Mail app** (iPhone or Mac): opens Mail with the email typed in; attach your résumé yourself. **Gmail:** a draft "
              "with your résumé attached; read it and press Send. **Auto-send:** reply `send <#>`. " + WARNING)
    return "\n".join(out) + "\n\n" + legend + "\n\n## Drafts\n\n" + "\n".join(full)
