"""Writes on one job from the UI. Set status goes through `tracker.set_status_both` (status.json + the tracker,
queued when Excel holds the workbook), the same path as `careeros job status`.

Shared by the Pipeline board (drag / Move to…) and the Jobs table / Job detail (Set status).
"""
from __future__ import annotations

from typing import Any

from careeros.models import STATUSES

MAX_NOTE = 200


def set_status(settings: Any, job_id: str, status: str, note: str | None = None) -> dict[str, Any]:
    """Returns {job_id, status, previous}. ValueError on an unknown status, LookupError on an unknown job."""
    from careeros.store import Store
    from careeros.tracker import set_status_both
    from careeros.ui.services.jobs import job_dir_for

    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}, got {status!r}")
    if job_dir_for(settings, job_id) is None:
        raise LookupError(f"no job {job_id!r}")
    previous = Store(settings).get_status(job_id)
    note = (note or "").strip()[:MAX_NOTE] or "set in careeros ui"
    set_status_both(settings, job_id, status, note)
    return {"job_id": job_id, "status": status, "previous": previous}
