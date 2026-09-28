"""GET /api/jobs (the live table: filters, sort, paging over the index) and GET /api/jobs/{id} (Job detail, read
from the job's own files, which stay the source of truth)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from typing_extensions import TypedDict

from careeros.store import _is_finder_copy

SORTS = ("fit", "company", "location", "status", "tier", "found_at", "applied_at", "updated_at")
DEFAULT_SORT = "-fit"
MAX_LIMIT = 1000
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
# Files Job detail shows in its own sections; everything else in the folder is listed as a document.
SECTION_FILES = {"posting.json", "status.json", "score.json", "safety.json", "qa.json", "contacts.json",
                 "apply_session.json", "log.md"}
# The documents Job detail shows prominently, in this order; every other file in the folder is under "All files".
KEY_DOCUMENTS = ("resume.pdf", "cover_letter.pdf", "cover_letter.md", "resume.txt", "cover_letter.txt")
# Excel-style column filters (docs/UI.md "Jobs"): value lists per column, min..max ranges, inclusive ISO date ranges.
# GET /api/jobs/facets counts a column's values under every other active filter.
VALUE_COLUMNS = ("company", "location", "status", "tier", "category", "safety", "ats", "qa_passed")
NUMBER_COLUMNS = ("fit", "qa_score")
DATE_COLUMNS = ("found_at", "applied_at", "closes_at")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LIST_FIELDS = ("job_id", "company", "title", "location", "ats", "url", "category", "fit", "tier", "status", "safety",
               "qa_passed", "qa_score", "found_at", "applied_at", "updated_at", "closes_at")


# Response shapes (OpenAPI -> ui/src/api/schema.gen.ts). Index columns are nullable (qa_passed is the index's 0/1
# INTEGER). The job's own files (posting.json, score.json, ...) are returned as written, so they stay open mappings
# (a typed shape would drop keys it does not list); the UI describes their contents by hand.
class JobRow(TypedDict):
    job_id: str
    company: str | None
    title: str | None
    location: str | None
    ats: str | None
    url: str | None
    category: str | None
    fit: int | None
    tier: str | None
    status: str | None
    safety: str | None
    qa_passed: int | None
    qa_score: float | None
    found_at: str | None
    applied_at: str | None
    updated_at: str | None
    closes_at: str | None


class JobListItem(JobRow):
    next_action: str | None      # the highest-priority open Action Item's "what"


class JobsPage(TypedDict):
    items: list[JobListItem]
    total: int
    next_cursor: str | None


class FacetValue(TypedDict):
    value: str | int | float | None
    count: int


class JobFacets(TypedDict):
    field: str
    values: list[FacetValue]


class JobsTab(TypedDict):
    key: str
    label: str
    count: int


class JobsTabs(TypedDict):
    tabs: list[JobsTab]


class FileEntry(TypedDict):
    name: str
    size: int
    modified: float              # epoch seconds


class ContactPolicy(TypedDict):
    name: str
    role: str
    manual: bool
    reason: str | None
    detail: str


class Registry(TypedDict):
    verified: dict[str, Any] | None
    flagged: dict[str, Any] | None


class ActivityEntry(TypedDict):
    at: str
    component: str
    message: str                 # the raw log.md line body
    label: str                   # plain-English version of `message` (humanize_activity)


class JobDetail(TypedDict):
    job: JobRow | None
    posting: dict[str, Any]
    status: str | None
    history: list[dict[str, Any]]
    score: dict[str, Any] | None
    safety: dict[str, Any] | None
    qa: dict[str, Any] | None
    documents: list[FileEntry]   # KEY_DOCUMENTS that exist, in that order
    other_files: list[FileEntry]
    submitted: list[str]
    apply_session: dict[str, Any] | None
    screenshots: list[FileEntry]
    contacts: list[dict[str, Any]]
    log: str
    override: str | None
    registry: Registry
    outreach: dict[str, Any] | None
    contacts_policy: list[ContactPolicy]
    activity: list[ActivityEntry]


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
           category: list[str] | None = None, q: str | None = None, location: str | None = None,
           tab: str | None = None, closed: list[str] | None = None,
           job_ids: list[str] | None = None, values: dict[str, list[str]] | None = None,
           ranges: dict[str, tuple[Any, Any]] | None = None) -> tuple[str, list[Any]]:
    """`values` = {column: [exact values]} for VALUE_COLUMNS; `ranges` = {column: (lo, hi)} for NUMBER_COLUMNS
    (numbers, either side None) and DATE_COLUMNS (ISO dates, inclusive on both sides)."""
    where, params = [], []
    merged: dict[str, list[str]] = {k: list(v) for k, v in (values or {}).items() if v}
    for col, vals in (("status", status), ("tier", tier), ("safety", safety), ("category", category)):
        if vals:
            merged.setdefault(col, []).extend(vals)
    for col, vals in merged.items():
        if col not in VALUE_COLUMNS:
            raise ValueError(f"unknown filter column {col!r}; valid: {', '.join(VALUE_COLUMNS)}")
        where.append(f"{col} IN ({','.join('?' * len(vals))})")
        params.extend(vals)
    for col, (lo, hi) in (ranges or {}).items():
        if col in NUMBER_COLUMNS:
            for side, v, op in (("min", lo, ">="), ("max", hi, "<=")):
                if v is None or v == "":
                    continue
                try:
                    num = float(v)
                except (TypeError, ValueError):
                    raise ValueError(f"{col}_{side} must be a number, got {v!r}") from None
                where.append(f"{col} {op} ?")
                params.append(num)
        elif col in DATE_COLUMNS:
            for side, v, op in (("from", lo, ">= ?"), ("to", hi, "< date(?, '+1 day')")):
                if v is None or v == "":
                    continue
                if not isinstance(v, str) or not _ISO_DATE.match(v):
                    raise ValueError(f"{col[:-3]}_{side} must be an ISO date (YYYY-MM-DD), got {v!r}")
                where.append(f"{col} {op}")
                params.append(v)
        else:
            raise ValueError(f"unknown range column {col!r}; valid: {', '.join(NUMBER_COLUMNS + DATE_COLUMNS)}")
    if q and q.strip():
        where.append("(LOWER(company) LIKE ? ESCAPE '\\' OR LOWER(title) LIKE ? ESCAPE '\\' "
                     "OR LOWER(location) LIKE ? ESCAPE '\\')")
        params.extend([_like(q.strip())] * 3)
    if location and location.strip():
        where.append("LOWER(location) LIKE ? ESCAPE '\\'")
        params.append(_like(location.strip()))
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
              location: str | None = None, sort: str = DEFAULT_SORT, cursor: str | None = None, limit: int = 100,
              tab: str | None = None, closed: list[str] | None = None, values: dict[str, list[str]] | None = None,
              ranges: dict[str, tuple[Any, Any]] | None = None) -> JobsPage:
    clause, params = _where(status=status, tier=tier, safety=safety, category=category, q=q, location=location,
                            tab=tab, closed=closed, values=values, ranges=ranges)
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


def tabs(ix: Any, closed: list[str], q: str | None = None, location: str | None = None, **filters: Any) -> list[JobsTab]:
    out: list[JobsTab] = []
    for key, label in TABS:
        clause, params = _where(q=q, location=location, tab=key, closed=closed, **filters)
        out.append({"key": key, "label": label, "count": ix.query(f"SELECT COUNT(*) AS n FROM jobs{clause}", params)[0]["n"]})
    return out


def facets(ix: Any, field: str, *, closed: list[str], **filters: Any) -> JobFacets:
    """Distinct values of one column with counts, under every filter except the one on that column (so the
    checklist still shows what else could be picked, as Excel does). NULLs are left out."""
    if field not in VALUE_COLUMNS:
        raise ValueError(f"unknown facet field {field!r}; valid: {', '.join(VALUE_COLUMNS)}")
    filters = dict(filters)
    filters.pop(field, None)
    values = {k: v for k, v in (filters.pop("values", None) or {}).items() if k != field}
    clause, params = _where(closed=closed, values=values, **filters)
    clause = f"{clause} AND " if clause else " WHERE "
    rows = ix.query(f"SELECT {field} AS value, COUNT(*) AS count FROM jobs{clause}{field} IS NOT NULL "
                    f"GROUP BY {field} ORDER BY count DESC, value ASC", params)
    return {"field": field, "values": [{"value": r["value"], "count": r["count"]} for r in rows]}


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


def _obj(path: Path) -> dict[str, Any] | None:
    """A JSON file that must hold an object; anything else (missing, broken, a list) reads as None."""
    v = _json(path)
    return v if isinstance(v, dict) else None


def _files(d: Path, skip: set[str] | None = None) -> list[FileEntry]:
    if not d.is_dir():
        return []
    out: list[FileEntry] = []
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
    root = Path(settings.paths["jobs_dir"])
    d = root / job_id
    try:  # a symlinked job folder must stay inside jobs_dir
        inside = d.resolve().is_relative_to(root.resolve())
    except OSError:
        return None
    return d if inside and (d / "posting.json").is_file() else None


def job_detail(settings: Any, ix: Any, job_id: str) -> JobDetail | None:
    d = job_dir_for(settings, job_id)
    if d is None:
        return None
    rows = ix.query(f"SELECT {', '.join(LIST_FIELDS)} FROM jobs WHERE job_id = ?", (job_id,))
    posting = _obj(d / "posting.json") or {}
    posting.pop("description_html", None)
    posting.pop("raw", None)
    status = _obj(d / "status.json") or {}
    qa = _obj(d / "qa.json")
    contacts = (_obj(d / "contacts.json") or {}).get("contacts")
    submitted = d / "submitted"
    try:
        log = (d / "log.md").read_text(encoding="utf-8")
    except OSError:
        log = ""
    score = _obj(d / "score.json")
    if score is not None and isinstance(score.get("reasons"), list):
        score = {**score, "reasons": humanize_reasons(score["reasons"])}
    files = _files(d, SECTION_FILES)
    by_name = {f["name"]: f for f in files}
    return {
        "job": rows[0] if rows else None,
        "posting": posting,
        "status": status["status"] if isinstance(status.get("status"), str) else None,
        "history": [h for h in status.get("history") or [] if isinstance(h, dict)]
        if isinstance(status.get("history"), list) else [],
        "score": score,
        "safety": _obj(d / "safety.json"),
        "qa": qa,                                        # the qa-review skill's qa.json as written
        "documents": [by_name[n] for n in KEY_DOCUMENTS if n in by_name],
        "other_files": [f for f in files if f["name"] not in KEY_DOCUMENTS],
        "submitted": sorted(p.name for p in submitted.iterdir() if p.is_dir()) if submitted.is_dir() else [],
        "apply_session": _obj(d / "apply_session.json"),
        "screenshots": _files(d / "screenshots"),
        "contacts": [c for c in contacts if isinstance(c, dict)] if isinstance(contacts, list) else [],
        "log": log,
        "override": _override(settings, job_id),
        "registry": _registry(settings, str(posting.get("company") or ""), str(posting.get("apply_url") or
                                                                              posting.get("url") or "")),
        "outreach": _obj(d / "outreach.json"),
        "contacts_policy": _contacts_policy(settings, contacts if isinstance(contacts, list) else []),
        "activity": parse_log(log),
    }


_LOG_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?) \[([^\]]*)\] (.*)$")


def parse_log(log: str) -> list[ActivityEntry]:
    """log.md lines (`- 2026-09-24 18:04:00 [component] message`), newest first; other lines are skipped."""
    out: list[ActivityEntry] = []
    for line in log.splitlines():
        m = _LOG_LINE.match(line.strip())
        if m:
            out.append({"at": m[1].replace(" ", "T"), "component": m[2], "message": m[3],
                        "label": humanize_activity(m[2], m[3])})
    return out[::-1]


_REASON_TAIL = re.compile(r"\s*->\s*[A-Za-z_][\w.]*(?:\s+[-+]?\d+(?:\.\d+)?(?:\s*/\s*\d+)?)?\s*$")


def humanize_reasons(reasons: list[Any]) -> list[str]:
    """Score reasons as sentences: `skills 3/6 matched (...) -> skills_overlap 20/40` -> `Skills 3/6 matched (...).`.

    Old score.json files hold lowercase fragments with the scoring key appended; newer ones are already sentences
    and pass through unchanged apart from whitespace."""
    out: list[str] = []
    for r in reasons:
        if not isinstance(r, str):
            continue
        text = " ".join(_REASON_TAIL.sub("", r).split())
        if not text:
            continue
        text = text[0].upper() + text[1:]
        if text[-1] not in ".!?":
            text += "."
        out.append(text)
    return out


def _kv(message: str) -> dict[str, str]:
    """`key=value` pairs in a skill's log line."""
    return dict(re.findall(r"(\w+)=(\S+)", message))


