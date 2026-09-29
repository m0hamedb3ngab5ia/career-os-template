"""Batches: a named selection of jobs taken up to one stop point, run as a queue of per-job runs.

Slice 7 = the model and the preview: which jobs can go, from which stage, in which order, and why the others
cannot. The driver that works the queue (one `run_batch(kind, job_ids=[id])` per job and stage, under the global
runner lock) comes next. Hard rules, not configurable: Tier A is never auto-submitted, LinkedIn is never
automated (excluded from fill/submit), apply is one job per run, and a batch only narrows `runs.auto_submit`.
Files: `<runs_dir>/batches/<id>.json`.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from careeros.config import Settings
from careeros.runs.config import load_runs_config
from careeros.runs.runner import auto_submit_verdict, new_run_id, select_candidates
from careeros.runs.store import _dump, _load, iso, runs_dir_for
from careeros.store import Store

# stop point -> the run kinds it walks through, in order ("fill" = apply with auto-submit forced off)
STOP_POINTS = {"score": ("score",), "prepare": ("score", "prepare"), "fill": ("score", "prepare", "apply"),
               "submit": ("score", "prepare", "apply")}
MAX_JOBS = 500
_ID = re.compile(r"[\w-]{1,80}")
# reasons found after the job-state rules passed: more telling than a later stage's "status found"
_HARD = ("not found", "pruned", "posting.json unreadable")


def _hard(reason: str) -> bool:
    return reason in _HARD or reason.startswith("filtered:")


def _dir(settings: Settings) -> Path:
    return runs_dir_for(settings) / "batches"


def is_linkedin(posting: dict[str, Any]) -> bool:
    urls = f"{posting.get('url') or ''} {posting.get('apply_url') or ''}".lower()
    return str(posting.get("ats") or "").lower() == "linkedin" or "linkedin.com" in urls


def preview(settings: Settings, job_ids: list[str], stop_at: str, now: datetime | None = None) -> dict[str, Any]:
    """{stop_at, kind, selected, excluded}. Each selected job starts at the first stage it is eligible for and
    runs every later stage up to the stop point (`stages`); excluded jobs carry the reason."""
    if stop_at not in STOP_POINTS:
        raise ValueError(f"stop_at must be one of {', '.join(STOP_POINTS)}")
    ids = list(dict.fromkeys(job_ids or []))
    if not ids:
        raise ValueError("pick at least one job")
    if len(ids) > MAX_JOBS:
        raise ValueError(f"at most {MAX_JOBS} jobs per batch")
    now = now or datetime.now(timezone.utc)
    kinds = STOP_POINTS[stop_at]
    store, cfg = Store(settings), load_runs_config(settings)
    excluded: dict[str, str] = {}
    if "apply" in kinds:  # LinkedIn is never automated: the candidate applies there by hand
        for jid in ids:
            if is_linkedin(store._read(jid, "posting.json") or {}):
                excluded[jid] = "LinkedIn: apply yourself on LinkedIn"
    remaining = [j for j in ids if j not in excluded]
    selected: list[dict[str, Any]] = []
    for i, kind in enumerate(kinds):
        if not remaining:
            break
        ranked, out = select_candidates(settings, kind, cfg, now, job_ids=remaining)
        for r in ranked:
            selected.append({**r, "stage": kind, "stages": list(kinds[i:])})
        for e in out:  # a later stage's reason wins, except one found after the job-state rules passed
            if not _hard(excluded.get(e["job_id"], "")):
                excluded[e["job_id"]] = e["reason"]
        done = {r["job_id"] for r in ranked}
        remaining = [j for j in remaining if j not in done and not _hard(excluded.get(j, ""))]
    # ponytail: stage scores differ in weights (fit counts only for prepare); one merged sort is good enough
    selected.sort(key=lambda r: (-r["score"], r["job_id"]))
    for n, r in enumerate(selected, 1):
        r["rank"] = n
        excluded.pop(r["job_id"], None)
        if stop_at == "submit":
            ok, why = auto_submit_verdict(settings, store, cfg, r)
        else:
            ok, why = False, f"stop point {stop_at}: never submits"
        r["auto_submit"], r["submit_reason"] = ok, why
    return {"stop_at": stop_at, "kind": kinds[-1], "selected": selected,
            "excluded": [{"job_id": j, "reason": excluded[j]} for j in ids if j in excluded]}


def job_runs(batch: dict[str, Any]) -> list[dict[str, Any]]:
    """The batch as the queue of runs the driver makes: one job per run, stages in order. `auto_submit` is
    true only on an apply run whose job the policy allows (never Tier A, never below stop point `submit`)."""
    return [{"job_id": r["job_id"], "kind": k, "job_ids": [r["job_id"]],
             "auto_submit": bool(r["auto_submit"]) and k == "apply"}
            for r in batch["selected"] for k in r["stages"]]


def create(settings: Settings, job_ids: list[str], stop_at: str, name: str | None = None, dry_run: bool = False,
           now: datetime | None = None) -> dict[str, Any]:
    """The preview (dry run), or a saved batch in status `queued` (ValueError when no job can run)."""
    now = now or datetime.now(timezone.utc)
    out = preview(settings, job_ids, stop_at, now)
    if dry_run:
        return {**out, "dry_run": True}
    if not out["selected"]:
        reasons = "; ".join(f"{e['job_id']}: {e['reason']}" for e in out["excluded"][:5])
        raise ValueError(f"no job in this selection can run ({reasons})")
    local = now.astimezone()
    batch = {"id": new_run_id("batch", now), "name": (name or "").strip() or f"Batch — {local:%b} {local.day}",
             "created_at": iso(now), "status": "queued", "dry_run": False, **out}
    for r in batch["selected"]:
        r["state"] = "pending"
    _dump(_dir(settings) / f"{batch['id']}.json", batch)
    return batch


def load(settings: Settings, batch_id: str) -> dict[str, Any] | None:
    if not _ID.fullmatch(batch_id or ""):
        return None
    return _load(_dir(settings) / f"{batch_id}.json")


def list_ids(settings: Settings) -> list[str]:
    d = _dir(settings)
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []
