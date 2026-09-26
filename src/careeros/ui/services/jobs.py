"""GET /api/jobs (the live table: filters, sort, paging over the index) and GET /api/jobs/{id} (Job detail, read
from the job's own files, which stay the source of truth)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from careeros.store import _is_finder_copy

SORTS = ("fit", "company", "status", "tier", "found_at", "applied_at", "updated_at")
DEFAULT_SORT = "-fit"
MAX_LIMIT = 1000
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
# Files Job detail shows in its own sections; everything else in the folder is listed as a document.
SECTION_FILES = {"posting.json", "status.json", "score.json", "safety.json", "qa.json", "contacts.json",
                 "apply_session.json", "log.md"}
LIST_FIELDS = ("job_id", "company", "title", "location", "ats", "url", "category", "fit", "tier", "status", "safety",
               "qa_passed", "qa_score", "found_at", "applied_at", "updated_at", "closes_at")


def _order(sort: str) -> str:
    desc = sort.startswith("-")
    col = sort.lstrip("-")
    if col not in SORTS:
        raise ValueError(f"sort must be one of {', '.join(SORTS)} (prefix - for descending), got {sort!r}")
    return f"({col} IS NULL), {col} {'DESC' if desc else 'ASC'}, company ASC, job_id ASC"


def _like(q: str) -> str:
    return "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_jobs(ix: Any, *, status: list[str] | None = None, tier: list[str] | None = None,
              safety: list[str] | None = None, category: list[str] | None = None, q: str | None = None,
              sort: str = DEFAULT_SORT, cursor: str | None = None, limit: int = 100) -> dict[str, Any]:
    where, params = [], []
    for col, vals in (("status", status), ("tier", tier), ("safety", safety), ("category", category)):
        if vals:
            where.append(f"{col} IN ({','.join('?' * len(vals))})")
            params.extend(vals)
    if q and q.strip():
        where.append("(LOWER(company) LIKE ? ESCAPE '\\' OR LOWER(title) LIKE ? ESCAPE '\\' "
                     "OR LOWER(location) LIKE ? ESCAPE '\\')")
        params.extend([_like(q.strip())] * 3)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    try:
        offset = int(cursor) if cursor else 0
    except ValueError:
        raise ValueError(f"cursor must come from next_cursor, got {cursor!r}") from None
    if offset < 0:
        raise ValueError("cursor must be >= 0")
    limit = max(1, min(int(limit), MAX_LIMIT))
    total = ix.query(f"SELECT COUNT(*) AS n FROM jobs{clause}", params)[0]["n"]
    rows = ix.query(f"SELECT {', '.join(LIST_FIELDS)} FROM jobs{clause} ORDER BY {_order(sort)} LIMIT ? OFFSET ?",
                    [*params, limit, offset])
    nxt = offset + len(rows)
    return {"items": rows, "total": total, "next_cursor": str(nxt) if nxt < total else None}


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _files(d: Path, skip: set[str] | None = None) -> list[dict[str, Any]]:
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.name.startswith(".") or _is_finder_copy(f.name) or f.name.endswith(".tmp"):
            continue
        if skip and f.name in skip:
            continue
        st = f.stat()
        out.append({"name": f.name, "size": st.st_size, "modified": st.st_mtime})
    return out


def job_dir_for(settings: Any, job_id: str) -> Path | None:
    """The job's folder, or None for an id that is malformed (path tricks) or has no posting."""
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id) or _is_finder_copy(job_id):
        return None
    d = Path(settings.paths["jobs_dir"]) / job_id
    return d if (d / "posting.json").is_file() else None


def job_detail(settings: Any, ix: Any, job_id: str) -> dict[str, Any] | None:
    d = job_dir_for(settings, job_id)
    if d is None:
        return None
    rows = ix.query(f"SELECT {', '.join(LIST_FIELDS)} FROM jobs WHERE job_id = ?", (job_id,))
    posting = _json(d / "posting.json") or {}
    posting.pop("description_html", None)
    posting.pop("raw", None)
    status = _json(d / "status.json") or {}
    qa = _json(d / "qa.json")
    contacts = (_json(d / "contacts.json") or {}).get("contacts")
    submitted = d / "submitted"
    try:
        log = (d / "log.md").read_text(encoding="utf-8")
    except OSError:
        log = ""
    return {
        "job": rows[0] if rows else None,
        "posting": posting,
        "status": status.get("status"),
        "history": status.get("history") if isinstance(status.get("history"), list) else [],
        "score": _json(d / "score.json"),
        "safety": _json(d / "safety.json"),
        "qa": qa if isinstance(qa, dict) else None,      # the qa-review skill's qa.json as written
        "documents": _files(d, SECTION_FILES),
        "submitted": sorted(p.name for p in submitted.iterdir() if p.is_dir()) if submitted.is_dir() else [],
        "apply_session": _json(d / "apply_session.json"),
        "screenshots": _files(d / "screenshots"),
        "contacts": contacts if isinstance(contacts, list) else [],
        "log": log,
    }
