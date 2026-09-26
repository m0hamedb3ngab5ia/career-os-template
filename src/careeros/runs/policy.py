"""Volume and submit policy in code: the daily apply cap, the auto-submit rules, the retry limit.

Daily cap = `targets.yaml: volume.max_applications_per_day` x `volume.season_multiplier[<month>]` (floored),
counted per calendar day from DateApplied (tracker) or the first `applied` in status history. apply-job checks it
with `careeros run cap --check`; any future apply path must call `cap_status` before submitting.

Auto-submit (`pipeline.yaml: runs.auto_submit`) is configuration only in this version: runs never apply.
`auto_submit_decision` is the pure rule a future apply path will call. Tier A is never auto-submitted, whatever
the config says, and a safety verdict other than pass always means manual.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from careeros.config import ConfigError

DEFAULT_MAX_PER_DAY = 15
DEFAULT_RETRY = {"max_attempts": 2, "action_item": True}
AUTO_SUBMIT_KEYS = ("enabled", "allow", "manual")
DEFAULT_AUTO_SUBMIT = {"enabled": False, "allow": ["tier_c", "tier_b"], "manual": ["tier_a", "fit_gte_90"]}
_TOKEN_RE = re.compile(r"^(tier_[abc]|fit_(gte|lt)_\d{1,3}|dream|category_[a-z0-9_]+)$")


def _whole(v: Any, minimum: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= minimum


# --- daily cap ------------------------------------------------------------------------------------------

def _volume(targets: dict[str, Any]) -> tuple[int, dict[int, float]]:
    vol = (targets or {}).get("volume") or {}
    if not isinstance(vol, dict):
        raise ConfigError("config/targets.yaml: volume must be a mapping")
    base = vol.get("max_applications_per_day", DEFAULT_MAX_PER_DAY)
    if not _whole(base, 1):
        raise ConfigError(f"config/targets.yaml: volume.max_applications_per_day must be a whole number >= 1, "
                          f"got {base!r}")
    raw = vol.get("season_multiplier") or {}
    if not isinstance(raw, dict):
        raise ConfigError("config/targets.yaml: volume.season_multiplier must be a mapping month -> multiplier")
    mult: dict[int, float] = {}
    for k, v in raw.items():
        try:
            month = int(k)
        except (TypeError, ValueError):
            month = 0
        if not 1 <= month <= 12:
            raise ConfigError(f"config/targets.yaml: volume.season_multiplier key {k!r} must be a month 1-12")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise ConfigError(f"config/targets.yaml: volume.season_multiplier[{k}] must be a number > 0, got {v!r}")
        mult[month] = float(v)
    return base, mult


def daily_cap(targets: dict[str, Any], day: date) -> int:
    base, mult = _volume(targets)
    return max(1, math.floor(base * mult.get(day.month, 1.0)))


def applied_on(records: Iterable[Any], day: date) -> int:
    """Applications with DateApplied == `day` (company_policy.JobRecord list)."""
    return sum(1 for r in records if getattr(r, "date_applied", None) == day)


def cap_status(targets: dict[str, Any], records: Iterable[Any], day: date) -> dict[str, Any]:
    base, mult = _volume(targets)
    cap = daily_cap(targets, day)
    done = applied_on(records, day)
    return {"date": day.isoformat(), "cap": cap, "applied": done, "remaining": max(0, cap - done),
            "multiplier": mult.get(day.month, 1.0), "base": base, "reached": done >= cap}


def current_cap(settings: Any, day: date | None = None) -> dict[str, Any]:
    from careeros.company_policy import load_records

    return cap_status(settings.targets, load_records(settings), day or date.today())


# --- auto-submit (config + pure decision; no apply path uses it yet) ----------------------------------------

@dataclass
class AutoSubmitPolicy:
    enabled: bool = False
    allow: list[str] = field(default_factory=lambda: list(DEFAULT_AUTO_SUBMIT["allow"]))
    manual: list[str] = field(default_factory=lambda: list(DEFAULT_AUTO_SUBMIT["manual"]))

    @classmethod
    def from_config(cls, runs: dict[str, Any]) -> "AutoSubmitPolicy":
        raw = (runs or {}).get("auto_submit")
        if raw is None:
            return cls()
        where = "config/pipeline.yaml: runs.auto_submit"
        if not isinstance(raw, dict):
            raise ConfigError(f"{where} must be a mapping {{enabled, allow, manual}}")
        for k in raw:
            if k not in AUTO_SUBMIT_KEYS:
                raise ConfigError(f"{where}: unknown key {k!r}; valid: {', '.join(AUTO_SUBMIT_KEYS)}")
        p = cls()
        if "enabled" in raw:
            if not isinstance(raw["enabled"], bool):
                raise ConfigError(f"{where}.enabled must be true or false")
            p.enabled = raw["enabled"]
        for key in ("allow", "manual"):
            if key in raw:
                vals = raw[key] or []
                if not isinstance(vals, list) or not all(isinstance(t, str) and _TOKEN_RE.match(t) for t in vals):
                    raise ConfigError(f"{where}.{key} must be a list of rules: tier_a|tier_b|tier_c, fit_gte_<n>, "
                                      f"fit_lt_<n>, dream, category_<name>; got {vals!r}")
                setattr(p, key, list(vals))
        return p


def _matches(token: str, job: dict[str, Any]) -> bool:
    if token.startswith("tier_"):
        return str(job.get("tier") or "").upper() == token[-1].upper()
    if token.startswith("fit_"):
        fit = job.get("fit")
        if not isinstance(fit, (int, float)):
            return False
        n = int(token.rsplit("_", 1)[1])
        return fit >= n if "_gte_" in token else fit < n
    if token == "dream":
        return bool(job.get("dream"))
    if token.startswith("category_"):
        return job.get("category") == token[len("category_"):]
    return False


def auto_submit_decision(job: dict[str, Any], policy: AutoSubmitPolicy) -> tuple[bool, str]:
    """(may auto-submit, reason). `job`: tier, fit, dream, category, safety_pass. Manual rules win over allow."""
    if not policy.enabled:
        return False, "auto_submit disabled"
    if str(job.get("tier") or "").upper() == "A":
        return False, "manual: tier_a (never auto-submitted)"
    if not job.get("safety_pass"):
        return False, "safety verdict is not pass"
    for t in policy.manual:
        if _matches(t, job):
            return False, f"manual: {t}"
    for t in policy.allow:
        if _matches(t, job):
            return True, f"allowed: {t}"
    return False, "no allow rule matches"


# --- retry ------------------------------------------------------------------------------------------------

def load_retry_config(runs: dict[str, Any]) -> dict[str, Any]:
    raw = (runs or {}).get("retry")
    out = dict(DEFAULT_RETRY)
    if raw is None:
        return out
    where = "config/pipeline.yaml: runs.retry"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a mapping {{max_attempts, action_item}}")
    for k, v in raw.items():
        if k == "max_attempts":
            if not _whole(v, 1):
                raise ConfigError(f"{where}.max_attempts must be a whole number >= 1, got {v!r}")
            out[k] = v
        elif k == "action_item":
            if not isinstance(v, bool):
                raise ConfigError(f"{where}.action_item must be true or false")
            out[k] = v
        else:
            raise ConfigError(f"{where}: unknown key {k!r}; valid: max_attempts, action_item")
    return out


def load_prepare_config(runs: dict[str, Any]) -> dict[str, Any]:
    raw = (runs or {}).get("prepare")
    out = {"stop_at_daily_cap": True}
    if raw is None:
        return out
    where = "config/pipeline.yaml: runs.prepare"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a mapping {{stop_at_daily_cap}}")
    for k, v in raw.items():
        if k != "stop_at_daily_cap":
            raise ConfigError(f"{where}: unknown key {k!r}; valid: stop_at_daily_cap")
        if not isinstance(v, bool):
            raise ConfigError(f"{where}.stop_at_daily_cap must be true or false")
        out[k] = v
    return out
