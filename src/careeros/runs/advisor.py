"""Suggest-only advisor: storage growth and run efficiency -> recommendations, each with an id and (when there is
one) a concrete change to config/pipeline.yaml. Nothing here writes config; `careeros advise apply <id>` does,
and only when the candidate runs it.

Storage (from data/runs/storage.jsonl), once the snapshots span `advisor.advise_after_days`:
  - growth projected 30 / 90 days ahead (linear over the history) vs `storage.budget_mb`; at `warn_at_pct` of the
    budget, tighten the retention key of the biggest category (postings, screenshots, run logs; résumés, the
    tracker and the rest have no retention rule: advice only)
  - disk free under `storage.disk_free_warn_pct`: a warning
  - prune removed nothing for `advisor.prune_idle_weeks` weeks while far under budget: keep postings longer
Runs (from run.json + attempts), once a kind has `advisor.min_runs` runs in the last `advisor.window_days`:
  - slow jobs near the timeout -> raise runs.job_timeout_minutes.<kind>
  - usage-limit stops -> a smaller runs.preset; a backlog that outgrows the budget -> a bigger one
  - failure rate, scored -> prepared yield: advice only
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from careeros.config import ConfigError

MB = 1024 * 1024
FILE = "config/pipeline.yaml"
STORAGE_DEFAULTS = {"budget_mb": 1024, "warn_at_pct": 80, "disk_free_warn_pct": 10}
ADVISOR_DEFAULTS = {"advise_after_days": 14, "prune_idle_weeks": 4, "min_runs": 5, "window_days": 30,
                    "usage_limit_stops": 2, "failure_rate_warn": 0.3}
PRESET_LADDER = ("small", "medium", "large", "max")
# category -> (retention key, how to tighten it)
TIGHTEN = {
    "postings": ("unprepared_posting_days", lambda d: max(14, d * 2 // 3)),
    "screenshots": ("screenshots_after_closed_days", lambda d: max(7, (d // 2) // 7 * 7)),
    "run_logs": ("run_logs_days", lambda d: max(7, (d // 2) // 7 * 7)),
}
LOOSEN_STEP_DAYS = 30


def _num(block: dict[str, Any], key: str, where: str, lo: float, hi: float | None = None) -> float:
    v = block[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < lo or (hi is not None and v > hi):
        rng = f">= {lo}" + (f" and <= {hi}" if hi is not None else "")
        raise ConfigError(f"config/pipeline.yaml: {where}.{key} must be a number {rng}, got {v!r}")
    return v


def load_advisor_config(pipeline: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, defaults, bounds in (
        ("storage", STORAGE_DEFAULTS, {"budget_mb": (1, None), "warn_at_pct": (1, 100), "disk_free_warn_pct": (0, 100)}),
        ("advisor", ADVISOR_DEFAULTS, {"advise_after_days": (1, None), "prune_idle_weeks": (1, None),
                                       "min_runs": (1, None), "window_days": (1, None), "usage_limit_stops": (1, None),
                                       "failure_rate_warn": (0, 1)}),
    ):
        raw = (pipeline or {}).get(name)
        raw = {} if raw is None else raw
        if not isinstance(raw, dict):
            raise ConfigError(f"config/pipeline.yaml: {name} must be a mapping")
        block = dict(defaults)
        for k in raw:
            if k not in defaults:
                raise ConfigError(f"config/pipeline.yaml: {name}: unknown key {k!r}; valid: {', '.join(defaults)}")
            block[k] = raw[k]
            lo, hi = bounds[k]
            _num(block, k, name, lo, hi)
        out[name] = block
    return out


def _at(s: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(s["at"])


def _rec(rid: str, kind: str, severity: str, title: str, why: str, path: str | None = None, frm: Any = None,
         to: Any = None) -> dict[str, Any]:
    change = {"file": FILE, "path": path, "from": frm, "to": to} if path else None
    return {"id": rid, "kind": kind, "severity": severity, "title": title, "why": why, "change": change}


def _retention(pipeline: dict[str, Any], key: str) -> int:
    """The effective value, as `careeros prune` sees it: missing = retention.DEFAULTS, null / 0 = rule off (0)."""
    from careeros import retention

    return int(retention.retention_config(type("_P", (), {"pipeline": pipeline or {}})())[key])


def storage_advice(snaps: list[dict[str, Any]], pipeline: dict[str, Any], now: datetime) -> dict[str, Any]:
    cfg = load_advisor_config(pipeline)
    st, adv = cfg["storage"], cfg["advisor"]
    if not snaps:
        return {"ready": False, "days": 0, "need_days": adv["advise_after_days"], "recommendations": []}
    first, last = snaps[0], snaps[-1]
    days = (_at(last) - _at(first)).total_seconds() / 86400
    out: dict[str, Any] = {"ready": days >= adv["advise_after_days"], "days": round(days, 1),
                           "need_days": adv["advise_after_days"], "current": last["total"], "recommendations": []}
    if not out["ready"]:
        return out
    rate = max(0.0, (last["total"] - first["total"]) / days) if days else 0.0
    proj = {"30d": int(last["total"] + 30 * rate), "90d": int(last["total"] + 90 * rate)}
    budget = st["budget_mb"] * MB
    out.update(rate_per_day=int(rate), projection=proj, budget=int(budget))
    recs = out["recommendations"]
    limit = budget * st["warn_at_pct"] / 100
    by_cat = last.get("bytes") or {}
    dominant = max(by_cat, key=lambda c: by_cat[c]) if by_cat else None
    tighten = max(proj["90d"], last["total"]) >= limit
    if tighten and dominant:
        head = (f"storage is projected at {proj['90d'] / MB:.0f} MB in 90 days (budget {st['budget_mb']} MB, "
                f"warn at {st['warn_at_pct']}%); {dominant} is the biggest part ({by_cat[dominant] / MB:.0f} MB)")
        if dominant in TIGHTEN:
            key, fn = TIGHTEN[dominant]
            cur = _retention(pipeline, key)
            if not cur:  # the rule is off: turning it on is the candidate's call, not a "tighten"
                recs.append(_rec(f"retention-off-{key}", "storage", "warn", f"{dominant} is filling the budget",
                                 head + f"; retention.{key} is off (null / 0), so nothing prunes it"))
            elif fn(cur) != cur:
                recs.append(_rec(f"tighten-{key}", "storage", "warn", f"Prune {dominant} sooner",
                                 head, f"retention.{key}", cur, fn(cur)))
        else:
            recs.append(_rec(f"storage-{dominant}", "storage", "warn", f"{dominant} is filling the budget",
                             head + "; it has no retention rule (kept by design): raise storage.budget_mb or "
                                    "clean up by hand"))
    free_pct = (last.get("disk") or {}).get("free_pct")
    if isinstance(free_pct, (int, float)) and free_pct < st["disk_free_warn_pct"]:
        recs.append(_rec("disk-low", "storage", "warn", "Disk almost full",
                         f"{free_pct}% of the disk is free (warn under {st['disk_free_warn_pct']}%)"))
    window_start = now - timedelta(weeks=adv["prune_idle_weeks"])
    prunes = [s for s in snaps if s.get("trigger") == "prune"]
    recent = [s for s in prunes if _at(s) >= window_start]
    cur = _retention(pipeline, "unprepared_posting_days")
    if (not tighten and cur and recent and prunes and _at(prunes[0]) <= window_start
            and all(not s.get("pruned_bytes") for s in recent) and proj["90d"] < limit / 2):
        recs.append(_rec("loosen-unprepared_posting_days", "storage", "info", "Keep postings longer",
                         f"prune removed nothing in {adv['prune_idle_weeks']} weeks and storage is far under budget; "
                         "full descriptions help re-scoring", "retention.unprepared_posting_days", cur,
                         cur + LOOSEN_STEP_DAYS))
    return out


# --- runs ------------------------------------------------------------------------------------------------------

def _p90(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, math.ceil(0.9 * len(s)) - 1)]


def _preset_target(kind: str, runs_of_kind: list[dict[str, Any]], rcfg: Any, sched: Any) -> tuple[str, Any, str]:
    """(yaml path, its current value, the preset the runs actually used). The per-job preset
    (schedule.jobs.<kind>.preset) wins over runs.preset when it is set."""
    job = sched.jobs.get(kind) if sched else None
    path, cur = (f"schedule.jobs.{kind}.preset", job.preset) if job and job.preset else ("runs.preset", rcfg.preset)
    used = Counter((r.get("budget") or {}).get("preset") for r in runs_of_kind).most_common(1)
    return path, cur, (used[0][0] if used and used[0][0] else cur)


def _step(preset: str, delta: int) -> str | None:
    if preset not in PRESET_LADDER:
        return None
    i = PRESET_LADDER.index(preset) + delta
    return PRESET_LADDER[i] if 0 <= i < len(PRESET_LADDER) else None


def run_advice(runs: list[dict[str, Any]], pipeline: dict[str, Any], now: datetime) -> dict[str, Any]:
    from careeros.config import ConfigError
    from careeros.runs.config import load_runs_config
    from careeros.runs.schedule import load_schedule

    adv = load_advisor_config(pipeline)["advisor"]
    p = type("_P", (), {"pipeline": pipeline})()
    rcfg = load_runs_config(p)
    try:
        sched = load_schedule(p)
    except ConfigError:
        sched = None
    since = now - timedelta(days=adv["window_days"])
    recent = [r for r in runs if r.get("status") != "running" and r.get("started_at")
              and datetime.fromisoformat(r["started_at"]) >= since]
    metrics: dict[str, Any] = {}
    recs: list[dict[str, Any]] = []
    ready_runs: dict[str, list[dict[str, Any]]] = {}
    backlog_kinds: list[str] = []
    for kind in ("score", "prepare"):
        rs = [r for r in recent if r.get("kind") == kind]
        if not rs:
            continue
        atts = [a for r in rs for a in r.get("_attempts") or []]
        durs = [float(a.get("duration_s") or 0) for a in atts]
        attempted = sum((r.get("counters") or {}).get("attempted", 0) for r in rs)
        failed = sum((r.get("counters") or {}).get("failed", 0) for r in rs)
        used = [(r.get("counters") or {}).get("attempted", 0) / max(1, (r.get("budget") or {}).get("max_jobs") or 1)
                for r in rs]
        m = {"runs": len(rs), "attempts": attempted, "avg_job_s": round(sum(durs) / len(durs), 1) if durs else 0,
             "p90_job_s": _p90(durs), "failure_rate": round(failed / attempted, 2) if attempted else 0.0,
             "budget_used": round(sum(used) / len(used), 2), "stops": dict(Counter(r.get("stop_reason") for r in rs))}
        if kind == "score":
            oks = [a for a in atts if a.get("outcome") == "ok"]
            m["prepare_share"] = round(sum(1 for a in oks if (a.get("result") or {}).get("decision") == "prepare")
                                       / len(oks), 2) if oks else None
        metrics[kind] = m
        if len(rs) < adv["min_runs"]:
            continue
        ready_runs[kind] = rs
        limit_s = float(rcfg.job_timeout_minutes[kind]) * 60
        timeouts = sum(1 for a in atts if a.get("outcome") == "timeout")
        if durs and (m["p90_job_s"] >= 0.8 * limit_s or timeouts):
            to = max(math.ceil(max(m["p90_job_s"], limit_s) * 1.5 / 60), int(rcfg.job_timeout_minutes[kind]) + 5)
            recs.append(_rec(f"timeout-{kind}", "runs", "warn", f"Give {kind} jobs more time",
                             f"90% of {kind} jobs take up to {m['p90_job_s'] / 60:.1f} min ({timeouts} timed out); "
                             f"the timeout is {rcfg.job_timeout_minutes[kind]:g} min",
                             f"runs.job_timeout_minutes.{kind}", rcfg.job_timeout_minutes[kind], to))
        if m["failure_rate"] > adv["failure_rate_warn"]:
            recs.append(_rec(f"failures-{kind}", "runs", "warn", f"{kind} jobs fail often",
                             f"{m['failure_rate']:.0%} of {kind} jobs failed in the last {adv['window_days']} days; "
                             "`careeros run show <id>` shows why (a denied tool: add it to llm.allowed_tools)"))
        if kind == "score" and m.get("prepare_share") is not None and m["attempts"] >= 20 and m["prepare_share"] < 0.1:
            recs.append(_rec("score-yield", "runs", "info", "Most scored jobs are skipped",
                             f"only {m['prepare_share']:.0%} of scored jobs reach prepare: tighten the scout filters "
                             "(targets.yaml scout / categories) or review targets.yaml thresholds.min_fit_to_prepare"))
        backlog = [r for r in rs if r.get("stop_reason") == "budget_reached"
                   and (r.get("counters") or {}).get("candidates", 0) > 2 * ((r.get("budget") or {}).get("max_jobs") or 0)]
        if len(backlog) >= 0.6 * len(rs):
            backlog_kinds.append(kind)
    # usage-limit stops: only score / prepare runs of kinds that reached min_runs count
    limited = {k: sum(1 for r in rs if r.get("stop_reason") == "usage_limit") for k, rs in ready_runs.items()}
    n_limited = sum(limited.values())
    if n_limited >= adv["usage_limit_stops"]:
        why = f"{n_limited} runs in the last {adv['window_days']} days stopped at the subscription usage limit"
        recs += _preset_recs("down", [k for k, n in limited.items() if n], ready_runs, rcfg, sched,
                             "Runs hit the usage limit", why, "warn")
    elif backlog_kinds:
        why = ("runs keep hitting the job budget with over twice as many jobs still waiting "
               f"({', '.join(backlog_kinds)})")
        recs += _preset_recs("up", backlog_kinds, ready_runs, rcfg, sched, "The queue outgrows the budget", why, "info")
    ready = bool(ready_runs)
    return {"ready": ready, "min_runs": adv["min_runs"], "metrics": metrics, "recommendations": recs}


def _preset_recs(direction: str, kinds: list[str], ready_runs: dict[str, list[dict[str, Any]]], rcfg: Any, sched: Any,
                 title: str, why: str, severity: str) -> list[dict[str, Any]]:
    """One recommendation per YAML key: both kinds on runs.preset share one `preset-<dir>`; a kind with its own
    schedule.jobs.<kind>.preset gets `preset-<dir>-<kind>`."""
    by_path: dict[str, dict[str, Any]] = {}
    for k in kinds:
        path, cur, used = _preset_target(k, ready_runs[k], rcfg, sched)
        e = by_path.setdefault(path, {"cur": cur, "used": used, "kinds": []})
        e["kinds"].append(k)
    out = []
    for path, e in by_path.items():
        rid = f"preset-{direction}" if path == "runs.preset" else f"preset-{direction}-{e['kinds'][0]}"
        to = _step(e["used"], -1 if direction == "down" else 1)
        text = f"{why}; affects {', '.join(e['kinds'])}"
        if to is None or to == e["cur"]:
            hint = ("run less often (fewer schedule.jobs.score / prepare times) or lower runs.custom"
                    if direction == "down" else "raise runs.custom")
            out.append(_rec(rid if direction == "up" else "usage-limit", "runs", severity, title, f"{text}; {hint}"))
        else:
            out.append(_rec(rid, "runs", severity, title, text, path, e["cur"], to))
    return out


def effective_value(pipeline: dict[str, Any], path: str) -> Any:
    """What the code uses for a recommendation path (defaults applied), so `advise apply` compares like with like:
    a key missing from the file is its default, a null retention rule is 0 (off)."""
    from careeros.runs.config import load_runs_config
    from careeros.runs.schedule import load_schedule
    from careeros.runs.yamledit import get_path

    parts = path.split(".")
    p = type("_P", (), {"pipeline": pipeline or {}})()
    if parts[0] == "retention" and len(parts) == 2:
        return _retention(pipeline, parts[1])
    if path == "runs.preset":
        return load_runs_config(p).preset
    if parts[:2] == ["runs", "job_timeout_minutes"] and len(parts) == 3:
        return load_runs_config(p).job_timeout_minutes.get(parts[2])
    if parts[:2] == ["schedule", "jobs"] and len(parts) == 4 and parts[3] == "preset":
        return load_schedule(p).jobs[parts[2]].preset
    return get_path(pipeline, path)


def load_runs_history(settings: Any) -> list[dict[str, Any]]:
    from careeros.runs.store import RunStore

    rs = RunStore(settings)
    out = []
    for r in rs.list_runs():
        r["_attempts"] = rs.load_attempts(r["id"])
        out.append(r)
    return out


def advise(settings: Any, now: datetime) -> dict[str, Any]:
    from careeros.runs.storage import load_snapshots
    from careeros.runs.store import RunStore

    s = storage_advice(load_snapshots(RunStore(settings)), settings.pipeline, now)
    r = run_advice(load_runs_history(settings), settings.pipeline, now)
    return {"storage": s, "runs": r, "recommendations": s["recommendations"] + r["recommendations"]}
