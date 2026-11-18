"""High-odds channels as the default path (REQ-161..163, DEC-027). Fresh postings first, outreach after applying,
and volume that yields to outreach. Nothing here sends mail to anyone but the candidate (DEC-026) and nothing
opens LinkedIn; outreach drafts are drafts until the candidate fills "your line" and presses send themselves."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Any, Callable
from urllib.parse import quote

from careeros.config import Settings
from careeros.store import Store
from careeros.tracker import Tracker

FRESH_URGENT_HOURS = 48
DONE_STATUSES = {"applied", "screening", "interview", "offer", "rejected", "skipped", "withdrawn"}
REACH_FIRST = "reach_first"
MAX_WORDS = 120  # message only, sign-off excluded; same as config qa.yaml after-apply (user 2026-11-18)

# One plain line per item kind. Numbers are copied from docs/work/yield-model/research (funnel.md, competition.md).
WHY = {
    "fresh": "Fresh: a posting that is only a day or two old is one of the few edges left, because most applicants arrive later.",
    "reach_out": "Why: a referred application turns into an interview about 40% of the time, a cold one about 3% (Ashby).",
    REACH_FIRST: "Why: applications per recruiter went from 146 to 746 between 2022 and 2025 (Greenhouse), so more volume buys less each year.",
}


def _cfg(s: Settings, key: str) -> dict[str, Any]:
    v = s.pipeline.get(key)
    return v if isinstance(v, dict) else {}


def max_overdue(s: Settings) -> int:
    try:
        return max(0, int(_cfg(s, "outreach").get("max_overdue", 3)))
    except (TypeError, ValueError):
        return 3


def outreach_auto(s: Settings) -> bool:
    return _cfg(s, "outreach").get("auto", True) is not False


def _dt(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def age_hours(p: Any, now: datetime) -> float | None:
    v = p.first_published or p.posted_at
    d = _dt(v) if v else None
    return max(0.0, (now - d).total_seconds() / 3600) if d else None


def scan_fresh(s: Settings, now: datetime | None = None, *, send: Callable[..., str] | None = None) -> list[str]:
    """REQ-161: urgent email (once per job) for a fitting posting at most 48h old that is not yet applied to."""
    from careeros import notify
    from careeros.watch import min_fit

    now = now or datetime.now(timezone.utc)
    store, tr = Store(s), Tracker(settings=s)
    status = {str(j["JobID"]): str(j.get("Status") or "") for j in tr.list_jobs()}
    st = notify._state(s)
    if "fresh_seen" not in st:  # first run: baseline existing jobs so rollout doesn't flood urgent emails
        notify._save(s, fresh_seen=list(store.iter_job_ids()))
        return []
    seen = list(st.get("fresh_seen") or [])
    sent = []
    for jid in store.iter_job_ids():
        if jid in seen:
            continue
        sc, p = store.load_score(jid), store.load_posting(jid)
        if not sc or not p:
            continue
        seen.append(jid)
        if sc.hard_filter_fails or sc.fit < min_fit(s) or status.get(jid, "") in DONE_STATUSES:
            continue
        h = age_hours(p, now)
        if h is None or h > FRESH_URGENT_HOURS:
            continue
        res = (send or notify.send_urgent)(
            s, f"job:{jid}", f"Fresh: {p.title} at {p.company} (fit {sc.fit})",
            f"{p.title} at {p.company}\nFit: {sc.fit}\nPosted about {h:.0f}h ago.\n{p.url or ''}\n\n{WHY['fresh']}")
        if str(res).startswith("error"):
            seen.remove(jid)  # send_urgent keeps the key unsent; retry next tick
        elif res == "sent":
            sent.append(jid)
    notify._save(s, fresh_seen=seen)
    return sent


def overdue_reach_outs(s: Settings, today: date | None = None) -> int:
    today = today or date.today()
    n = 0
    for it in Tracker(settings=s).list_action_items(open_only=True):
        if str(it.get("Detail") or "").split("\n")[0] != "reach_out":
            continue
        d = str(it.get("Due") or "")[:10]
        if d and d < today.isoformat():
            n += 1
    return n


def raise_reach_first(s: Settings, today: date | None = None) -> list[str]:
    """REQ-163: one soft Action Item "Reach out before applying to more" while overdue reach-outs exceed
    `outreach.max_overdue`; closed when they drop back. Never blocks anything."""
    from careeros.tracker import add_action

    today = today or date.today()
    n, tr = overdue_reach_outs(s, today), Tracker(settings=s)
    iid = hashlib.sha1(REACH_FIRST.encode()).hexdigest()[:8]
    mine = [i for i in tr.list_action_items(open_only=False) if str(i.get("ID")) == iid]
    is_open = any(str(i.get("Done") or "N").upper() != "Y" for i in mine)
    if n <= max_overdue(s):
        if is_open:
            tr.mark_action_done(iid, note="Closed: reach-outs are back under the limit.")
        return []
    if is_open:
        return []
    if mine:  # closed earlier, over the limit again: reopen the same item
        tr.reopen_action(iid)
        return [f"Reopened: reach out before applying to more ({n} overdue)."]
    return [add_action(s, f"Reach out before applying to more: {n} reach-outs are overdue.", "follow_up",
                       detail=REACH_FIRST, priority="H", due=today.isoformat(), due_reason=WHY[REACH_FIRST], id=iid)]


# ---- outreach QA gate + "your line" + one-click compose -------------------------------------------------------
def _words(t: str) -> int:
    return len(re.findall(r"\S+", t))


# a short sign-off line only ("Thank you,", "Best regards,"); a long paragraph that opens with "Thanks" is message
SIGN_OFF = re.compile(r"\n\n(thank you|thanks|best|regards|cheers|sincerely)\b[^\n]{0,30}(?=\n)", re.I)


def message_text(body: str) -> str:
    """The body without the sign-off block (name, phone, LinkedIn), which the word limit does not count."""
    m = list(SIGN_OFF.finditer(body + "\n"))
    return body[:m[-1].start()] if m else body


def draft_problems(d: dict[str, Any], banned: list[str]) -> list[str]:
    """Deterministic gate for one outreach draft. [] = passes."""
    em = d.get("email") if isinstance(d.get("email"), dict) else {}
    body = str(em.get("body") or d.get("linkedin_message") or "")
    out = []
    if not body.strip():
        out.append("no message text")
    n = _words(message_text(body))
    if n > MAX_WORDS:
        out.append(f"too long: {n} words, limit {MAX_WORDS}")
    low = body.lower()
    out += [f"banned phrase: {b}" for b in banned if b and b.lower() in low]
    facts = [f for f in d.get("facts_used") or [] if isinstance(f, dict) and str(f.get("fact") or "").strip()]
    if not facts and not str(d.get("fact_source") or "").strip():
        out.append("no sourced fact (facts_used) from the posting or company")
    if not (d.get("bullet_ids") or d.get("narrative_ids") or str(d.get("shared_network") or "").strip()):
        out.append("no profile bullet id")
    if "**" in body:
        out.append("markdown bold in message")
    return out


def draft_ready(d: dict[str, Any]) -> bool:
    """Ready = passes the gate AND the candidate wrote their own line."""
    return d.get("qa_pass") is True and bool(str(d.get("your_line") or "").strip())


def gate_outreach(data: dict[str, Any], banned: list[str]) -> list[str]:
    """Stamps `qa_pass`, `qa_problems`, `ready` on every draft (and ensures an empty `your_line`). Returns problems."""
    allp = []
    for d in data.get("drafts") or []:
        if not isinstance(d, dict):
            continue
        d.setdefault("your_line", "")
        probs = draft_problems(d, banned)
        d.update(qa_pass=not probs, qa_problems=probs)
        d["ready"] = draft_ready(d)
        allp += [f"{d.get('contact') or '?'}: {x}" for x in probs]
    return allp


def final_body(d: dict[str, Any]) -> str:
    """The email body as sent: the candidate's own line (if any) after the greeting ("Hi Sam,"), never above it."""
    em = d.get("email") if isinstance(d.get("email"), dict) else {}
    line, body = str(d.get("your_line") or "").strip(), str(em.get("body") or "")
    if line and line not in body:
        head, sep, rest = body.partition("\n\n")
        body = f"{head}\n\n{line}\n\n{rest}" if sep and head.rstrip().endswith(",") else f"{line}\n\n{body}"
    return body


