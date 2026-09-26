"""`pipeline.yaml: schedule` and the pure tick planner.

launchd calls `careeros tick` every `tick_minutes`. For each job (scout, score, prepare, prune) the planner
decides, from the last run and `now`:

Each job runs either every N hours / days (`every_hours`, `every_days`) or at times of day (`at: ["01:00"]`,
local time). A time-of-day job never fires on the very first tick: its reference point is its last run, else the
last tick, else now, and it runs once for the latest slot after that point.

- not_due      the interval has not passed / no slot since the last run
- run          due; runs now
- wait_quiet   due, but a claude-using job (score, prepare) and `now` is inside quiet_hours: it runs when they end
- missed       due while the Mac was asleep or off (the gap since the last tick is over missed_after_minutes)
               and more than missed_after_minutes late: it does NOT run. Every missed slot collapses into ONE
               pending catch-up record; the candidate starts it with `careeros run catch-up`
- skip_paused  due while runs are paused (`careeros run pause`): skipped, not stored up for later
- disabled     `enabled: false`

A slot that falls inside quiet hours counts from the end of the quiet window, so a deferred slot is never
"missed" just because quiet hours held it. Times are local (`timezone: local`) unless an IANA name is given.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, tzinfo
from typing import Any

from careeros.config import ConfigError

JOB_KINDS = ("scout", "inbox_sync", "score", "prepare", "prune")
CLAUDE_KINDS = ("inbox_sync", "score", "prepare")
SCHEDULE_KEYS = ("tick_minutes", "timezone", "quiet_hours", "missed_after_minutes", "jobs", "launchd_label")
JOB_KEYS = ("enabled", "every_hours", "every_days", "at", "preset", "mcp_servers", "allowed_tools_extra")
DEFAULT_JOBS: dict[str, dict[str, Any]] = {
    "scout": {"every_hours": 3},
    # Off until the inbox-sync skill is finished. Needs the Gmail MCP logged in: a run whose init event reports it
    # needs auth (or whose skill says gmail_mcp_unavailable) stops with auth_required.
    "inbox_sync": {"at": ["08:00", "18:00"], "enabled": False, "mcp_servers": ["gmail"],
                   "allowed_tools_extra": ["ToolSearch", "mcp__claude_ai_Gmail__search_threads",
                                           "mcp__claude_ai_Gmail__get_thread"]},
    "score": {"at": ["01:00"]},
    "prepare": {"at": ["02:00"]},
    "prune": {"every_days": 7},
}
DEFAULT_QUIET = ("09:00", "18:00")
DEFAULT_LABEL = "com.careeros.tick"
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
WHERE = "config/pipeline.yaml: schedule"


@dataclass
class JobSchedule:
    kind: str
    every_minutes: float | None
    enabled: bool = True
    preset: str | None = None
    at: list[time] | None = None
    mcp_servers: list[str] = field(default_factory=list)
    allowed_tools_extra: list[str] = field(default_factory=list)

    @property
    def claude(self) -> bool:
        return self.kind in CLAUDE_KINDS


@dataclass
class ScheduleConfig:
    tick_minutes: float = 15
    tz: tzinfo | None = None                   # None = the machine's local time zone
    quiet_start: time | None = time(9)
    quiet_end: time | None = time(18)
    missed_after_minutes: float = 60
    jobs: dict[str, JobSchedule] = field(default_factory=dict)
    launchd_label: str = DEFAULT_LABEL


@dataclass
class Decision:
    kind: str
    action: str
    due_at: datetime | None = None
    slots: int = 0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "action": self.action, "due_at": self.due_at.isoformat() if self.due_at else None,
                "slots": self.slots, "detail": self.detail}


def _err(msg: str) -> ConfigError:
    return ConfigError(f"{WHERE}{msg} (see examples/config/pipeline.yaml)")


def _pos(v: Any, where: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise _err(f"{where} must be a number > 0, got {v!r}")
    return float(v)


def _hhmm(v: Any, where: str) -> time:
    m = _HHMM.match(str(v)) if isinstance(v, str) else None
    if not m:
        raise _err(f"{where} must be \"HH:MM\" (24h), got {v!r}")
    return time(int(m[1]), int(m[2]))


def _job(kind: str, raw: Any, presets: tuple[str, ...]) -> JobSchedule:
    where = f".jobs.{kind}"
    if isinstance(raw, str):
        raise _err(f"{where} is a cron string ({raw!r}); the scheduler reads "
                   f"schedule.jobs.{kind}: {{every_hours: N}} now")
    if not isinstance(raw, dict):
        raise _err(f"{where} must be a mapping like {{every_hours: 3}}")
    for k in raw:
        if k not in JOB_KEYS:
            raise _err(f"{where}: unknown key {k!r}; valid: {', '.join(JOB_KEYS)}")
    if sum(k in raw for k in ("every_hours", "every_days", "at")) != 1:
        raise _err(f"{where} needs exactly one of every_hours / every_days / at")
    at = None
    minutes = None
    if "at" in raw:
        times = raw["at"] if isinstance(raw["at"], list) else [raw["at"]]
        if not times:
            raise _err(f"{where}.at must list at least one \"HH:MM\"")
        at = sorted({_hhmm(t, f"{where}.at") for t in times})
    else:
        minutes = (_pos(raw["every_hours"], f"{where}.every_hours") * 60 if "every_hours" in raw
                   else _pos(raw["every_days"], f"{where}.every_days") * 24 * 60)
    lists = {}
    for key in ("mcp_servers", "allowed_tools_extra"):
        v = raw.get(key, [])
        if key in raw and kind not in CLAUDE_KINDS:
            raise _err(f"{where}.{key} only applies to jobs that call Claude ({', '.join(CLAUDE_KINDS)})")
        if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
            raise _err(f"{where}.{key} must be a list of names")
        lists[key] = list(v)
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise _err(f"{where}.enabled must be true or false")
    preset = raw.get("preset")
    if preset is not None:
        if kind not in CLAUDE_KINDS:
            raise _err(f"{where}.preset only applies to score and prepare")
        if preset not in presets:
            raise _err(f"{where}.preset must be one of {' | '.join(presets)}, got {preset!r}")
    return JobSchedule(kind, minutes, enabled, preset, at, **lists)


def load_schedule(settings: Any) -> ScheduleConfig:
    from careeros.runs.config import PRESET_NAMES

    raw = (getattr(settings, "pipeline", None) or {}).get("schedule")
    raw = {} if raw is None else raw
    if not isinstance(raw, dict):
        raise _err(" must be a mapping")
    crons = [k for k, v in raw.items() if k in JOB_KINDS + ("score_and_prepare", "inbox_sync", "followups")
             and isinstance(v, str)]
    if crons:
        raise _err(f": {', '.join(crons)} are old cron strings, which nothing ever read. The scheduler "
                   "(`careeros tick`) reads schedule.jobs.<scout|score|prepare|prune>: {every_hours|every_days}")
    for k in raw:
        if k not in SCHEDULE_KEYS:
            raise _err(f": unknown key {k!r}; valid: {', '.join(SCHEDULE_KEYS)}")
    c = ScheduleConfig()
    if "tick_minutes" in raw:
        c.tick_minutes = _pos(raw["tick_minutes"], ".tick_minutes")
    if "missed_after_minutes" in raw:
        c.missed_after_minutes = _pos(raw["missed_after_minutes"], ".missed_after_minutes")
    tzname = raw.get("timezone", "local")
    if tzname not in (None, "local"):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            c.tz = ZoneInfo(str(tzname))
        except (ZoneInfoNotFoundError, ValueError):
            raise _err(f".timezone {tzname!r} is not an IANA time zone (e.g. America/New_York) or local") from None
    if "quiet_hours" in raw:
        q = raw["quiet_hours"]
        if q is None:
            c.quiet_start = c.quiet_end = None
        elif isinstance(q, dict) and set(q) == {"start", "end"}:
            c.quiet_start, c.quiet_end = _hhmm(q["start"], ".quiet_hours.start"), _hhmm(q["end"], ".quiet_hours.end")
        else:
            raise _err(".quiet_hours must be {start: \"HH:MM\", end: \"HH:MM\"} or null")
    jobs = raw.get("jobs") or {}
    if not isinstance(jobs, dict):
        raise _err(".jobs must be a mapping")
    for k in jobs:
        if k not in JOB_KINDS:
            raise _err(f".jobs: unknown job {k!r}; valid: {', '.join(JOB_KINDS)}")
    for kind in JOB_KINDS:
        given = jobs.get(kind)
        # a partial block (e.g. only `enabled: true`) keeps the default timing and extras
        block = dict(DEFAULT_JOBS[kind]) if given is None else given
        if isinstance(given, dict) and not any(k in given for k in ("every_hours", "every_days", "at")):
            block = {**DEFAULT_JOBS[kind], **given}
        elif isinstance(given, dict) and kind == "inbox_sync":
            block = {**{k: v for k, v in DEFAULT_JOBS[kind].items() if k in ("mcp_servers", "allowed_tools_extra")},
                     **given}
        c.jobs[kind] = _job(kind, block, PRESET_NAMES)
    label = raw.get("launchd_label", DEFAULT_LABEL)
    if not isinstance(label, str) or not re.match(r"^[A-Za-z0-9._-]+$", label):
        raise _err(f".launchd_label must be a reverse-DNS name like {DEFAULT_LABEL}")
    c.launchd_label = label
    return c


# --- time helpers -------------------------------------------------------------------------------------------

def in_quiet(t: time, start: time | None, end: time | None) -> bool:
    if start is None or end is None or start == end:
        return False
    return start <= t < end if start < end else (t >= start or t < end)


def quiet_end_after(dt: datetime, start: time | None, end: time | None) -> datetime:
    """`dt` if it is outside quiet hours, else the moment they end (same tz as `dt`)."""
    if not in_quiet(dt.timetz().replace(tzinfo=None), start, end):
        return dt
    candidate = dt.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)  # type: ignore[union-attr]
    return candidate if candidate > dt else candidate + timedelta(days=1)


def _parse(v: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def _local(dt: datetime, tz: tzinfo | None) -> datetime:
    return dt.astimezone(tz) if tz else dt.astimezone()


def effective_due(cfg: ScheduleConfig, job: JobSchedule, due: datetime) -> datetime:
    if not job.claude:
        return due
    return quiet_end_after(_local(due, cfg.tz), cfg.quiet_start, cfg.quiet_end)


# --- planning ------------------------------------------------------------------------------------------------

def _slots(cfg: ScheduleConfig, job: JobSchedule, start: datetime, end: datetime) -> list[datetime]:
    """Time-of-day slots t with start < t <= end (aware datetimes, the schedule's time zone)."""
    ls, le = _local(start, cfg.tz), _local(end, cfg.tz)
    out = []
    day = ls.date() - timedelta(days=1)
    while day <= le.date():
        for t in job.at or []:
            dt = datetime.combine(day, t, tzinfo=ls.tzinfo)
            if ls < dt <= le:
                out.append(dt)
        day += timedelta(days=1)
    return sorted(out)


def _next_slot(cfg: ScheduleConfig, job: JobSchedule, after: datetime) -> datetime:
    return _slots(cfg, job, after, after + timedelta(days=2))[0]


def _reference(state: dict[str, Any], kind: str, now: datetime) -> tuple[datetime | None, datetime]:
    last = _parse(((state or {}).get("jobs") or {}).get(kind, {}).get("last_run"))
    return last, last or _parse((state or {}).get("last_tick")) or now


def plan_tick(cfg: ScheduleConfig, state: dict[str, Any], now: datetime, paused: bool) -> list[Decision]:
    last_tick = _parse((state or {}).get("last_tick"))
    miss = timedelta(minutes=cfg.missed_after_minutes)
    asleep = last_tick is not None and now - last_tick > miss
    out = []
    for kind in JOB_KINDS:
        job = cfg.jobs[kind]
        if not job.enabled:
            out.append(Decision(kind, "disabled"))
            continue
        last, ref = _reference(state, kind, now)
        if job.at:
            passed = _slots(cfg, job, ref, now)
            if not passed:
                out.append(Decision(kind, "not_due", _next_slot(cfg, job, now)))
                continue
            due, n_slots = passed[-1], len(passed)
            eff = effective_due(cfg, job, due)
        else:
            every = timedelta(minutes=job.every_minutes or 0)
            due = last + every if last else now
            if now < due:
                out.append(Decision(kind, "not_due", due))
                continue
            eff = effective_due(cfg, job, due)
            n_slots = int(math.floor((now - eff) / every)) + 1
        if asleep and eff < now - miss:
            out.append(Decision(kind, "missed", eff, n_slots, f"{n_slots} slot(s) since {eff.isoformat()}"))
        elif paused:
            out.append(Decision(kind, "skip_paused", eff))
        elif job.claude and in_quiet(_local(now, cfg.tz).timetz().replace(tzinfo=None), cfg.quiet_start, cfg.quiet_end):
            out.append(Decision(kind, "wait_quiet", eff, detail=f"quiet hours until {eff.isoformat()}"))
        else:
            out.append(Decision(kind, "run", eff))
    return out


def merge_catch_up(record: dict[str, Any] | None, decisions: list[Decision], now: datetime) -> dict[str, Any] | None:
    """Fold `missed` decisions into the single pending catch-up record (None when there is nothing)."""
    missed = [d for d in decisions if d.action == "missed"]
    if not missed:
        return record
    rec = dict(record or {"created_at": now.isoformat(), "kinds": {}})
    kinds = {k: dict(v) for k, v in (rec.get("kinds") or {}).items()}
    for d in missed:
        e = kinds.setdefault(d.kind, {"first_missed": d.due_at.isoformat() if d.due_at else None, "slots": 0})
        e["slots"] = int(e.get("slots", 0)) + d.slots
        e["last_missed"] = now.isoformat()
    rec["kinds"], rec["updated_at"] = kinds, now.isoformat()
    return rec


def next_runs(cfg: ScheduleConfig, state: dict[str, Any], now: datetime) -> dict[str, datetime | None]:
    """When each enabled job runs next (quiet hours applied to claude jobs); None when disabled."""
    out: dict[str, datetime | None] = {}
    for kind in JOB_KINDS:
        job = cfg.jobs[kind]
        if not job.enabled:
            out[kind] = None
            continue
        last, ref = _reference(state, kind, now)
        if job.at:
            due = now if _slots(cfg, job, ref, now) else _next_slot(cfg, job, now)
        else:
            due = max(last + timedelta(minutes=job.every_minutes or 0), now) if last else now
        eff = effective_due(cfg, job, due)
        out[kind] = eff.astimezone(now.tzinfo) if now.tzinfo else eff
    return out