def _words(code: str) -> str:
    return code.replace("_", " ").replace("-", " ").strip()


def _plural(n: str, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == "1" else "s")


def _cap(text: str) -> str:
    text = " ".join(text.split())
    return text[0].upper() + text[1:] if text else text


def humanize_activity(component: str, message: str) -> str:  # noqa: C901 - one branch per known log line shape
    """A plain-English label for a log.md line; unknown shapes come back as the message with a capital letter."""
    msg = message.strip()
    kv = _kv(msg)
    m = re.match(r"^status -> (\S+)(?::\s*(.*))?$", msg)
    if m:  # store.set_status / tracker.set_status
        return f"Status changed to {_words(m[1])}" + (f": {m[2]}" if m[2] else "")
    m = re.match(r"^qa \(deterministic\) (pass|fail): (\d+) hard, (\d+) soft$", msg)
    if m:  # ui rerun QA
        return f"QA re-run {'passed' if m[1] == 'pass' else 'failed'}: {_plural(m[2], 'hard fail')}, {_plural(m[3], 'soft fail')}"
    if component == "qa-review" and "pass" in kv:
        verdict = "passed" if kv["pass"].lower() == "true" else "failed"
        extra = [f"mean {kv['mean']}" if "mean" in kv else "",
                 _plural(kv["hard_fails"], "hard fail") if "hard_fails" in kv else "",
                 f"next: {_words(kv['next'])}" if "next" in kv else ""]
        return f"QA review {verdict} (" + ", ".join(e for e in extra if e) + ")" if any(extra) else f"QA review {verdict}"
    if component == "score-job" and "fit" in kv:
        parts = [f"fit {kv['fit']}", f"tier {kv['tier']}" if "tier" in kv else "",
                 f"decision {_words(kv['decision'])}" if "decision" in kv else ""]
        return "Scored: " + ", ".join(p for p in parts if p)
    if component == "prepare-job" and "status" in kv:
        parts = [f"status {_words(kv['status'])}", f"tier {kv['tier']}" if "tier" in kv else "",
                 f"fit {kv['fit']}" if "fit" in kv else "",
                 ("QA passed" if kv["qa_pass"].lower() == "true" else "QA failed") if "qa_pass" in kv else ""]
        return "Prepared: " + ", ".join(p for p in parts if p)
    if component == "tailor-resume" and "bullets" in kv:
        parts = [_plural(kv["bullets"], "bullet"), _plural(kv["words"], "word") if "words" in kv else "",
                 _plural(kv["pages"], "page") if "pages" in kv else ""]
        return "Résumé tailored (" + ", ".join(p for p in parts if p) + ")"
    if component == "write-cover-letter" and "words" in kv:
        parts = [_plural(kv["words"], "word"), _plural(kv["facts"], "company fact") if "facts" in kv else ""]
        return "Cover letter written (" + ", ".join(p for p in parts if p) + ")"
    m = re.match(r"^(\d+) contacts? drafted", msg)
    if m and component == "draft-outreach":
        return f"Outreach drafted for {_plural(m[1], 'contact')}"
    m = re.match(r"^(\d+) contacts?\b", msg)
    if m and component == "find-contacts":
        return f"Found {_plural(m[1], 'contact')}"
    m = re.match(r'^"(.*)" type=', msg)
    if m and component == "answer-question":
        return f"Answered a form question: \u201c{m[1]}\u201d" + (" (needs review)" if kv.get("needs_review", "").lower() == "true" else "")
    m = re.match(r"^(\S+) from (\S+) (\S+) -> status (\S+)", msg)
    if m and component == "inbox-sync":
        return f"Inbox: {_words(m[1])} from {m[2]}; status set to {_words(m[4])}"
    m = re.match(r"^found via (\S+?)/(\S+?);", msg)
    if m:  # scout
        return f"Found by scout on {m[1]}"
    m = re.match(r"^(\S+) session (\S+): (.*?) \((\d+) steps?", msg)
    if m:  # applier
        return f"Apply session {_words(m[2])} on {m[1]}: {m[3]} ({_plural(m[4], 'step')})"
    m = re.match(r"^safety (pass|block|skip|review)(?::\s*(.*))?$", msg)
    if m:
        return f"Safety check: {m[1]}" + (f" ({m[2]})" if m[2] else "")
    if msg.startswith("frozen as-submitted copy"):
        return "Submitted copy frozen"
    m = re.match(r"^\[(\w+)/\w+/\w+\] (.*)$", msg)
    if m and component == "action":
        return f"Action item added ({_words(m[1])}): {m[2]}"
    m = re.match(r"^(?:job )?locked(?: by (\S+))?", msg)
    if m:
        return "Job locked" + (f" by {m[1]}" if m[1] else "")
    if re.match(r"^(?:job )?unlocked", msg):
        return "Job unlocked"
    m = re.match(r"^attempt (\d+) (\S+) \S+ -> (\S+)(?::\s*(.*))?$", msg)
    if m:  # runner attempt line (run logs; here for jobs whose log mirrors it)
        return f"Run attempt {m[1]} ({m[2]}) {_words(m[3])}" + (f": {m[4]}" if m[4] else "")
    m = re.match(r"^skill (\S+) (start|started|done|finished|failed)\b(.*)$", msg)
    if m:
        verb = {"start": "started", "started": "started", "done": "finished", "finished": "finished", "failed": "failed"}[m[2]]
        return f"{m[1]} {verb}{m[3]}"
    m = re.match(r"^tracker sync(?:ed)?\b(.*)$", msg)
    if m:
        return "Tracker synced" + m[1]
    return _cap(msg)


def _override(settings: Any, job_id: str) -> str | None:
    from careeros.tracker import Tracker

    try:
        tr = Tracker(settings=settings)
        row = tr.get_job(job_id) if tr.path.exists() else None
    except Exception:  # noqa: BLE001 - a locked or broken workbook must not break Job detail
        return None
    v = (row or {}).get("Override")
    return str(v).strip() if v not in (None, "") else None


def _registry(settings: Any, company: str, url: str) -> Registry:
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


def _contacts_policy(settings: Any, contacts: list[Any]) -> list[ContactPolicy]:
    from careeros.outreach import OutreachPolicy, check_contacts

    rows = check_contacts({"contacts": [c for c in contacts if isinstance(c, dict)]},
                          OutreachPolicy.from_settings(settings))
    return [{"name": str(r["name"] or ""), "role": str(r["role"] or ""), "manual": bool(r["manual"]),
             "reason": r["reason"], "detail": str(r["detail"] or "")} for r in rows]