def compose_url(d: dict[str, Any], mail: bool = False) -> str | None:
    """Gmail compose link prefilled with the draft's own to/subject/body plus the candidate's line. Only for a
    ready email draft; the candidate reads it and presses send. `mail=True`: a mailto: link for the phone's mail
    app (iPhone; the Claude app only taps https/mailto links, and Gmail's mobile web drops the prefill)."""
    em = d.get("email") if isinstance(d.get("email"), dict) else None
    to = d.get("to") or (em or {}).get("to")
    if not em or not d.get("ready") or not to:
        return None
    body = final_body(d)
    if mail:
        return f"mailto:{quote(str(to))}?subject={quote(str(em.get('subject') or ''))}&body={quote(body)}"
    return ("https://mail.google.com/mail/?view=cm&fs=1&to=" + quote(str(to)) + "&su=" + quote(str(em.get("subject") or ""))
            + "&body=" + quote(body))


def send_kit(job_id: str, title: str, out: dict[str, Any], contacts: dict[str, Any]) -> str:
    """Markdown the candidate sends from in a few clicks: per unsent draft, a LinkedIn link (their profile, a
    people search for the named person, or the role's search URL; career-os never opens LinkedIn itself), the note
    in a copy block, the prefilled Gmail link when the draft is ready, and the command that records the send."""
    company = str(out.get("company") or contacts.get("company") or "")
    urls = contacts.get("search_urls") or {}
    blocks = []
    for d in out.get("drafts") or []:
        if not isinstance(d, dict) or d.get("sent"):
            continue
        who = str(d.get("contact") or "")
        named = who and "unnamed" not in who.lower()
        li = d.get("linkedin") or (
            "https://www.linkedin.com/search/results/people/?keywords=" + quote(f"{who} {company}") if named
            else urls.get(str(d.get("role") or "recruiter")) or urls.get("recruiter"))
        lines = [f"### {company}, {title}: {who}"]
        if d.get("manual_tailor"):
            lines.append(f"Tailor by hand before sending ({d.get('manual_reason') or 'you know this person'}).")
        connected = d.get("linkedin_degree") == 1 or d.get("role") == "referral" or not d.get("linkedin_note")
        text, how = ((d.get("linkedin_message"), "Message") if connected else (d.get("linkedin_note"), "Connect, Add a note"))
        if text:
            lines += [f"1. [Find on LinkedIn]({li}), {how}, paste:" if li else "1. LinkedIn, paste:",
                      "```", str(text).strip(), "```"]
        url = compose_url(d)
        lines.append(f"2. Open the email prefilled: [Mail]({compose_url(d, mail=True)}) on iPhone, [Gmail]({url}) on a "
                     "computer. Attach your résumé, read, then Send" if url else
                     f"2. Email: needs your line first: `careeros outreach qa {job_id} --contact \"{who}\" --line \"...\"`")
        lines.append(f"3. Sent? `careeros outreach sent {job_id} --contact \"{who}\"`")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
