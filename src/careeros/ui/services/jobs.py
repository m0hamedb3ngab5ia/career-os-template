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


# Jobs screen tabs: key -> label. "active" leaves out the closed statuses (config `ui.pipeline`), "applied" is
# everything after applying.
TABS = (("active", "Active"), ("review", "Needs review"), ("applied", "Applied"), ("tier_a", "Tier A"), ("all", "All"))
APPLIED_STATUSES = ("applied", "screening", "interview", "offer")
_NEXT_ACTION = ("(SELECT a.what FROM action_items a WHERE a.job_id = jobs.job_id AND a.done = 0 ORDER BY "
                "CASE a.priority WHEN 'H' THEN 0 WHEN 'M' THEN 1 WHEN 'L' THEN 2 ELSE 3 END, a.created LIMIT 1)")
# Export columns: key -> header. JobID always comes first.
EXPORT_COLUMNS = {"company": "Company", "title": "Role", "location": "Location", "tier": "Tier", "fit": "Fit",
                  "status": "Status", "safety": "Safety", "qa_score": "QA", "ats": "ATS", "found_at": "Found",
                  "applied_at": "Applied", "next_action": "Next action", "category": "Category", "url": "URL",
                  "closes_at": "Closes"}
DEFAULT_EXPORT = ("company", "title", "location", "tier", "fit", "status", "safety", "qa_score", "ats", "found_at",
                  "applied_at", "next_action", "url")
MAX_EXPORT = 5000


def _tab_clause(tab: str | None, closed: list[str] | None) -> tuple[str | None, list[Any]]:
    if tab in (None, "", "all"):
        return None, []
    if tab == "active":
        cl = list(closed or [])
        return (f"(status IS NULL OR status NOT IN ({','.join('?' * len(cl))}))", cl) if cl else (None, [])
    if tab == "review":
        return "status = ?", ["needs_review"]
    if tab == "applied":
        return f"status IN ({','.join('?' * len(APPLIED_STATUSES))})", list(APPLIED_STATUSES)
    if tab == "tier_a":
        return "tier = ?", ["A"]
    raise ValueError(f"tab must be one of {', '.join(k for k, _ in TABS)}, got {tab!r}")


def _where(*, status: list[str] | None = None, tier: list[str] | None = None, safety: list[str] | None = None,
           category: list[str] | None = None, q: str | None = None, tab: str | None = None,
           closed: list[str] | None = None, job_ids: list[str] | None = None) -> tuple[str, list[Any]]:
    where, params = [], []
    for col, vals in (("status", status), ("tier", tier), ("safety", safety), ("category", category)):
        if vals:
            where.append(f"{col} IN ({','.join('?' * len(vals))})")
            params.extend(vals)
    if q and q.strip():
        where.append("(LOWER(company) LIKE ? ESCAPE '\\' OR LOWER(title) LIKE ? ESCAPE '\\' "
                     "OR LOWER(location) LIKE ? ESCAPE '\\')")
        params.extend([_like(q.strip())] * 3)
    clause, extra = _tab_clause(tab, closed)
    if clause:
        where.append(clause)
        params.extend(extra)
    if job_ids is not None:
        bad = [j for j in job_ids if not isinstance(j, str) or not JOB_ID_RE.match(j)]
        if bad:
            raise ValueError(f"not a job id: {bad[0]!r}")
        where.append(f"job_id IN ({','.join('?' * len(job_ids))})" if job_ids else "0")
        params.extend(job_ids)
    return (f" WHERE {' AND '.join(where)}" if where else ""), params


def list_jobs(ix: Any, *, status: list[str] | None = None, tier: list[str] | None = None,
              safety: list[str] | None = None, category: list[str] | None = None, q: str | None = None,
              sort: str = DEFAULT_SORT, cursor: str | None = None, limit: int = 100, tab: str | None = None,
              closed: list[str] | None = None) -> dict[str, Any]:
    clause, params = _where(status=status, tier=tier, safety=safety, category=category, q=q, tab=tab, closed=closed)
    try:
        offset = int(cursor) if cursor else 0
    except ValueError:
        raise ValueError(f"cursor must come from next_cursor, got {cursor!r}") from None
    if offset < 0:
        raise ValueError("cursor must be >= 0")
    limit = max(1, min(int(limit), MAX_LIMIT))
    total = ix.query(f"SELECT COUNT(*) AS n FROM jobs{clause}", params)[0]["n"]
    rows = ix.query(f"SELECT {', '.join(LIST_FIELDS)}, {_NEXT_ACTION} AS next_action FROM jobs{clause} "
                    f"ORDER BY {_order(sort)} LIMIT ? OFFSET ?", [*params, limit, offset])
    nxt = offset + len(rows)
    return {"items": rows, "total": total, "next_cursor": str(nxt) if nxt < total else None}


