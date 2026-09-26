"""Run history, canonical in files under `paths.runs_dir` (default: data/runs next to data/jobs).

data/runs/
  <run_id>/run.json               parent record: kind, trigger, budget, status, counters, stop_reason, timestamps
  <run_id>/attempts/NNN.json      one per skill call: job_id, stage, session_id, outcome, RESULT, timings
  <run_id>/attempts/NNN.stream.jsonl   the raw stream-json output of that call (a run log: pruned first)
  <run_id>/run.log                human-readable log
  queue-<kind>.json               the latest ranking ("why next") for the UI and `careeros run status`
  runner.lock, locks/<job_id>.lock
  pause.json                      global pause (`careeros run pause`)

Every JSON write is atomic (temp file + rename). Run ids sort by start time: YYYYMMDD-HHMMSS-<kind>-<hex4>.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from careeros.store import _is_finder_copy

RUN = "run.json"
LOG = "run.log"
ATTEMPTS = "attempts"


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def runs_dir_for(settings: Any) -> Path:
    p = settings.paths.get("runs_dir")
    return Path(p) if p else Path(settings.paths["jobs_dir"]).parent / "runs"


class RunStore:
    def __init__(self, settings: Any):
        self.settings = settings
        self.dir = runs_dir_for(settings)

    # --- paths ---------------------------------------------------------------------------------------------

    def run_dir(self, run_id: str) -> Path:
        return self.dir / run_id

    @property
    def runner_lock_path(self) -> Path:
        return self.dir / "runner.lock"

    def job_lock_path(self, job_id: str) -> Path:
        return self.dir / "locks" / f"{job_id}.lock"

    @property
    def pause_path(self) -> Path:
        return self.dir / "pause.json"

    # --- runs ----------------------------------------------------------------------------------------------

    def new_run(self, kind: str, trigger: str, budget: dict[str, Any], now: datetime, run_id: str | None = None,
                **extra: Any) -> dict[str, Any]:
        rid = run_id or f"{now.astimezone().strftime('%Y%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:4]}"
        run = {"id": rid, "kind": kind, "trigger": trigger, "budget": budget, "status": "running",
               "stop_reason": None, "detail": "", "started_at": iso(now), "ended_at": None, "duration_s": None,
               "pid": os.getpid(), "counters": {}, "attempts": [], **extra}
        self.save_run(run)
        return run

    def save_run(self, run: dict[str, Any]) -> None:
        _dump(self.run_dir(run["id"]) / RUN, run)

    def load_run(self, run_id: str) -> dict[str, Any] | None:
        got = _load(self.run_dir(run_id) / RUN)
        return got if isinstance(got, dict) else None

    def run_ids(self) -> list[str]:
        if not self.dir.is_dir():
            return []
        return sorted((d.name for d in self.dir.iterdir()
                       if d.is_dir() and not _is_finder_copy(d.name) and (d / RUN).exists()), reverse=True)

    def list_runs(self, kind: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        out = []
        for rid in self.run_ids():
            r = self.load_run(rid)
            if r and (kind is None or r.get("kind") == kind):
                out.append(r)
                if limit and len(out) >= limit:
                    break
        return out

    # --- attempts ------------------------------------------------------------------------------------------

    def next_attempt(self, run_id: str) -> tuple[int, Path]:
        d = self.run_dir(run_id) / ATTEMPTS
        d.mkdir(parents=True, exist_ok=True)
        n = 1 + sum(1 for f in d.glob("[0-9][0-9][0-9].json"))
        return n, d / f"{n:03d}.stream.jsonl"

    def save_attempt(self, run_id: str, attempt: dict[str, Any]) -> None:
        _dump(self.run_dir(run_id) / ATTEMPTS / f"{attempt['n']:03d}.json", attempt)

    def load_attempts(self, run_id: str) -> list[dict[str, Any]]:
        d = self.run_dir(run_id) / ATTEMPTS
        if not d.is_dir():
            return []
        return [a for f in sorted(d.glob("[0-9][0-9][0-9].json")) if isinstance(a := _load(f), dict)]

    # --- log -----------------------------------------------------------------------------------------------

    def log(self, run_id: str, msg: str) -> None:
        d = self.run_dir(run_id)
        d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with (d / LOG).open("a", encoding="utf-8") as f:
            f.write(f"- {ts} [run] {msg}\n")

    def read_log(self, run_id: str) -> str:
        p = self.run_dir(run_id) / LOG
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # --- queue ("why next") --------------------------------------------------------------------------------

    def write_queue(self, kind: str, items: list[dict[str, Any]], excluded: list[dict[str, Any]],
                    now: datetime) -> None:
        _dump(self.dir / f"queue-{kind}.json", {"kind": kind, "ranked_at": iso(now), "items": items,
                                                "excluded": excluded})

    def load_queue(self, kind: str) -> dict[str, Any]:
        got = _load(self.dir / f"queue-{kind}.json")
        return got if isinstance(got, dict) else {"kind": kind, "items": [], "excluded": []}

    # --- pause ---------------------------------------------------------------------------------------------

    def set_pause(self, until: datetime | None, reason: str, now: datetime) -> dict[str, Any]:
        body = {"paused_at": iso(now), "until": iso(until) if until else None, "reason": reason}
        _dump(self.pause_path, body)
        return body

    def clear_pause(self) -> bool:
        if self.pause_path.exists():
            self.pause_path.unlink()
            return True
        return False

    def pause_state(self, now: datetime) -> dict[str, Any] | None:
        """The active pause, or None (no pause file, or its `until` has passed)."""
        p = _load(self.pause_path)
        if not isinstance(p, dict):
            return None
        until = p.get("until")
        if until:
            try:
                if now >= datetime.fromisoformat(until):
                    return None
            except ValueError:
                pass
        return p
