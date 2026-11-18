"""Send panel for outreach drafts (user 2026-11-18). Per draft, four options in chat: read it, open it in the Mail app (iPhone or Mac)
(mailto, no attachment), open a Gmail draft with the résumé attached (IMAP append to the candidate's own
Drafts; the candidate presses Send), or send it now on the candidate's explicit request (SMTP, with a bounce warning).
The app password is the one `careeros notify setup` stored in the Keychain; nothing here runs on a schedule."""
from __future__ import annotations

import imaplib
import smtplib
import time
from datetime import date
from email.message import EmailMessage
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


def build_message(frm: str, d: dict[str, Any], resume: Path | None, name: str) -> EmailMessage:
    """The email with the résumé attached. Refuses without the PDF: every draft says the résumé is attached."""
    check(d)
    if not resume or not resume.exists():
        raise SendError(f"{d.get('contact')}: no résumé PDF for this job (resume.pdf or submitted/*/resume.pdf)")
    em = d.get("email") or {}
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = frm, str(d["to"]), str(em.get("subject") or "")
    m.set_content(final_body(d))
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
    smtp(frm, password, build_message(frm, d, resume, name))
    d.update(sent=True, sent_by="candidate", sent_via="careeros", sent_at=today or date.today().isoformat())


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
