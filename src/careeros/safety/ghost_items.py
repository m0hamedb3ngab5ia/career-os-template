"""Ghost Action Items. A ghost flag only matters when it can change a decision, so an item is raised only for a
dream-company job that is scored, passes its hard filters and meets `thresholds.min_fit_to_prepare` (a prepare
decision), and one item covers all such jobs of a company. Never raised at safety-check time."""
from __future__ import annotations

from datetime import date
from typing import Any

from careeros.config import Settings, normalize_company
from careeros.models import Posting
from careeros.safety.ghost import check_ghost, load_signals
from careeros.safety.scam import apply_levels
from careeros.store import Store
from careeros.tracker import Tracker, add_action

TYPE = "ghost_job"
_OPEN_STATUSES = {"found", "scored", "queued", "prepared", "needs_review"}


def _review_reasons(s: Settings, store: Store, p: Posting, today: date | None, hist: dict[str, Any]) -> list[str]:
    flags = apply_levels(check_ghost(p, store.history_for(p), load_signals(s), s, today=today, company_history=hist), s)
    return [f.detail for f in flags if f.code.startswith("GHOST_") and f.level == "review"]


def _worthy(s: Settings, store: Store, job_id: str) -> Posting | None:
    p = store.load_posting(job_id)
    raw = store._read(job_id, "score.json") or {}
    if raw.get("decision", "prepare") != "prepare" or (store.get_status(job_id) or "found") not in _OPEN_STATUSES:
        return None  # skipped by the skill (e.g. a non-preferred-location threshold) or already past applying
    try:
        sc = store.load_score(job_id)
    except ValueError:
        return None
    floor = int((s.targets.get("thresholds") or {}).get("min_fit_to_prepare", 70))
    if not (p and sc and sc.passes and sc.fit >= floor and s.is_dream(p.company)):
        return None
    return p


def _flagged(s: Settings, today: date | None) -> dict[str, list[tuple[Posting, list[str]]]]:
    store, hist = Store(s), Store(s).load_history()
    out: dict[str, list[tuple[Posting, list[str]]]] = {}
    for jid in store.iter_job_ids():
        p = _worthy(s, store, jid)
        why = _review_reasons(s, store, p, today, hist) if p else []
        if p and why:
            out.setdefault(normalize_company(p.company), []).append((p, why))
    return out


def raise_ghost_items(s: Settings, today: date | None = None) -> list[str]:
    """Add one open item per company that has flagged prepare-worthy jobs and no open ghost item yet."""
    tr = Tracker(settings=s)
    open_items = {normalize_company(str(i.get("Company") or "")): i for i in tr.list_action_items(open_only=True)
                  if i.get("Type") == TYPE and not i.get("JobID")}
    lines = []
    for key, jobs in _flagged(s, today).items():
        company = jobs[0][0].company
        detail = "\n".join(f"{p.title} ({p.job_id}): {'; '.join(w)}" for p, w in jobs)[:2000]
        old = open_items.get(key)
        if old and str(old.get("Detail") or "") == detail:
            continue
        if old:  # the job list changed: replace the company's item so it lists every flagged job
            tr.mark_action_done(str(old["ID"]), note="Replaced by an updated item for this company.")
        lines.append(add_action(s, f"Posting may be stale: {len(jobs)} jobs at {company}", TYPE, company=company,
                                link=jobs[0][0].url or jobs[0][0].apply_url, detail=detail))
    return lines


def close_stale_ghost_items(s: Settings, today: date | None = None, dry_run: bool = False) -> dict[str, int]:
    """Mark done (with a note, never delete) open per-job ghost items the current rule would not raise."""
    store, tr, hist = Store(s), Tracker(settings=s), Store(s).load_history()
    closed = kept = 0
    for it in tr.list_action_items(open_only=True):
        jid = str(it.get("JobID") or "")
        if it.get("Type") != TYPE or not jid:
            continue
        p = _worthy(s, store, jid)
        if p and _review_reasons(s, store, p, today, hist):
            kept += 1
            continue
        closed += 1
        if not dry_run:
            tr.mark_action_done(str(it["ID"]), note="Closed: no longer raised (job not worth preparing, or the "
                                "ghost rule no longer flags it). Ghost items are now one per company.")
    return {"closed": closed, "kept": kept}
