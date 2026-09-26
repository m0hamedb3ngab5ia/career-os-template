"""Applications per company: caps, rejection cooldown, posting close dates, deadline clusters.

Rules (config: targets.yaml `volume`, companies.yaml `company_caps`):

- Cap. At most `volume.max_per_company_per_90_days` applications per company in a rolling window, or the
  company's own `company_caps: {<Company>: {max, window_days, aliases}}`. A slot is used by every
  application submitted in the window (DateApplied; the outcome does not matter: the ATS still saw it) and
  by every reservation (queued / prepared / needs_review: materials exist, submit pending) whose posting
  has not closed.
- Candidates. Jobs scored `prepare` and not yet reserved, plus jobs the gate deferred (`company_cap` /
  `cooldown`, from score.json or the `skipped` status note). A job skipped for anything else (dead
  posting, safety, by hand) never holds a slot.
- Similar roles only. Only roles in `targets.yaml categories.primary` or `secondary` compete for a slot;
  an excluded, unknown or other category never does (no spraying unrelated roles at one company).
- Ranking. Reservations keep their slots; the remaining slots go to candidates by fit (desc), then the
  earliest close date. The rest are deferred (`company_cap`) and compete again later.
- Cooldown. After a rejection, the company is paused for `volume.same_company_cooldown_days`. A selected
  role still goes ahead now, flagged urgent, when waiting would miss it: its posting closes before the
  cooldown ends. Unknown close date = wait.
- Deadline clusters. When two or more selected roles at one company close within
  `volume.deadline_cluster_days` of each other, all of them are urgent and go now (cooldown or not), so
  related applications land together. The cap still applies in every case.

Everything below `load_records` is pure: records in, dicts out, `today` passed in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from careeros.config import VOLUME_INTS, Settings, _check_company_caps, _check_volume, normalize_company
from careeros.models import Posting

# Statuses after a submit. Counted in the window by DateApplied; an active one with no date still counts.
SUBMITTED: tuple[str, ...] = ("applied", "screening", "interview", "offer", "rejected", "withdrawn", "ghosted")
ACTIVE_SUBMITTED: tuple[str, ...] = ("applied", "screening", "interview", "offer")
RESERVED: tuple[str, ...] = ("queued", "prepared", "needs_review")
# Skip reasons that only defer a job: `careeros company requeue` re-checks them.
DEFERRED_REASONS: tuple[str, ...] = ("company_cap", "cooldown")
# Other applications worth telling a recruiter about, most advanced first.
NOTE_STATUSES: tuple[str, ...] = ("interview", "screening", "applied", "prepared", "queued")
DEFAULT_WINDOW_DAYS = 90

# --- close dates -------------------------------------------------------------------------------------

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
           "oct": 10, "nov": 11, "dec": 12}
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
          r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?")
_DATE = (
    r"(?:(?P<iy>\d{4})-(?P<im>\d{1,2})-(?P<id>\d{1,2})"
    r"|(?P<na>\d{1,2})/(?P<nb>\d{1,2})/(?P<ny>\d{4}|\d{2})\b"
    rf"|(?P<m1>{_MONTH})\s+(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(?P<y1>\d{{4}}))?"
    rf"|(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<m2>{_MONTH})(?:,?\s+(?P<y2>\d{{4}}))?)"
)
# Phrases that introduce an application close date. "deadlines" (plural) is job-description noise.
_TRIGGER = (
    r"(?:apply\s+by"
    r"|applications?\s+(?:will\s+)?(?:close[sd]?|are\s+due|due|deadline)\b"
    r"|deadline\s+to\s+apply"
    r"|deadline\b"
    r"|clos(?:ing|e)\s+date"
    r"|accepting\s+applications\s+(?:until|through)"
    r"|(?:apply|submit\w*|applications?)\b[^.\n]{0,40}?no\s+later\s+than)"
)
_DEADLINE_RE = re.compile(_TRIGGER + r"[^.\n]{0,40}?" + _DATE, re.I)
_DATE_RE = re.compile(_DATE, re.I)
_META_KEY_RE = re.compile(r"deadline|clos(?:e|es|ing)\b", re.I)
_YEARLESS_SLACK = timedelta(days=31)  # a yearless date this far before the posting date means next year


def _build(m: re.Match[str], ref: date) -> date | None:
    g = m.groupdict()
    try:
        if g["iy"]:
            return date(int(g["iy"]), int(g["im"]), int(g["id"]))
        if g["na"]:
            a, b, y = int(g["na"]), int(g["nb"]), int(g["ny"])
            y = y + 2000 if y < 100 else y
            month, day = (b, a) if a > 12 else (a, b)  # US order unless the first number cannot be a month
            return date(y, month, day)
        name, day, year = (g["m1"], g["d1"], g["y1"]) if g["m1"] else (g["m2"], g["d2"], g["y2"])
        month = _MONTHS[name.lower().rstrip(".")[:3]]
        if year:
            return date(int(year), month, int(day))
        got = date(ref.year, month, int(day))
        return got if got >= ref - _YEARLESS_SLACK else date(ref.year + 1, month, int(day))
    except ValueError:
        return None


def parse_deadline_text(text: str, ref: date) -> date | None:
    """First explicit application deadline in `text` ("apply by", "applications close", "deadline",
    "closing date", "no later than", "accepting applications until" + a date). A date without a year is
    the next one on or after `ref` (the posting date), allowing a month of slack. None when absent."""
    for m in _DEADLINE_RE.finditer(text or ""):
        got = _build(m, ref)
        if got:
            return got
    return None


def _iso_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(v or ""))
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _posting_ref(p: Posting) -> date:
    for v in (p.first_published, p.posted_at, p.fetched_at):
        d = _iso_date(v)
        if d:
            return d
    return date.today()


def posting_closes_at(posting: Posting) -> date | None:
    """When a posting stops taking applications, if it says so; None when unknown.

    Order: `closes_at` already stored; the ATS field (Greenhouse `application_deadline`, or a Greenhouse
    custom metadata field named like "Application Deadline" / "Closing Date"); then the description text.
    Lever and Ashby job-board APIs have no deadline field, so only their text can carry one."""
    stored = _iso_date(posting.closes_at)
    if stored:
        return stored
    raw = posting.raw or {}
    got = _iso_date(raw.get("application_deadline"))
    if got:
        return got
    ref = _posting_ref(posting)
    meta = raw.get("metadata")
    if isinstance(meta, dict):
        for k, v in meta.items():
            if v and _META_KEY_RE.search(str(k)):
                got = _iso_date(v)
                if not got:
                    m = _DATE_RE.search(str(v))
                    got = _build(m, ref) if m else None
                if got:
                    return got
    text = posting.description_text
    if not text and posting.description_html:
        from careeros.scout.base import html_to_text

        text = html_to_text(posting.description_html)
    return parse_deadline_text(text, ref)


def closes_at_iso(posting: Posting) -> str | None:
    d = posting_closes_at(posting)
    return d.isoformat() if d else None


# --- config -------------------------------------------------------------------------------------------

@dataclass
class Policy:
    default_max: int = 2
    cooldown_days: int = 30
    cluster_days: int = 7
    caps: dict[str, tuple[int, int]] = field(default_factory=dict)   # canonical key -> (max, window_days)
    aliases: dict[str, str] = field(default_factory=dict)            # normalized name -> canonical key
    similar: frozenset[str] = frozenset()

    @classmethod
    def from_settings(cls, s: Settings) -> "Policy":
        volume = s.targets.get("volume")
        _check_volume(volume)
        raw_caps = s.companies.get("company_caps")
        _check_company_caps(raw_caps)
        vol = {k: (volume or {}).get(k, default) for k, (default, _) in VOLUME_INTS.items()}
        p = cls(default_max=int(vol["max_per_company_per_90_days"]),
                cooldown_days=int(vol["same_company_cooldown_days"]),
                cluster_days=int(vol["deadline_cluster_days"]))
        for name, cap in (raw_caps or {}).items():
            canon = normalize_company(str(name))
            p.aliases[canon] = canon
            for a in cap.get("aliases") or []:
                p.aliases[normalize_company(a)] = canon
            p.caps[canon] = (int(cap.get("max", p.default_max)), int(cap.get("window_days", DEFAULT_WINDOW_DAYS)))
        cats = s.targets.get("categories") or {}
        wanted = set(cats.get("primary") or []) | set(cats.get("secondary") or [])
        if not wanted:
            wanted = set(s.active_categories())
        excluded = set(cats.get("excluded") or []) | {
            k for k, v in s.categories.items() if isinstance(v, dict) and v.get("excluded")}
        p.similar = frozenset(wanted - excluded)
        return p

    def company_key(self, name: str) -> str:
        n = normalize_company(name or "")
        return self.aliases.get(n, n)

    def cap_for(self, company: str) -> tuple[int, int]:
        """(max applications, window in days) for this company."""
        return self.caps.get(self.company_key(company), (self.default_max, DEFAULT_WINDOW_DAYS))

    def is_similar(self, category: str | None) -> bool:
        return bool(category) and category in self.similar


# --- records --------------------------------------------------------------------------------------------

@dataclass
class JobRecord:
    job_id: str
    company: str
    title: str
    status: str
    fit: int | None = None
    category: str | None = None
    decision: str | None = None          # score.json decision (prepare | skip)
    skip_reason: str | None = None
    date_applied: date | None = None
    rejected_at: date | None = None
    closes_at: date | None = None


def _local_date(at: Any) -> date | None:
    try:
        dt = datetime.fromisoformat(str(at))
    except ValueError:
        return _iso_date(at)
    return (dt.astimezone() if dt.tzinfo else dt).date()


def _int(v: Any) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _deferral_note(hist: list[dict[str, Any]]) -> str | None:
    """The deferral reason of the latest `skipped` entry in status history, if its note names one.

    prepare-job Step 1b and apply-job record a gate deferral only as a status note that starts with the
    reason (`company_cap: ...`, `company cooldown: ...`); score.json may still say `decision: prepare`."""
    last = next((h for h in reversed(hist) if h.get("status") == "skipped"), None)
    note = str((last or {}).get("note") or "").strip().lower()
    note = note[len("company "):] if note.startswith("company ") else note
    head = re.split(r"[:\s]", note, maxsplit=1)[0]
    return head if head in DEFERRED_REASONS else None


def load_records(settings: Settings, store: Any = None, tracker: Any = None) -> list[JobRecord]:
    """One record per job dir (status.json, score.json, posting close date) with DateApplied from the
    tracker (else the first `applied` in status history) and the rejection date from status history
    (else the tracker's LastEmailDate). Tracker rows with no job dir (applied by hand) are included."""
    from careeros.store import Store
    from careeros.tracker import Tracker

    store = store or Store(settings)
    tr = tracker or Tracker(settings=settings)
    rows = {str(r["JobID"]): r for r in tr.list_jobs()} if tr.path.exists() else {}
    out: list[JobRecord] = []
    for jid in store.iter_job_ids():
        p = store.load_posting(jid)
        if not p:
            continue
        st = store._read(jid, "status.json") or {}
        sc = store._read(jid, "score.json") or {}
        status = st.get("status") or "found"
        hist = st.get("history") or []
        row = rows.pop(jid, None) or {}
        applied = _iso_date(row.get("DateApplied")) or next(
            (_local_date(h.get("at")) for h in hist if h.get("status") == "applied"), None)
        rejected = None
        if status == "rejected":
            rejected = next((_local_date(h.get("at")) for h in reversed(hist) if h.get("status") == "rejected"),
                            None) or _iso_date(row.get("LastEmailDate"))
        out.append(JobRecord(job_id=jid, company=p.company, title=p.title, status=status, fit=_int(sc.get("fit")),
                             category=sc.get("category"), decision=sc.get("decision"),
                             skip_reason=(_deferral_note(hist) if status == "skipped" else None)
                             or sc.get("skip_reason"), date_applied=applied, rejected_at=rejected,
                             closes_at=posting_closes_at(p)))
    for jid, row in rows.items():
        status = str(row.get("Status") or "found")
        out.append(JobRecord(job_id=jid, company=str(row.get("Company") or ""), title=str(row.get("Role") or ""),
                             status=status, fit=_int(row.get("Fit")), category=row.get("Category") or None,
                             date_applied=_iso_date(row.get("DateApplied")),
                             rejected_at=_iso_date(row.get("LastEmailDate")) if status == "rejected" else None))
    return out


# --- evaluation -----------------------------------------------------------------------------------------

def _counts(r: JobRecord, since: date) -> bool:
    if r.status not in SUBMITTED:
        return False
    if r.date_applied is None:
        return r.status in ACTIVE_SUBMITTED
    return r.date_applied >= since


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _competes(r: JobRecord) -> bool:
    """A candidate for a slot: scored `prepare` and not yet queued, or deferred by the gate (skipped as
    company_cap / cooldown, or requeued to `scored`). A job skipped for any other reason (dead posting,
    safety, manual) never holds a slot, whatever its score.json says."""
    deferred = r.skip_reason in DEFERRED_REASONS
    if r.status in ("found", "scored"):
        return r.decision == "prepare" or deferred
    return r.status == "skipped" and deferred


def _evaluate(company: str, records: Iterable[JobRecord], policy: Policy, today: date,
              include: str | None = None) -> dict[str, Any]:
    key = policy.company_key(company)
    recs = [r for r in records if policy.company_key(r.company) == key]
    mx, window = policy.cap_for(company)
    since = today - timedelta(days=window)
    submitted = [r for r in recs if _counts(r, since)]
    reserved = [r for r in recs if r.status in RESERVED]
    live_reserved = [r for r in reserved if not (r.closes_at and r.closes_at < today)]  # a closed one frees its slot
    pool = [r for r in recs if r.status not in SUBMITTED and r.status not in RESERVED
            and (r.job_id == include or _competes(r))]

    rejections = [r.rejected_at for r in recs if r.status == "rejected" and r.rejected_at]
    cd_end = max(rejections) + timedelta(days=policy.cooldown_days) if rejections and policy.cooldown_days else None
    if cd_end and cd_end <= today:
        cd_end = None

    def beats_cooldown(r: JobRecord) -> bool:
        return bool(cd_end and r.closes_at and r.closes_at < cd_end)

    entries: dict[str, dict[str, Any]] = {}
    selectable_reserved: list[JobRecord] = []
    selectable_pool: list[JobRecord] = []
    for r in reserved + pool:
        e = {"job_id": r.job_id, "title": r.title, "status": r.status, "category": r.category, "fit": r.fit,
             "closes_at": _iso(r.closes_at), "reserved": r.status in RESERVED, "selected": False,
             "allowed": False, "reason": "", "urgent": False, "until": None}
        entries[r.job_id] = e
        if r.category is None or r.fit is None:
            e["reason"] = "unscored"
        elif not policy.is_similar(r.category):
            e["reason"] = "not_similar"
        elif r.closes_at and r.closes_at < today:
            e["reason"] = "closed"
        else:
            (selectable_reserved if e["reserved"] else selectable_pool).append(r)

    def by_fit(r: JobRecord) -> tuple:
        return (-(r.fit or 0), r.closes_at or date.max, r.job_id)

    selectable_reserved.sort(key=by_fit)
    selectable_pool.sort(key=lambda r: (0 if beats_cooldown(r) else 1, *by_fit(r)))
    ordered = selectable_reserved + selectable_pool
    capacity = max(0, mx - len(submitted))
    selected, over = ordered[:capacity], ordered[capacity:]

    dated = sorted((r for r in selected if r.closes_at), key=lambda r: r.closes_at)  # type: ignore[arg-type,return-value]
    clustered = {a.job_id for a in dated for b in dated
                 if a is not b and abs((a.closes_at - b.closes_at).days) <= policy.cluster_days}  # type: ignore[operator]

    for r in selected:
        e = entries[r.job_id]
        e["selected"] = True
        urgent = beats_cooldown(r) or r.job_id in clustered
        if cd_end and not urgent:
            e.update(reason="cooldown", until=cd_end.isoformat())
        else:
            e.update(allowed=True, reason="ok", urgent=urgent)
    for r in over:
        entries[r.job_id]["reason"] = "company_cap"

    rest = sorted((e for e in entries.values() if e["reason"] in ("unscored", "not_similar", "closed")),
                  key=lambda e: (-(e["fit"] or 0), e["job_id"]))
    ranked = [entries[r.job_id] for r in ordered] + rest
    used = len(submitted) + len(live_reserved)
    return {
        "records": {r.job_id: r for r in recs},
        "ranked": ranked,
        "slots": {"company": company, "used": used, "allowed": mx, "remaining": max(0, mx - used),
                  "window_days": window, "submitted": len(submitted), "reserved": len(live_reserved),
                  "cooldown_until": _iso(cd_end)},
    }


def slots(company: str, *, records: Iterable[JobRecord], policy: Policy, today: date | None = None) -> dict[str, Any]:
    """{company, used, allowed, remaining, window_days, submitted, reserved, cooldown_until}."""
    return _evaluate(company, list(records), policy, today or date.today())["slots"]


def rank_candidates(company: str, *, records: Iterable[JobRecord], policy: Policy,
                    today: date | None = None) -> list[dict[str, Any]]:
    """This company's reserved and candidate roles, in slot order: reservations, then candidates by fit
    (during a cooldown, roles that close before it ends come first), then roles that cannot take a slot
    (unscored, not_similar, closed). Each: selected, allowed, reason, urgent, until, closes_at."""
    return _evaluate(company, list(records), policy, today or date.today())["ranked"]


def _detail(reason: str, e: dict[str, Any], sl: dict[str, Any], rec: JobRecord) -> str:
    used = f"{sl['used']}/{sl['allowed']} slots used at {rec.company} (window {sl['window_days']} days)"
    if reason == "ok":
        extra = ""
        if e.get("urgent"):
            extra = f"; urgent: closes {e['closes_at']}" if e.get("closes_at") else "; urgent"
        return used + extra
    if reason == "company_cap":
        return used + ("; higher-ranked roles at this company hold the remaining slots" if sl["remaining"] else "")
    if reason == "cooldown":
        return f"rejected by {rec.company} recently; cooldown until {e['until']} (no close date before then)"
    if reason == "not_similar":
        return f"category {rec.category} is not in targets.yaml categories.primary/secondary"
    if reason == "closed":
        return f"posting closed {e['closes_at']}"
    if reason == "unscored":
        return "no score.json category/fit yet; run score-job first"
    return f"already {rec.status}"


def gate(job_id: str, *, records: Iterable[JobRecord], policy: Policy, today: date | None = None) -> dict[str, Any]:
    """May this job be prepared / submitted now? KeyError when the job is unknown.

    {job_id, company, allowed, reason (ok | company_cap | cooldown | not_similar | closed | unscored |
    already_applied), urgent, closes_at, until, slots, action_note, detail}. `action_note` is the text to add
    to any Action Item for this job ("" unless urgent with a close date)."""
    records = list(records)
    rec = next((r for r in records if r.job_id == job_id), None)
    if rec is None:
        raise KeyError(job_id)
    today = today or date.today()
    ev = _evaluate(rec.company, records, policy, today, include=job_id)
    e = next((x for x in ev["ranked"] if x["job_id"] == job_id), None)
    if e is None:  # already submitted
        e = {"allowed": False, "reason": "already_applied", "urgent": False, "closes_at": _iso(rec.closes_at),
             "until": None}
    note = f"urgent: posting closes {e['closes_at']}; apply before then" if e["urgent"] and e["closes_at"] else ""
    return {"job_id": job_id, "company": rec.company, "allowed": e["allowed"], "reason": e["reason"],
            "urgent": e["urgent"], "closes_at": e["closes_at"], "until": e["until"], "slots": ev["slots"],
            "action_note": note, "detail": _detail(e["reason"], e, ev["slots"], rec)}


def order_jobs(jobs: list[dict[str, Any]], *, records: Iterable[JobRecord], policy: Policy,
               today: date | None = None) -> list[dict[str, Any]]:
    """`jobs list --order urgent`: urgent first, then the earliest close date, then fit. Adds `urgent` and
    `closes_at` to each job dict."""
    records = list(records)
    today = today or date.today()
    by_id = {r.job_id: r for r in records}
    flags: dict[str, dict[str, Any]] = {}
    done: set[str] = set()
    for j in jobs:
        r = by_id.get(j["job_id"])
        if r is None or policy.company_key(r.company) in done:
            continue
        done.add(policy.company_key(r.company))
        for e in _evaluate(r.company, records, policy, today)["ranked"]:
            flags[e["job_id"]] = e
    out = []
    for j in jobs:
        r = by_id.get(j["job_id"])
        e = flags.get(j["job_id"], {})
        out.append({**j, "urgent": bool(e.get("urgent")), "closes_at": _iso(r.closes_at) if r else None})
    return sorted(out, key=lambda j: (not j["urgent"], j["closes_at"] or "9999-99-99", -(j.get("fit") or 0),
                                      j["job_id"]))


# --- transparency ---------------------------------------------------------------------------------------

def active_applications(company: str, *, records: Iterable[JobRecord], exclude_job: str | None = None,
                        policy: Policy | None = None) -> list[dict[str, Any]]:
    """Other live applications at this company (applied / screening / interview, or queued / prepared),
    most advanced first."""
    key_of = policy.company_key if policy else (lambda n: normalize_company(n or ""))
    key = key_of(company)
    act = [r for r in records if r.job_id != exclude_job and r.status in NOTE_STATUSES and key_of(r.company) == key]
    act.sort(key=lambda r: (NOTE_STATUSES.index(r.status), r.title, r.job_id))
    return [{"job_id": r.job_id, "title": r.title, "status": r.status} for r in act]


def transparency_note(company: str, *, records: Iterable[JobRecord], exclude_job: str | None = None,
                      policy: Policy | None = None) -> str:
    """'Also active at <Company>: <role> (<status>), ... — mention these to the recruiter.' or ''."""
    act = active_applications(company, records=records, exclude_job=exclude_job, policy=policy)
    if not act:
        return ""
    return f"Also active at {company}: " + ", ".join(f"{a['title']} ({a['status']})" for a in act) + \
        " — mention these to the recruiter."


__all__ = ["JobRecord", "Policy", "posting_closes_at", "closes_at_iso", "parse_deadline_text", "load_records",
           "slots", "rank_candidates", "gate", "order_jobs", "active_applications", "transparency_note",
           "SUBMITTED", "RESERVED", "DEFERRED_REASONS"]
