"""Email digest to the candidate's OWN address (REQ-155, DEC-026). Never mails anyone else. The SMTP app password
lives only in the macOS Keychain (service `careeros-smtp`, account = the address); it is read at send time and never
written to a file, log or argv we control. Sender and keychain are injectable so tests touch neither."""
from __future__ import annotations

import colorsys
import hashlib
import html as _html
import json
import re
import smtplib
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from typing import Any, Callable

from careeros.config import Settings
from careeros.follow_ups import APPLIED, OUTREACH, OUTREACH14, REACH, TYPE as FOLLOW, _outreach_wait
from careeros.high_odds import REACH_FIRST, WHY
from careeros.runs.store import RunStore
from careeros.store import Store
from careeros.tracker import Tracker

SERVICE = "careeros-smtp"


class NotifyError(RuntimeError):
    pass


def config(s: Settings) -> dict[str, Any]:
    c = s.pipeline.get("notify") or {}
    return {"enabled": bool(c.get("enabled", False)), "email": c.get("email") or None,
            "send_at": str(c.get("send_at") or "08:00"), "smtp_host": c.get("smtp_host") or "smtp.gmail.com",
            "smtp_port": int(c.get("smtp_port") or 587),
            "digest": str(c.get("digest") or "daily").lower(), "weekly_day": str(c.get("weekly_day") or "mon")[:3].lower(),
            "urgent": bool(c.get("urgent", True)),
            "every_days": max(0, int(c.get("every_days") or 0)),
            "apply_max": max(1, int(c.get("apply_max") or 10)),
            "section_max": max(1, int(c.get("section_max") or 5)),
            "deadline_days": max(0, int(c.get("deadline_days") if c.get("deadline_days") is not None else 7))}


def keychain_password(email: str) -> str:
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", email, "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise NotifyError("no app password in the Keychain; run `careeros notify setup`")
    return r.stdout.strip()


def store_password(email: str) -> None:
    """`security` prompts for the password itself on the terminal: it never passes through this process or argv."""
    r = subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", email, "-w"])
    if r.returncode != 0:
        raise NotifyError("could not save the password to the Keychain")


def smtp_send(cfg: dict[str, Any], subject: str, body: str, password: str, html: str | None = None) -> None:
    msg = EmailMessage()
    msg["From"] = msg["To"] = cfg["email"]
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30) as sm:
        sm.starttls()
        sm.login(cfg["email"], password)
        sm.send_message(msg)


def _day(v: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(v)[:10]).date() if v else None
    except ValueError:
        return None


def _days(n: int) -> str:
    return f"{n} day" + ("" if n == 1 else "s")


def _kind(it: dict[str, Any]) -> str:
    return str(it.get("Detail") or "").split("\n")[0] if it.get("Type") == FOLLOW else ""


def _waiting_since(it: dict[str, Any], jobs: dict[str, dict[str, Any]], store: Store) -> date | None:
    from careeros.follow_ups import _outreach_wait

    jid, kind = str(it.get("JobID") or ""), _kind(it)
    if kind == REACH:   # the item is due the day it is raised, so count from the application, not the item
        return _day((jobs.get(jid) or {}).get("DateApplied")) or _day(it.get("Due")) or _day(it.get("Created"))
    if kind == OUTREACH:
        return _outreach_wait(store, jid)
    if kind == APPLIED:
        return _day((jobs.get(jid) or {}).get("DateApplied"))
    return _day(it.get("Created"))


@dataclass
class Row:
    title: str
    company: str = ""    # set = a job row (badge with initials, "Company · Location" line)
    location: str = ""
    url: str = ""
    note: str = ""       # status line: "Emailed Tom · 2 days, no reply"
    chips: list[str] = field(default_factory=list)   # small grey pills: "fit 87", "new", "ready", "closes in 3 days"
    icon: str = ""       # badge symbol for a non-job row


