"""Email digest to the candidate's OWN address (REQ-155, DEC-026). Never mails anyone else. The SMTP app password
lives only in the macOS Keychain (service `careeros-smtp`, account = the address); it is read at send time and never
written to a file, log or argv we control. Sender and keychain are injectable so tests touch neither."""
from __future__ import annotations

import html as _html
import json
import smtplib
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from typing import Any, Callable

from careeros.config import Settings
from careeros.follow_ups import APPLIED, OUTREACH, REACH, TYPE as FOLLOW
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
    if kind == REACH:
        return _day(it.get("Due")) or _day(it.get("Created"))
    if kind == OUTREACH:
        return _outreach_wait(store, jid)
    if kind == APPLIED:
        return _day((jobs.get(jid) or {}).get("DateApplied"))
    return _day(it.get("Created"))


@dataclass
class Row:
    title: str
    sub: str = ""        # company, or the action's second half
    url: str = ""
    note: str = ""       # "fit 87 - ready", "3 days", "in 2 days"
    ready: bool = False


@dataclass
class Section:
    key: str
    heading: str
    rows: list[Row] = field(default_factory=list)
    note: str = ""
    ids: list[str] = field(default_factory=list)   # job ids listed (apply section): remembered so they are not repeated


_PRE_APPLY = ("found", "scored", "queued", "prepared", "needs_review")
_APPLY = ("queued", "prepared")


def _job_row(p: Any, note: str = "", ready: bool = False) -> Row:
    return Row(p.title, p.company, p.url, note, ready)


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
    top = cands[:c["apply_max"]]
    rows = [_job_row(p, f"{'new - ' if new else ''}fit {fit}", _ready(store, jid)) for new, fit, _, jid, p in top]
    note = f"showing {len(top)} of {len(cands)}: new first, then best fit" if len(cands) > len(top) else ""
    return Section("apply", "Apply to these", rows, note, [jid for _, _, _, jid, _ in top])


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
            found.append((d, Row(str(it.get("What to do") or ""), "", "", f"{why + ': ' if why else ''}{_in_days((d - today).days)}")))
    return Section("deadlines", "Deadlines", [r for _, r in sorted(found, key=lambda x: x[0])])


def build_sections(s: Settings, today: date | None = None) -> list[Section]:
    """Non-empty sections in email order: follow up, deadlines, apply, needs you, then the older ones."""
    today = today or date.today()
    c = config(s)
    tr, store = Tracker(settings=s), Store(s)
    jobs = {str(j["JobID"]): j for j in tr.list_jobs()}
    items = tr.list_action_items(open_only=True)

    def row(it: dict[str, Any], with_days: bool) -> Row:
        p = store.load_posting(str(it.get("JobID") or "")) if it.get("JobID") else None
        since = _waiting_since(it, jobs, store) if with_days else None
        note = _days(max(0, (today - since).days)) if since else ""
        return Row(p.title, p.company, p.url, note) if p else Row(str(it.get("What to do") or ""), note=note)

    def prio(it: dict[str, Any]) -> bool:
        return str(it.get("Priority") or "").upper() == "H" and it.get("Type") != FOLLOW

    from careeros.high_odds import REACH_FIRST, WHY

    reach = [i for i in items if _kind(i) == REACH]
    apply = _apply_section(s, c, jobs, store, today)
    secs = [Section("follow", "Follow up", [row(i, True) for i in items if i.get("Type") == FOLLOW
                                            and _kind(i) not in (REACH, REACH_FIRST)]),
            _deadline_section(c, jobs, items, store, today), apply,
            Section("needs", "Needs you", [Row(str(i.get("What to do"))) for i in items if prio(i)]),
            Section("reach_first", "Reach out before applying to more",
                    [Row(str(i.get("What to do"))) for i in items if _kind(i) == REACH_FIRST], WHY[REACH_FIRST]),
            Section("reach", "Reach out (overdue)", [row(i, True) for i in reach], WHY["reach_out"] if reach else "")]
    secs += _extra_sections(s, today, store)
    return [x for x in secs if x.rows]


def render_text(secs: list[Section]) -> str:
    def line(r: Row) -> str:
        return f"- {r.title}" + (f" @ {r.sub}" if r.sub else "") + (f" - {r.url}" if r.url else "") \
            + (f" ({r.note}{', ready' if r.ready else ''})" if r.note or r.ready else "")

    return "\n\n".join(f"{x.heading}\n" + (f"  {x.note}\n" if x.note else "") + "\n".join(line(r) for r in x.rows)
                       for x in secs)


def build_digest(s: Settings, today: date | None = None) -> str | None:
    """Plain-text body, or None when every section is empty."""
    secs = build_sections(s, today)
    return render_text(secs) if secs else None


