"""Email digest to the candidate's OWN address (REQ-155, DEC-026). Never mails anyone else. The SMTP app password
lives only in the macOS Keychain (service `careeros-smtp`, account = the address); it is read at send time and never
written to a file, log or argv we control. Sender and keychain are injectable so tests touch neither."""
from __future__ import annotations

import json
import smtplib
import subprocess
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
            "urgent": bool(c.get("urgent", True))}


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


def smtp_send(cfg: dict[str, Any], subject: str, body: str, password: str) -> None:
    msg = EmailMessage()
    msg["From"] = msg["To"] = cfg["email"]
    msg["Subject"] = subject
    msg.set_content(body)
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


def build_digest(s: Settings, today: date | None = None) -> str | None:
    """Plain-text body, or None when every section is empty."""
    today = today or date.today()
    tr, store = Tracker(settings=s), Store(s)
    jobs = {str(j["JobID"]): j for j in tr.list_jobs()}
    items = tr.list_action_items(open_only=True)

    def line(it: dict[str, Any], with_days: bool) -> str:
        p = store.load_posting(str(it.get("JobID") or "")) if it.get("JobID") else None
        if p:
            head = f"{p.title} @ {p.company}" + (f" - {p.url}" if p.url else "")
        else:
            head = str(it.get("What to do") or "")
        since = _waiting_since(it, jobs, store) if with_days else None
        return f"- {head} ({_days(max(0, (today - since).days))})" if since else f"- {head}"

    def prio(it: dict[str, Any]) -> bool:
        return str(it.get("Priority") or "").upper() == "H" and it.get("Type") != FOLLOW

    from careeros.high_odds import REACH_FIRST, WHY

    first = [i for i in items if _kind(i) == REACH_FIRST]
    sections = [("Reach out before applying to more", [f"- {i.get('What to do')}\n  {WHY[REACH_FIRST]}" for i in first]),
                ("Reach out (overdue)", [line(i, True) for i in items if _kind(i) == REACH]
                 + ([f"  {WHY['reach_out']}"] if any(_kind(i) == REACH for i in items) else [])),
                ("Follow up", [line(i, True) for i in items if i.get("Type") == FOLLOW and _kind(i) not in (REACH, REACH_FIRST)]),
                ("Needs you", [f"- {i.get('What to do')}" for i in items if prio(i)])]
    sections += _extra_sections(s, today, store)
    out = [f"{h}\n" + "\n".join(rows) for h, rows in sections if rows]
    return "\n\n".join(out) if out else None


def _extra_sections(s: Settings, today: date, store: Store) -> list[tuple[str, list[str]]]:
    """REQ-159 watch jobs not yet digested, REQ-160 heads-up before a high/peak season (once per window and year)."""
    rows = []
    for jid in _state(s).get("watch_pending") or []:
        p = store.load_posting(jid)
        sc = store.load_score(jid)
        if p:
            rows.append(f"- {p.title} @ {p.company}" + (f" (fit {sc.fit})" if sc else "") + (f" - {p.url}" if p.url else ""))
    out = [("New at your target companies", rows)]
    up = _heads_up(s, today)
    if up:
        out.append(("Coming up", [f"- {up['name']} starts {up['starts']} ({up['level']}). {up['advice']}"]))
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
    """`now` is naive local time. `notify.digest`: daily (default) | weekly (on `weekly_day`) | off. Once per send
    day, first call at/after `send_at`. Returns a status word; any failure is `error: ...` and the next tick
    retries (nothing is recorded as sent)."""
    c = config(s)
    if not c["enabled"] or c["digest"] == "off":
        return "disabled"
    if not c["email"]:
        return "no_email"
    today = now.date()
    if c["digest"] == "weekly" and _DAYS[today.weekday()] != c["weekly_day"]:
        return "not_today"
    if _state(s).get("last_sent") == today.isoformat():
        return "already_sent"
    if now.strftime("%H:%M") < c["send_at"]:
        return "too_early"
    try:
        body = build_digest(s, today)
        if body is None:
            return "empty"
        (sender or smtp_send)(c, "career-os: what needs you today", body, (keychain or keychain_password)(c["email"]))
        up = _heads_up(s, today)
        _save(s, last_sent=today.isoformat(), watch_pending=[],
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
