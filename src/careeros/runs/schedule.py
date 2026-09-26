"""`pipeline.yaml: schedule` and the pure tick planner.

launchd calls `careeros tick` every `tick_minutes`. For each job (scout, score, prepare, prune) the planner
decides, from the last run and `now`:

- not_due      the interval has not passed
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

JOB_KINDS = ("scout", "score", "prepare", "prune")
CLAUDE_KINDS = ("score", "prepare")
SCHEDULE_KEYS = ("tick_minutes", "timezone", "quiet_hours", "missed_after_minutes", "jobs", "launchd_label")
JOB_KEYS = ("enabled", "every_hours", "every_days", "preset")
DEFAULT_JOBS: dict[str, dict[str, Any]] = {
    "scout": {"every_hours": 3},
    "score": {"every_hours": 6},
    "prepare": {"every_hours": 12},
    "prune": {"every_days": 7},
}
DEFAULT_QUIET = ("09:00", "18:00")
DEFAULT_LABEL = "com.careeros.tick"
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
WHERE = "config/pipeline.yaml: schedule"


@dataclass
class JobSchedule:
    kind: str
    every_minutes: float
    enabled: bool = True
    preset: str | None = None

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
    if ("every_hours" in raw) == ("every_days" in raw):
        raise _err(f"{where} needs exactly one of every_hours / every_days")
    minutes = (_pos(raw["every_hours"], f"{where}.every_hours") * 60 if "every_hours" in raw
               else _pos(raw["every_days"], f"{where}.every_days") * 24 * 60)
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise _err(f"{where}.enabled must be true or false")
    preset = raw.get("preset")
    if preset is not None:
        if kind not in CLAUDE_KINDS:
            raise _err(f"{where}.preset only applies to score and prepare")
        if preset not in presets:
            raise _err(f"{where}.preset must be one of {' | '.join(presets)}, got {preset!r}")
    return JobSchedule(kind, minutes, enabled, preset)


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
        c.jobs[kind] = _job(kind, jobs.get(kind, DEFAULT_JOBS[kind]), PRESET_NAMES)
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
        last = _parse(((state or {}).get("jobs") or {}).get(kind, {}).get("last_run"))
        every = timedelta(minutes=job.every_minutes)
        due = last + every if last else now
        if now < due:
            out.append(Decision(kind, "not_due", due))
            continue
        eff = effective_due(cfg, job, due)
        if asleep and eff < now - miss:
            slots = int(math.floor((now - eff) / every)) + 1
            out.append(Decision(kind, "missed", eff, slots, f"{slots} slot(s) since {eff.isoformat()}"))
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
        last = _parse(((state or {}).get("jobs") or {}).get(kind, {}).get("last_run"))
        due = max(last + timedelta(minutes=job.every_minutes), now) if last else now
        out[kind] = effective_due(cfg, job, due).astimezone(now.tzinfo) if now.tzinfo else effective_due(cfg, job, due)
    return out
