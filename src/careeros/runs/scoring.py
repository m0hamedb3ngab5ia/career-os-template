"""Auto-scoring queue and budget (DEC-023, REQ-134, REQ-135): `pipeline.yaml: scoring`.

Order: fresh postings before stale ones (older than `stale_days`), then quick match (`raw.prescore`, REQ-133)
desc, then newest posted/found, then the run ranking. Jobs below `min_prescore` are not
auto-scored; a job with no prescore yet is queued. Caps: `per_scan` jobs per run, `per_day` attempts per local
day, counted from runs marked `daily_scoring`. `--job` / Score now runs skip all of this."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from careeros.runs.config import _err, _num

DEFAULT_SCORING: dict[str, int] = {"per_scan": 150, "per_day": 300, "stale_days": 21, "min_prescore": 20}


def load_scoring_config(raw: Any) -> dict[str, int]:
    raw = {} if raw is None else raw
    if not isinstance(raw, dict):
        raise _err("scoring must be a mapping {per_scan, per_day, stale_days, min_prescore}")
    out = dict(DEFAULT_SCORING)
    for k, v in raw.items():
        if k not in DEFAULT_SCORING:
            raise _err(f"scoring: unknown key {k!r}; valid: {', '.join(DEFAULT_SCORING)}")
        out[k] = _num(v, f"scoring.{k}", ge=0 if k == "min_prescore" else 1, whole=True)
    if out["min_prescore"] > 100:
        raise _err(f"scoring.min_prescore must be 0 to 100, got {out['min_prescore']!r}")
    return out


def order_queue(ranked: list[dict[str, Any]], meta: dict[str, tuple[int | None, datetime | None]],
                now: datetime, scfg: dict[str, int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(queue, below-cutoff excluded). `meta`: job_id -> (prescore, posted_at); `ranked` is in rank order."""
    stale_at = now - timedelta(days=scfg["stale_days"])
    queue, below = [], []
    for r in ranked:
        pre, posted = meta.get(r["job_id"], (None, None))
        r["prescore"] = pre
        if pre is not None and pre < scfg["min_prescore"]:
            below.append({"job_id": r["job_id"], "reason": f"below cutoff (quick match {pre} < "
                                                           f"{scfg['min_prescore']})"})
        else:
            queue.append(r)
    def key(r: dict[str, Any]) -> tuple:
        posted = meta[r["job_id"]][1]
        return (bool(posted and posted < stale_at), -(r["prescore"] if r["prescore"] is not None else -1),
                -posted.timestamp() if posted else 0, r["rank"])  # REQ-134: ties go newest posted/found first
    queue.sort(key=key)
    for i, r in enumerate(queue, 1):
        r["rank"] = i
    return queue, below


def scored_today(runs: list[dict[str, Any]], now: datetime) -> int:
    day = now.astimezone().date()
    return sum(int((r.get("counters") or {}).get("attempted") or 0) for r in runs
               if r.get("daily_scoring") and _local_date(r.get("started_at")) == day)


def _local_date(v: Any):
    try:
        return datetime.fromisoformat(str(v)).astimezone().date()
    except ValueError:
        return None


def avg_attempt_s(runs: list[dict[str, Any]]) -> float | None:
    done = [r for r in runs[:10] if (r.get("counters") or {}).get("attempted") and r.get("duration_s")]
    if not done:
        return None
    return sum(float(r["duration_s"]) for r in done) / sum(int(r["counters"]["attempted"]) for r in done)


def dry_run_line(info: dict[str, Any]) -> str:
    eta = f"ETA ~{info['eta_minutes']} min" if info["eta_minutes"] is not None else "ETA unknown (no past score runs)"
    return (f"score queue {info['queue']}; this run takes {info['take']} (per scan {info['per_scan']}, "
            f"{info['left_today']} of {info['per_day']} left today); {eta}")