_LABEL = {"apply": ("job to apply to", "jobs to apply to"), "follow": ("follow-up", "follow-ups"),
          "deadlines": ("deadline", "deadlines"), "needs": ("needs you", "need you")}


def counts(secs: list[Section]) -> list[tuple[int, str]]:
    """(n, label) per headline section, in email order: 6 jobs to apply to, 3 follow-ups, ..."""
    out = []
    for key in ("follow", "deadlines", "apply", "needs"):
        n = next((len(x.rows) for x in secs if x.key == key), 0)
        if n:
            one, many = _LABEL[key]
            out.append((n, one if n == 1 else many))
    return out


def subject_for(secs: list[Section]) -> str:
    order = {"jobs to apply to": 0, "job to apply to": 0, "follow-up": 1, "follow-ups": 1, "deadline": 2, "deadlines": 2}
    cs = sorted(counts(secs), key=lambda x: order.get(x[1], 3))[:3]
    return "career-os: " + ", ".join(f"{n} {w}" for n, w in cs) if cs else "career-os: what needs you today"


def render_html(secs: list[Section], today: date | None = None) -> str:
    """Email-safe: tables, inline CSS, no images/fonts/scripts, 600px column, dark-mode overrides in <style>."""
    e = _html.escape
    today = today or date.today()
    head = " &middot; ".join(f"<strong>{n}</strong> {e(w)}" for n, w in counts(secs)) or "Nothing urgent"
    body = ""
    for x in secs:
        body += (f'<tr><td class="h" style="padding:20px 0 6px;font-size:13px;font-weight:700;letter-spacing:.04em;'
                 f'text-transform:uppercase;color:#475569">{e(x.heading)}</td></tr>')
        if x.note:
            body += f'<tr><td class="m" style="padding:0 0 6px;font-size:13px;color:#64748b">{e(x.note)}</td></tr>'
        for r in x.rows:
            t = e(r.title)
            if r.url.startswith(("https://", "http://")):
                t = f'<a href="{e(r.url, quote=True)}" class="a" style="color:#1d4ed8;text-decoration:underline">{t}</a>'
            meta = " &middot; ".join(e(v) for v in (r.sub, r.note) if v)
            tag = (' <span class="r" style="display:inline-block;padding:1px 6px;border-radius:9px;background:#dcfce7;'
                   'color:#166534;font-size:11px;font-weight:600">ready</span>' if r.ready else "")
            body += (f'<tr><td class="row" style="padding:9px 0;border-top:1px solid #e2e8f0;font-size:15px;line-height:1.4;'
                     f'color:#0f172a">{t}{tag}'
                     + (f'<br><span class="m" style="font-size:13px;color:#64748b">{meta}</span>' if meta else "")
                     + "</td></tr>")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">'
        "<title>career-os digest</title><style>"
        "@media (prefers-color-scheme: dark){body,.bg{background:#0b1220 !important}.card{background:#111a2e !important}"
        ".row{color:#e5e7eb !important;border-color:#26334d !important}.h{color:#94a3b8 !important}.m{color:#94a3b8 !important}"
        ".a{color:#93c5fd !important}.t{color:#f8fafc !important}.r{background:#14532d !important;color:#bbf7d0 !important}}"
        "@media (max-width:620px){.card{padding:16px !important}}</style></head>"
        '<body class="bg" style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="bg" style="background:#f1f5f9"><tr>'
        '<td align="center" style="padding:16px 8px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%"><tr>'
        '<td class="card" style="background:#ffffff;border-radius:10px;padding:24px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td class="t" style="font-size:18px;line-height:1.35;color:#0f172a">{head}</td></tr>'
        f'<tr><td class="m" style="padding-top:2px;font-size:13px;color:#64748b">{e(today.strftime("%a %d %b %Y"))}</td></tr>'
        f"{body}</table></td></tr></table></td></tr></table></body></html>")


def _extra_sections(s: Settings, today: date, store: Store) -> list[Section]:
    """REQ-159 watch jobs not yet digested, REQ-160 heads-up before a high/peak season (once per window and year)."""
    rows = []
    for jid in _state(s).get("watch_pending") or []:
        p = store.load_posting(jid)
        sc = store.load_score(jid)
        if p:
            rows.append(_job_row(p, f"fit {sc.fit}" if sc else ""))
    out = [Section("watch", "New at your target companies", rows)]
    up = _heads_up(s, today)
    if up:
        out.append(Section("season", "Coming up", [Row(f"{up['name']} starts {up['starts']} ({up['level']}). {up['advice']}")]))
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
        (sender or smtp_send)(c, subject_for(secs), render_text(secs), (keychain or keychain_password)(c["email"]),
                              html=render_html(secs, today))
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
