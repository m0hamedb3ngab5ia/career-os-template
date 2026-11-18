"""Send panel for outreach drafts (user 2026-11-18). Per draft, four options in chat: read it, open it in the iPhone
Mail app (mailto, no attachment), open a Gmail draft with the résumé attached (IMAP append to the candidate's own
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

WARNING = ("Auto-send sends right away from your Gmail. Addresses are guesses at each company's email format; a "
           "bounce hurts how Gmail treats your mail, so send only the ones you approve, one at a time.")


class SendError(RuntimeError):
    pass


def build_message(frm: str, d: dict[str, Any], resume: Path | None, name: str) -> EmailMessage:
    em = d.get("email") or {}
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = frm, str(d["to"]), str(em.get("subject") or "")
    m.set_content(str(em.get("body") or ""))
    if resume and resume.exists():
        m.add_attachment(resume.read_bytes(), maintype="application", subtype="pdf",
                         filename=f"{name.replace(' ', '_')}_Resume.pdf")
    return m


def mail_link(d: dict[str, Any]) -> str:
    em = d.get("email") or {}
    return f"mailto:{quote(str(d['to']))}?subject={quote(str(em.get('subject') or ''))}&body={quote(str(em.get('body') or ''))}"


def gmail_draft(frm: str, password: str, d: dict[str, Any], resume: Path | None, name: str, *,
                imap: Callable[[str], Any] = imaplib.IMAP4_SSL) -> str:
    """Puts the email, résumé attached, in the candidate's Gmail Drafts; returns a link that finds it."""
    box = imap("imap.gmail.com")
    box.login(frm, password)
    try:
        box.append('"[Gmail]/Drafts"', "\\Draft", imaplib.Time2Internaldate(time.time()),
                   build_message(frm, d, resume, name).as_bytes())
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
    if not yes:
        raise SendError(f"{WARNING} Re-run with --yes to send.")
    smtp(frm, password, build_message(frm, d, resume, name))
    d.update(sent=True, sent_by="candidate", sent_via="careeros", sent_at=today or date.today().isoformat())


def panel(rows: list[dict[str, Any]]) -> str:
    """Markdown: one table row per draft with Read / Mail / Gmail / Auto-send, then each draft in full."""
    out = ["| # | To | Company, role | Address | Read | iPhone | Laptop | Auto-send |", "|---|---|---|---|---|---|---|---|"]
    full = []
    for r in rows:
        d, n = r["draft"], r["n"]
        who = f"{d.get('contact')} ({str(d.get('role') or '').replace('_', ' ')})"
        job = f"{r['company']}, [{r['title']}]({r['url']})"
        addr = f"{d.get('to')} ({d.get('to_confidence') or '?'})"
        if d.get("hold"):
            out.append(f"| {n} | {who} | {job} | {addr} | [Read](#d{n}) | held: {d.get('hold_reason') or 'unverified'} | | |")
        else:
            gm = f"[Gmail]({r['gmail']})" if r.get("gmail") else "reply `gmail " + str(n) + "`"
            out.append(f"| {n} | {who} | {job} | {addr} | [Read](#d{n}) | [Mail]({mail_link(d)}) | {gm} | `send {n}` |")
        em = d.get("email") or {}
        full.append(f'<a id="d{n}"></a>\n### {n}. {d.get("contact")}, {r["company"]}\n\n**Subject:** {em.get("subject")}\n\n'
                    f'{em.get("body")}\n')
    legend = ("**iPhone:** opens Mail with the email typed in; attach your résumé yourself. **Laptop:** a Gmail draft "
              "with your résumé attached; read it and press Send. **Auto-send:** reply `send <#>`. " + WARNING)
    return "\n".join(out) + "\n\n" + legend + "\n\n## Drafts\n\n" + "\n".join(full)