def tabs(ix: Any, closed: list[str], q: str | None = None) -> list[dict[str, Any]]:
    out = []
    for key, label in TABS:
        clause, params = _where(q=q, tab=key, closed=closed)
        out.append({"key": key, "label": label, "count": ix.query(f"SELECT COUNT(*) AS n FROM jobs{clause}", params)[0]["n"]})
    return out


def _cell(v: Any) -> Any:
    """Board text is data, never a formula: a leading = + - @ (or tab/CR) gets a quote prefix."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def export_xlsx(ix: Any, *, job_ids: list[str] | None = None, columns: list[str] | None = None,
                sort: str = DEFAULT_SORT, closed: list[str] | None = None, **filters: Any) -> bytes:
    """The selected (job_ids) or filtered rows as a new workbook in memory; the tracker is never touched."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font

    cols = list(columns) if columns else list(DEFAULT_EXPORT)
    unknown = [c for c in cols if c not in EXPORT_COLUMNS and c != "job_id"]
    if unknown:
        raise ValueError(f"unknown column {unknown[0]!r}; valid: {', '.join(EXPORT_COLUMNS)}")
    cols = [c for c in cols if c != "job_id"]
    clause, params = _where(job_ids=job_ids, closed=closed, **filters)
    rows = ix.query(f"SELECT {', '.join(LIST_FIELDS)}, {_NEXT_ACTION} AS next_action FROM jobs{clause} "
                    f"ORDER BY {_order(sort)} LIMIT ?", [*params, MAX_EXPORT])
    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"
    ws.append(["JobID", *(EXPORT_COLUMNS[c] for c in cols)])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for r in rows:
        ws.append([r["job_id"], *(_cell(r.get(c)) for c in cols)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


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
        "override": _override(settings, job_id),
        "registry": _registry(settings, str(posting.get("company") or ""), str(posting.get("apply_url") or
                                                                              posting.get("url") or "")),
        "outreach": _json(d / "outreach.json"),
        "contacts_policy": _contacts_policy(settings, contacts if isinstance(contacts, list) else []),
        "activity": parse_log(log),
    }


_LOG_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?) \[([^\]]*)\] (.*)$")


def parse_log(log: str) -> list[dict[str, Any]]:
    """log.md lines (`- 2026-09-24 18:04:00 [component] message`), newest first; other lines are skipped."""
    out = []
    for line in log.splitlines():
        m = _LOG_LINE.match(line.strip())
        if m:
            out.append({"at": m[1].replace(" ", "T"), "component": m[2], "message": m[3]})
    return out[::-1]


def _override(settings: Any, job_id: str) -> str | None:
    from careeros.tracker import Tracker

    try:
        tr = Tracker(settings=settings)
        row = tr.get_job(job_id) if tr.path.exists() else None
    except Exception:  # noqa: BLE001 - a locked or broken workbook must not break Job detail
        return None
    v = (row or {}).get("Override")
    return str(v).strip() if v not in (None, "") else None


def _registry(settings: Any, company: str, url: str) -> dict[str, Any]:
    from careeros.config import normalize_company
    from careeros.safety import registry

    try:
        flagged = registry.is_flagged(registry.load(registry.default_path(settings)), company, url)
        key = normalize_company(company)
        verified = next((e for e in registry.load(registry.verified_path(settings))
                         if key and normalize_company(str(e.get("company") or "")) == key), None)
    except Exception:  # noqa: BLE001 - broken YAML: show nothing rather than fail the page
        return {"verified": None, "flagged": None}
    return {"verified": verified, "flagged": flagged}


def _contacts_policy(settings: Any, contacts: list[Any]) -> list[dict[str, Any]]:
    from careeros.outreach import OutreachPolicy, check_contacts

    return check_contacts({"contacts": [c for c in contacts if isinstance(c, dict)]},
                          OutreachPolicy.from_settings(settings))
