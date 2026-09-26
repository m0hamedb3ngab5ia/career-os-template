"""Per-job failure counts across runs (`data/runs/failures.json`): retry once, then an Action Item.

Only failures that are the job's own count (skill_error, invalid_result, error, timeout). A usage limit, a login
problem, a denied tool or a cancel stops the run but says nothing about the job, so its count is unchanged.
A success clears the entry.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from careeros.runs.store import RunStore, iso

JOB_FAILURES = ("skill_error", "invalid_result", "error", "timeout")


class Failures:
    def __init__(self, rs: RunStore):
        self.path = rs.dir / "failures.json"

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def key(kind: str, job_id: str) -> str:
        return f"{kind}:{job_id}"

    def get(self, kind: str, job_id: str) -> dict[str, Any] | None:
        return self._load().get(self.key(kind, job_id))

    def record(self, kind: str, job_id: str, outcome: str, detail: str, run_id: str, now: datetime) -> int:
        data = self._load()
        e = data.setdefault(self.key(kind, job_id), {"count": 0})
        e.update(count=e["count"] + 1, last_outcome=outcome, last_detail=detail[:300], last_run=run_id,
                 updated_at=iso(now))
        self._save(data)
        return e["count"]

    def clear(self, kind: str, job_id: str) -> None:
        data = self._load()
        if data.pop(self.key(kind, job_id), None) is not None:
            self._save(data)

    def retry_ids(self, kind: str, max_attempts: int) -> set[str]:
        """Jobs that failed before but have attempts left: they get the ranking's retry bonus."""
        pre = f"{kind}:"
        return {k[len(pre):] for k, e in self._load().items() if k.startswith(pre) and 0 < e.get("count", 0) < max_attempts}

    def exhausted(self, kind: str, max_attempts: int) -> dict[str, str]:
        """{job_id: reason} for jobs out of attempts: runs leave them to the Action Item."""
        pre = f"{kind}:"
        return {k[len(pre):]: f"failed {e['count']} times (last: {e.get('last_outcome')}); see Action Items"
                for k, e in self._load().items() if k.startswith(pre) and e.get("count", 0) >= max_attempts}