@dataclass
class Section:
    key: str
    heading: str
    rows: list[Row] = field(default_factory=list)
    note: str = ""
    ids: list[str] = field(default_factory=list)   # job ids listed (apply section): remembered so they are not repeated
    count: int = -1      # headline count (all of them, before the row cap); -1 = len(rows)
    more: int = 0        # rows hidden by `notify.section_max`


_PRE_APPLY = ("found", "scored", "queued", "prepared", "needs_review")
_APPLY = ("queued", "prepared")


def _place(p: Any) -> str:
    loc = (p.location or "").strip()
    if len(loc) > 40:   # multi-office strings: first place only
        loc = ", ".join(re.split(r"\s*[;|]\s*", loc)[0].split(", ")[:2]) + " and more"
    if p.remote and "remote" not in loc.lower():
        return f"{loc} (remote)" if loc else "Remote"
    return loc


def _job_row(p: Any, *chips: str, note: str = "") -> Row:
    return Row(p.title, p.company, _place(p), p.url, note, [c for c in chips if c])


def _cap(sec: Section, n: int) -> Section:
    if sec.count < 0:
        sec.count = len(sec.rows)
    sec.more = max(0, len(sec.rows) - n)
    sec.rows = sec.rows[:n]
    return sec


def _short(text: str, n: int = 90) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= n else one[:n - 1].rsplit(" ", 1)[0].rstrip(".,;:- ") + "\u2026"


