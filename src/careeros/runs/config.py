"""`pipeline.yaml: runs` (budgets, ranking, stop rules) and `llm` (the headless command), with defaults.

Every default here is the "(Recommended)" value documented in examples/config/pipeline.yaml; a test keeps the
two in step. Malformed values raise ConfigError (fail closed: an unattended run never guesses a budget).
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from careeros.config import ConfigError

KINDS = ("score", "prepare")
PRESET_NAMES = ("small", "medium", "large", "max", "custom")
RECOMMENDED_PRESET = "medium"
BUDGET_KEYS = ("max_score_jobs", "max_prepare_jobs", "max_minutes")
DEFAULT_PRESETS: dict[str, dict[str, int]] = {
    "small": {"max_score_jobs": 10, "max_prepare_jobs": 2, "max_minutes": 30},
    "medium": {"max_score_jobs": 25, "max_prepare_jobs": 5, "max_minutes": 90},
    "large": {"max_score_jobs": 50, "max_prepare_jobs": 10, "max_minutes": 180},
    "max": {"max_score_jobs": 150, "max_prepare_jobs": 25, "max_minutes": 480},
}
DEFAULT_RANKING: dict[str, float] = {
    "freshness_weight": 60,   # full weight for postings younger than fresh_hours, then linear down to 0
    "fresh_hours": 48,
    "stale_days": 30,
    "dream_bonus": 25,
    "deadline_bonus": 15,     # posting closes within deadline_days
    "deadline_days": 7,
    "fit_weight": 0.5,        # prepare runs only: points per fit point (fit 80 -> +40)
    "retry_bonus": 30,        # a job that failed once goes near the front of the next run
}
DEFAULT_TIMEOUTS: dict[str, float] = {"score": 10, "prepare": 45}
# Verified against `claude --help` (Claude Code 2.1): -p prints and exits; stream-json needs --verbose and ends
# with one `result` event; dontAsk denies any tool not in --allowedTools instead of prompting (nobody is there).
DEFAULT_HEADLESS_CMD: list[str] = ["claude", "-p", "--output-format", "stream-json", "--verbose",
                                   "--permission-mode", "dontAsk"]
DEFAULT_ALLOWED_TOOLS: list[str] = [
    "Read", "Write", "Edit", "Glob", "Grep",
    "Bash(.venv/bin/careeros *)", "Bash(.venv/bin/python *)", "Bash(date *)",
    "WebSearch", "WebFetch",
]
DEFAULT_USAGE_LIMIT_PATTERNS = [r"usage limit", r"hit your limit", r"limit reached", r"rate.?limit",
                                r"out of (extra )?usage", r"quota"]
DEFAULT_AUTH_PATTERNS = [r"/login", r"not logged in", r"invalid api key", r"oauth token", r"authenticat",
                         r"unauthori[sz]ed", r"credentials? (expired|missing|invalid)"]
RUN_KEYS = ("preset", "presets", "custom", "job_timeout_minutes", "max_consecutive_failures", "stop_on_timeout",
            "preflight_doctor", "ranking", "required_mcp_servers", "usage_limit_patterns", "auth_patterns")


@dataclass
class Budget:
    preset: str
    max_jobs: int
    max_minutes: float

    def to_dict(self) -> dict[str, Any]:
        return {"preset": self.preset, "max_jobs": self.max_jobs, "max_minutes": self.max_minutes}


@dataclass
class RunsConfig:
    preset: str = RECOMMENDED_PRESET
    presets: dict[str, dict[str, int]] = field(default_factory=lambda: deepcopy(DEFAULT_PRESETS))
    job_timeout_minutes: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TIMEOUTS))
    max_consecutive_failures: int = 3
    stop_on_timeout: bool = True
    preflight_doctor: bool = True
    ranking: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RANKING))
    required_mcp_servers: list[str] = field(default_factory=list)
    usage_limit_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_USAGE_LIMIT_PATTERNS))
    auth_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_AUTH_PATTERNS))
    headless_cmd: list[str] = field(default_factory=lambda: list(DEFAULT_HEADLESS_CMD))
    allowed_tools: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_TOOLS))
    model: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _err(msg: str) -> ConfigError:
    return ConfigError(f"config/pipeline.yaml: {msg} (see examples/config/pipeline.yaml)")


def _num(v: Any, where: str, *, ge: float | None = None, gt: float | None = None, whole: bool = False) -> Any:
    ok = isinstance(v, (int, float)) and not isinstance(v, bool)
    if ok and whole:
        ok = float(v).is_integer()
    if ok and ge is not None:
        ok = v >= ge
    if ok and gt is not None:
        ok = v > gt
    if not ok:
        bound = f">= {ge}" if ge is not None else f"> {gt}"
        raise _err(f"{where} must be {'a whole number' if whole else 'a number'} {bound}, got {v!r}")
    return int(v) if whole else v


def _bool(v: Any, where: str) -> bool:
    if not isinstance(v, bool):
        raise _err(f"{where} must be true or false, got {v!r}")
    return v


def _str_list(v: Any, where: str) -> list[str]:
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        raise _err(f"{where} must be a list of strings")
    return list(v)


def _patterns(v: Any, where: str) -> list[str]:
    out = _str_list(v, where)
    for p in out:
        try:
            re.compile(p, re.I)
        except re.error as e:
            raise _err(f"{where}: {p!r} is not a valid regex ({e})") from None
    return out


def _budget_block(raw: Any, where: str, base: dict[str, int]) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise _err(f"{where} must be a mapping of {', '.join(BUDGET_KEYS)}")
    out = dict(base)
    for k, v in raw.items():
        if k not in BUDGET_KEYS:
            raise _err(f"{where}: unknown key {k!r}; valid: {', '.join(BUDGET_KEYS)}")
        out[k] = _num(v, f"{where}.{k}", gt=0) if k == "max_minutes" else _num(v, f"{where}.{k}", ge=1, whole=True)
    return out


def load_runs_config(settings: Any) -> RunsConfig:
    pipeline = getattr(settings, "pipeline", None) or {}
    raw = pipeline.get("runs")
    raw = {} if raw is None else raw
    if not isinstance(raw, dict):
        raise _err("runs must be a mapping")
    for k in raw:
        if k not in RUN_KEYS:
            raise _err(f"runs: unknown key {k!r}")
    cfg = RunsConfig(raw=raw)
    presets = raw.get("presets") or {}
    if not isinstance(presets, dict):
        raise _err("runs.presets must be a mapping")
    for name, block in presets.items():
        if name not in DEFAULT_PRESETS:
            raise _err(f"runs.presets: unknown preset {name!r}; valid: {', '.join(DEFAULT_PRESETS)} "
                       "(put your own numbers under runs.custom)")
        cfg.presets[name] = _budget_block(block or {}, f"runs.presets.{name}", DEFAULT_PRESETS[name])
    cfg.presets["custom"] = _budget_block(raw.get("custom") or {}, "runs.custom", cfg.presets[RECOMMENDED_PRESET])
    preset = raw.get("preset", RECOMMENDED_PRESET)
    if preset not in PRESET_NAMES:
        raise _err(f"runs.preset must be one of {' | '.join(PRESET_NAMES)}, got {preset!r}")
    cfg.preset = preset
    timeouts = raw.get("job_timeout_minutes") or {}
    if not isinstance(timeouts, dict):
        raise _err("runs.job_timeout_minutes must be a mapping {score: N, prepare: N}")
    for k, v in timeouts.items():
        if k not in KINDS:
            raise _err(f"runs.job_timeout_minutes: unknown kind {k!r}; valid: {', '.join(KINDS)}")
        cfg.job_timeout_minutes[k] = _num(v, f"runs.job_timeout_minutes.{k}", gt=0)
    if "max_consecutive_failures" in raw:
        cfg.max_consecutive_failures = _num(raw["max_consecutive_failures"], "runs.max_consecutive_failures",
                                            ge=1, whole=True)
    for key in ("stop_on_timeout", "preflight_doctor"):
        if key in raw:
            setattr(cfg, key, _bool(raw[key], f"runs.{key}"))
    ranking = raw.get("ranking") or {}
    if not isinstance(ranking, dict):
        raise _err("runs.ranking must be a mapping")
    for k, v in ranking.items():
        if k not in DEFAULT_RANKING:
            raise _err(f"runs.ranking: unknown key {k!r}; valid: {', '.join(DEFAULT_RANKING)}")
        cfg.ranking[k] = _num(v, f"runs.ranking.{k}", ge=0)
    if "required_mcp_servers" in raw:
        cfg.required_mcp_servers = _str_list(raw["required_mcp_servers"] or [], "runs.required_mcp_servers")
    for key in ("usage_limit_patterns", "auth_patterns"):
        if key in raw:
            setattr(cfg, key, _patterns(raw[key], f"runs.{key}"))
    llm = pipeline.get("llm") or {}
    if not isinstance(llm, dict):
        raise _err("llm must be a mapping")
    if "headless_cmd" in llm:
        cfg.headless_cmd = _str_list(llm["headless_cmd"], "llm.headless_cmd")
    if "allowed_tools" in llm:
        cfg.allowed_tools = _str_list(llm["allowed_tools"], "llm.allowed_tools")
    model = llm.get("model_hint")
    if model is not None and not isinstance(model, str):
        raise _err("llm.model_hint must be a model name or null")
    cfg.model = model or None
    return cfg


def budget_for(cfg: RunsConfig, kind: str, preset: str | None = None, max_jobs: int | None = None,
               max_minutes: float | None = None) -> Budget:
    """The budget for one run: the preset (config default unless given), then CLI overrides. ValueError on bad input."""
    if kind not in KINDS:
        raise ValueError(f"unknown run kind {kind!r}")
    name = preset or cfg.preset
    if name not in cfg.presets:
        raise ValueError(f"unknown preset {name!r}; valid: {' | '.join(PRESET_NAMES)}")
    block = cfg.presets[name]
    jobs = block[f"max_{kind}_jobs"] if max_jobs is None else max_jobs
    minutes = block["max_minutes"] if max_minutes is None else max_minutes
    if not isinstance(jobs, int) or jobs < 1:
        raise ValueError(f"--max-jobs must be >= 1, got {jobs!r}")
    if not isinstance(minutes, (int, float)) or minutes <= 0:
        raise ValueError(f"--max-minutes must be > 0, got {minutes!r}")
    return Budget(name, jobs, minutes)