def _ready(store: Store, jid: str) -> bool:
    """qa-review's qa.json passed: top-level `pass: true`, or every legacy `results` entry passed."""
    try:
        d = json.loads((store.job_dir(jid) / "qa.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(d, dict):
        return False
    if "pass" in d:
        return d["pass"] is True
    qa = store.load_qa(jid)
    return bool(qa) and all(r.passed for r in qa)


def _in_days(n: int) -> str:
    return "today" if n == 0 else f"in {_days(n)}" if n > 0 else f"{_days(-n)} overdue"


def _apply_section(s: Settings, c: dict[str, Any], jobs: dict[str, dict[str, Any]], store: Store, today: date) -> Section:
    """Jobs from any source worth applying to (queued/prepared, still open) until you apply: ones not in an earlier
    digest first ("new"), then best fit. `ids` = every job listed, so the next digest knows what is new."""
    shown = set(_state(s).get("apply_shown") or [])
    cands = []
    for jid, j in jobs.items():
        p = store.load_posting(jid) if str(j.get("Status")) in _APPLY else None
        if p is None or (_day(p.closes_at) and _day(p.closes_at) < today):
            continue
        cands.append((jid not in shown, int(j.get("Fit") or 0), str(j.get("DateFound") or ""), jid, p))
    cands.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)   # new first, then best fit, then newest
    top = cands[:min(c["apply_max"], c["section_max"])]
    rows = [_job_row(p, f"fit {fit}" if fit else "", "new" if new else "", "ready" if _ready(store, jid) else "") for new, fit, _, jid, p in top]
    return Section("apply", "Apply to these", rows, "", [jid for _, _, _, jid, _ in top], len(cands), len(cands) - len(top))


def _deadline_section(c: dict[str, Any], jobs: dict[str, dict[str, Any]], items: list[dict[str, Any]], store: Store,
                      today: date) -> Section:
    found: list[tuple[date, Row]] = []
    for jid, j in jobs.items():
        p = store.load_posting(jid) if str(j.get("Status")) in _PRE_APPLY else None
        d = _day(p.closes_at) if p else None
        if p and d and 0 <= (d - today).days <= c["deadline_days"]:
            found.append((d, _job_row(p, f"closes {_in_days((d - today).days)}")))
    for it in items:
        d = _day(it.get("Due"))
        if d and it.get("Type") != FOLLOW and (d - today).days <= c["deadline_days"]:
            why = str(it.get("Due reason") or "")
            found.append((d, Row(_short(it.get("What to do") or ""), chips=[f"{why + ': ' if why else ''}{_in_days((d - today).days)}"],
                                 icon="!")))
    return _cap(Section("deadlines", "Deadlines", [r for _, r in sorted(found, key=lambda x: x[0])]), c["section_max"])


def _sent_drafts(store: Store, jid: str) -> list[dict[str, Any]]:
    from careeros.follow_ups import _json

    return [x for x in _json(store.job_dir(jid) / "outreach.json").get("drafts") or []
            if isinstance(x, dict) and x.get("sent") is True and not x.get("replied")]


def _follow_rows(items: list[dict[str, Any]], jobs: dict[str, dict[str, Any]], store: Store, today: date,
                 ) -> tuple[list[Row], set[str]]:
    """One row per job: the applied nudge and the outreach nudge of a job merge. Outreach rows first, then
    applied-only, longest wait first. Returns the rows and the job ids they cover."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for n, it in enumerate(i for i in items if i.get("Type") == FOLLOW and _kind(i) not in (REACH, REACH_FIRST)):
        groups.setdefault(str(it.get("JobID") or f"~{n}"), []).append(it)
    out: list[tuple[bool, int, Row]] = []
    for jid, its in groups.items():
        p = store.load_posting(jid) if not jid.startswith("~") else None
        drafts = _sent_drafts(store, jid) if p else []
        since_out = _outreach_wait(store, jid) if p and any(_kind(i) in (OUTREACH, OUTREACH14) for i in its) else None
        since = since_out or _waiting_since(its[0], jobs, store)
        n = max(0, (today - since).days) if since else 0
        if since_out:
            names = list(dict.fromkeys(str(d["contact"]) for d in drafts if d.get("contact")))
            who = ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "") or "a contact"
            verb = "Emailed" if any(d.get("to") for d in drafts) else "Messaged"
            note = f"{verb} {who} \u00b7 {_days(n)}, no reply"
        elif since:
            note = "Applied today, no reply" if n == 0 else f"Applied {_days(n)} ago, no reply"
        else:
            note = "No reply yet"
        ready = any((d.get("followup_7d") and not d.get("followup_7d_sent_at"))
                    or (d.get("followup_14d") and not d.get("followup_14d_sent_at")) for d in drafts)
        chips = ["follow-up ready"] if ready else []
        row = _job_row(p, *chips, note=note) if p else Row(_short(its[0].get("What to do") or ""), note=note, chips=chips, icon="\u21bb")
        out.append((bool(since_out), n, row))
    out.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _, _, r in out], {j for j in groups if not j.startswith("~")}


# Needs you: one row per Type, most urgent first. (singular/plural label, badge symbol)
_NEEDS = {"scam_suspected": ("scam warning", "scam warnings", "!"),
          "review": ("application ready for your review", "applications ready for your review", "\u2713"),
          "qa_fail": ("QA failure to decide", "QA failures to decide", "\u00d7"),
          "injection_suspected": ("posting with hidden text to check", "postings with hidden text to check", "!"),
          "question": ("form question to answer", "form questions to answer", "?"),
          "ghost_job": ("possible ghost job", "possible ghost jobs", "~"),
          "other": ("other task", "other tasks", "\u2022")}


def _needs_rows(items: list[dict[str, Any]], jobs: dict[str, dict[str, Any]], store: Store) -> list[Row]:
    by: dict[str, list[dict[str, Any]]] = {}
    for i in items:
        if i.get("Type") != FOLLOW and _kind(i) != REACH_FIRST:
            by.setdefault(str(i.get("Type") or "other"), []).append(i)
    order = list(_NEEDS)
    rows = []
    for ty in sorted(by, key=lambda k: (order.index(k) if k in order else len(order), -len(by[k]))):
        its, n = by[ty], len(by[ty])
        one, many, icon = _NEEDS.get(ty) or (f"{ty.replace('_', ' ')} item", f"{ty.replace('_', ' ')} items", "\u2022")
        if n == 1:
            rows.append(Row(_short(its[0].get("What to do") or one), icon=icon))
            continue
        title = f"{n} {many}"
        if ty == "review":
            names = []
            for i in its:
                jid = str(i.get("JobID") or "")
                p = store.load_posting(jid) if jid else None
                names.append(p.company if p else str((jobs.get(jid) or {}).get("Company") or ""))
            names = list(dict.fromkeys(x for x in names if x))
            if names:
                title += ": " + ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
        rows.append(Row(title, icon=icon))
    return rows


def build_sections(s: Settings, today: date | None = None) -> list[Section]:
    """Non-empty sections in email order: follow up, deadlines, apply, needs you, then the older ones. Every
    section shows at most `notify.section_max` rows; `count` is the full number, `more` what the cap hid."""
    today = today or date.today()
    c = config(s)
    cap = c["section_max"]
    tr, store = Tracker(settings=s), Store(s)
    jobs = {str(j["JobID"]): j for j in tr.list_jobs()}
    items = tr.list_action_items(open_only=True)


    follow_rows, followed = _follow_rows(items, jobs, store, today)
    reach: list[tuple[int, Row]] = []
    for it in items:
        if _kind(it) != REACH or str(it.get("JobID") or "") in followed:
            continue
        p = store.load_posting(str(it.get("JobID") or "")) if it.get("JobID") else None
        since = _waiting_since(it, jobs, store)
        n = max(0, (today - since).days) if since else 0
        note = ("Applied today" if n == 0 else f"Applied {_days(n)} ago") + " \u00b7 no contact yet" if since else "no contact yet"
        reach.append((n, _job_row(p, note=note) if p else Row(_short(it.get("What to do") or ""), note=note, icon="@")))
    reach.sort(key=lambda x: -x[0])
    need_rows = _needs_rows(items, jobs, store)
    need_total = sum(1 for i in items if i.get("Type") != FOLLOW and _kind(i) != REACH_FIRST)
    reach_first = [Row(_short(i.get("What to do") or ""), icon="!") for i in items if _kind(i) == REACH_FIRST]
    needs = _cap(Section("needs", "Needs you", need_rows, count=need_total), min(cap, 6))
    secs = [_cap(Section("follow", "Follow up", follow_rows), cap),
            _deadline_section(c, jobs, items, store, today), _apply_section(s, c, jobs, store, today), needs,
            _cap(Section("reach_first", "Reach out before applying to more", reach_first, WHY[REACH_FIRST] if reach_first else ""), cap),
            _cap(Section("reach", "Reach out", [r for _, r in reach], WHY["reach_out"] if reach else ""), cap)]
    secs += _extra_sections(s, today, store)
    return [x for x in secs if x.rows]


def footer(c: dict[str, Any]) -> str:
    if c["every_days"]:
        return f"Sent every {c['every_days']} days by career-os. Change it in pipeline.yaml notify.every_days."
    if c["digest"] == "weekly":
        return f"Sent weekly on {c['weekly_day']} by career-os. Change it in pipeline.yaml notify.digest."
    return "Sent daily by career-os. Change it in pipeline.yaml notify.digest."


def _summary(secs: list[Section]) -> str:
    return (" \u00b7 ".join(f"{n} {w}" for n, w in counts(secs))
            or " \u00b7 ".join(f"{x.count if x.count >= 0 else len(x.rows)} {x.heading.lower()}" for x in secs) or "nothing urgent")


def render_text(secs: list[Section], today: date | None = None, footer: str = "") -> str:
    def line(r: Row) -> str:
        first = f"- {r.title}" + (f", {r.company}" if r.company else "") + (f": {r.url}" if r.url else "")
        sub = " \u00b7 ".join([x for x in (r.location, r.note) if x] + [f"[{c}]" for c in r.chips])
        return first + (f"\n  {sub}" if sub else "")

    out = ["Your job search today" + (f", {today.strftime('%a %d %b %Y')}" if today else "") + f"\n{_summary(secs)}"]
    for x in secs:
        n = x.count if x.count >= 0 else len(x.rows)
        more = f"\n+{x.more} more: open Today (`careeros ui`)" if x.more else ""
        out.append(f"{x.heading} ({n})\n" + (f"  {x.note}\n" if x.note else "") + "\n".join(line(r) for r in x.rows) + more)
    if footer:
        out.append(footer)
    return "\n\n".join(out)


def build_digest(s: Settings, today: date | None = None) -> str | None:
    """Plain-text body, or None when every section is empty."""
    today = today or date.today()
    secs = build_sections(s, today)
    return render_text(secs, today, footer(config(s))) if secs else None


_LABEL = {"apply": ("job to apply to", "jobs to apply to"), "follow": ("follow-up", "follow-ups"),
          "deadlines": ("deadline", "deadlines"), "needs": ("needs you", "need you")}


def counts(secs: list[Section]) -> list[tuple[int, str]]:
    """(n, label) per headline section, in email order: 6 jobs to apply to, 3 follow-ups, ..."""
    out = []
    for key in ("follow", "deadlines", "apply", "needs"):
        x = next((x for x in secs if x.key == key), None)
        n = (x.count if x.count >= 0 else len(x.rows)) if x else 0
        if n:
            one, many = _LABEL[key]
            out.append((n, one if n == 1 else many))
    return out


def subject_for(secs: list[Section]) -> str:
    order = {"jobs to apply to": 0, "job to apply to": 0, "follow-up": 1, "follow-ups": 1, "deadline": 2, "deadlines": 2}
    cs = sorted(counts(secs), key=lambda x: order.get(x[1], 3))[:3]
    while cs:
        subj = "career-os: " + ", ".join(f"{n} {w}" for n, w in cs)
        if len(subj) <= 60:
            return subj
        cs.pop()
    return "career-os: what needs you today"


def initials(company: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", company)
    if not words:
        return "?"
    return (words[0][0] + words[1][0] if len(words) > 1 else words[0][:2]).upper()


def badge_colour(name: str) -> str:
    """Hex colour from the company name: stable, dark enough for white text (WCAG AA) at any hue."""
    hue = int(hashlib.sha1(name.lower().encode("utf-8")).hexdigest()[:6], 16) % 360 / 360
    r, g, b = colorsys.hls_to_rgb(hue, 0.30, 0.60)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def render_html(secs: list[Section], today: date | None = None, footer: str = "") -> str:
    """Email-safe, modelled on a job-alert mail: tables, inline CSS, no images/fonts/scripts, 600px column,
    dark-mode overrides in <style>."""
    e = _html.escape
    today = today or date.today()
    body = ""
    for x in secs:
        n = x.count if x.count >= 0 else len(x.rows)
        body += (f'<tr><td class="h" style="padding:28px 0 8px;font-size:13px;font-weight:700;letter-spacing:.04em;'
                 f'text-transform:uppercase;color:#475569">{e(x.heading)} ({n})</td></tr>')
        if x.note:
            body += f'<tr><td class="m" style="padding:0 0 8px;font-size:13px;line-height:1.4;color:#64748b">{e(x.note)}</td></tr>'
        for r in x.rows:
            t = e(r.title)
            if r.url.startswith(("https://", "http://")):
                t = f'<a href="{e(r.url, quote=True)}" class="a" style="color:#1d4ed8;text-decoration:none">{t}</a>'
            if r.company:
                badge = (f'<td width="40" height="40" align="center" valign="middle" style="width:40px;height:40px;'
                         f'border-radius:8px;background:{badge_colour(r.company)};color:#ffffff;font-size:15px;'
                         f'font-weight:700">{e(initials(r.company))}</td>')
                size = "16px"
            else:
                badge = (f'<td width="40" height="40" align="center" valign="middle" class="ib" style="width:40px;height:40px;'
                         f'border-radius:20px;background:#e2e8f0;color:#475569;font-size:16px;font-weight:700">{e(r.icon or chr(8226))}</td>')
                size = "15px"
            line2 = " &middot; ".join(e(v) for v in (r.company, r.location) if v)
            chips = "".join(f'<span class="c" style="display:inline-block;margin:4px 6px 0 0;padding:2px 8px;border-radius:10px;'
                            f'background:#e2e8f0;color:#475569;font-size:12px;line-height:1.4">{e(c)}</span>' for c in r.chips)
            text = "".join([
                f'<div class="t" style="font-size:{size};font-weight:700;line-height:1.35;color:#0f172a">{t}</div>',
                f'<div class="m" style="font-size:14px;line-height:1.4;color:#475569">{line2}</div>' if line2 else "",
                f'<div class="m" style="font-size:13px;line-height:1.4;color:#64748b">{e(r.note)}</div>' if r.note else "",
                f"<div>{chips}</div>" if chips else ""])
            body += (f'<tr><td class="row" style="padding:14px 0;border-top:1px solid #e2e8f0">'
                     f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                     f'<td width="52" valign="top" style="width:52px"><table role="presentation" cellpadding="0" cellspacing="0">'
                     f'<tr>{badge}</tr></table></td><td valign="top">{text}</td></tr></table></td></tr>')
        if x.more:
            body += (f'<tr><td class="m" style="padding:6px 0 0;font-size:13px;color:#64748b">+{x.more} more: open Today '
                     f'(<code>careeros ui</code>)</td></tr>')
    foot = f'<tr><td class="m" style="padding:28px 0 0;font-size:12px;line-height:1.5;color:#64748b">{e(footer)}</td></tr>' if footer else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">'
        "<title>career-os digest</title><style>"
        "@media (prefers-color-scheme: dark){body,.bg{background:#0b1220 !important}.card{background:#111a2e !important}"
        ".row{border-color:#26334d !important}.h,.m{color:#94a3b8 !important}"
        ".a{color:#93c5fd !important}.t{color:#f8fafc !important}.c,.ib{background:#26334d !important;color:#cbd5e1 !important}}"
        "@media (max-width:620px){.card{padding:16px !important}}</style></head>"
        '<body class="bg" style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="bg" style="background:#f1f5f9"><tr>'
        '<td align="center" style="padding:16px 8px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%"><tr>'
        '<td class="card" style="background:#ffffff;border-radius:10px;padding:24px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td class="t" style="font-size:22px;font-weight:700;line-height:1.3;color:#0f172a">Your job search today</td></tr>'
        f'<tr><td class="m" style="padding-top:4px;font-size:13px;color:#64748b">{e(today.strftime("%a %d %b %Y"))}</td></tr>'
        f'<tr><td class="t" style="padding-top:8px;font-size:15px;line-height:1.4;color:#0f172a">{e(_summary(secs))}</td></tr>'
        f"{body}{foot}</table></td></tr></table></td></tr></table></body></html>")


def _extra_sections(s: Settings, today: date, store: Store) -> list[Section]:
    """REQ-159 watch jobs not yet digested, REQ-160 heads-up before a high/peak season (once per window and year)."""
    rows = []
    for jid in _state(s).get("watch_pending") or []:
        p = store.load_posting(jid)
        sc = store.load_score(jid)
        if p:
            rows.append(_job_row(p, f"fit {sc.fit}" if sc else ""))
    out = [_cap(Section("watch", "New at your target companies", rows), config(s)["section_max"])]
    up = _heads_up(s, today)
    if up:
        out.append(Section("season", "Coming up", [Row(f"{up['name']} starts {up['starts']} ({up['level']}). {up['advice']}", icon="i")]))
    return out


def _heads_up(s: Settings, today: date) -> dict[str, Any] | None:
    from careeros.runs.policy import upcoming_window

    try:
        up = upcoming_window(s.targets or {}, today)
    except Exception:  # noqa: BLE001 - a bad season config must not stop the digest
        return None
    return up if up and f"{up['name']}:{up['starts'][:4]}" not in (_state(s).get("season_pinged") or []) else None


def _state_path(s: Settings):
    return RunStore(s).dir / "notify.json"


def _state(s: Settings) -> dict[str, Any]:
    try:
        d = json.loads(_state_path(s).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(s: Settings, **upd: Any) -> None:
    p = _state_path(s)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**_state(s), **upd}), encoding="utf-8")


_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def maybe_send_digest(s: Settings, now: datetime, *, sender: Callable[..., None] | None = None,
                      keychain: Callable[[str], str] | None = None) -> str:
    """`now` is naive local time. `notify.every_days: N` (send when the last digest is N+ days old) wins over `notify.digest`: daily (default) | weekly (on `weekly_day`) | off. Once per send
    day, first call at/after `send_at`. Returns a status word; any failure is `error: ...` and the next tick
    retries (nothing is recorded as sent)."""
    c = config(s)
    if not c["enabled"] or c["digest"] == "off":
        return "disabled"
    if not c["email"]:
        return "no_email"
    today = now.date()
    last = _day(_state(s).get("last_sent"))
    if last == today:
        return "already_sent"
    if c["every_days"]:
        if last and (today - last).days < c["every_days"]:
            return "not_today"
    elif c["digest"] == "weekly" and _DAYS[today.weekday()] != c["weekly_day"]:
        return "not_today"
    if now.strftime("%H:%M") < c["send_at"]:
        return "too_early"
    try:
        secs = build_sections(s, today)
        if not secs:
            return "empty"
        (sender or smtp_send)(c, subject_for(secs), render_text(secs, today, footer(c)), (keychain or keychain_password)(c["email"]),
                              html=render_html(secs, today, footer(c)))
        up = _heads_up(s, today)
        live = {str(j["JobID"]) for j in Tracker(settings=s).list_jobs() if str(j.get("Status")) in _APPLY}
        shown = sorted(({*(_state(s).get("apply_shown") or [])} & live)    # applied/closed jobs drop out: no cap
                       | set(next((x.ids for x in secs if x.key == "apply"), [])))
        _save(s, last_sent=today.isoformat(), watch_pending=[], apply_shown=shown,
              season_pinged=[*(_state(s).get("season_pinged") or []), *([f"{up['name']}:{up['starts'][:4]}"] if up else [])])
    except Exception as e:  # noqa: BLE001 - never crash the tick; the message never contains the password
        return f"error: {type(e).__name__}: {e}"[:200]
    return "sent"


def send_urgent(s: Settings, key: str, subject: str, body: str, *, sender: Callable[..., None] | None = None,
                keychain: Callable[[str], str] | None = None) -> str:
    """Email now (call it from a tick), not waiting for the digest. One send per `key`, forever. Subject gets
    "Urgent: ". Status word like `maybe_send_digest`; failure leaves the key unsent so the next tick retries."""
    c = config(s)
    if not c["enabled"] or not c["urgent"]:
        return "disabled"
    if not c["email"]:
        return "no_email"
    sent_keys = _state(s).get("urgent") or []
    if key in sent_keys or (key.startswith("job:") and {f"watch:{key[4:]}", f"fresh:{key[4:]}"} & set(sent_keys)):
        return "already_sent"  # job:<id> is the shared key; old watch:/fresh: keys still count
    try:
        (sender or smtp_send)(c, f"Urgent: {subject}", body, (keychain or keychain_password)(c["email"]))
        _save(s, urgent=[*(_state(s).get("urgent") or []), key])
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"[:200]
    return "sent"
