"""Ghost Action Items: one per company, only for jobs worth preparing; stale per-job items can be closed."""
from __future__ import annotations

from datetime import date

import pytest

from careeros.models import Posting, Score
from careeros.safety.ghost_items import close_stale_ghost_items, raise_ghost_items
from careeros.store import Store
from careeros.tracker import Tracker

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 25)
THIN = "We are hiring an engineer."
RICH = ("Build the ledger service in Go and Postgres. You join a team of six reporting to the platform director; "
        "first six months: migrate the batch jobs to streaming. Salary range $140,000 - $170,000. " * 4)


def _job(settings, n, company="Nimbus", fit=85, desc=THIN, fails=(), scored=True):
    store = Store(settings)
    p = Posting(company=company, title=f"Engineer {n}", ats="greenhouse", ats_job_id=str(n), posted_at="2026-06-01",
                last_updated="2026-06-01" if desc == THIN else "2026-09-20", description_text=desc, url=f"https://example.com/{company}/{n}")
    store.save_posting(p)
    if scored:
        store.save_score(Score(job_id=p.job_id, category="swe_backend", fit=fit, hard_filter_fails=list(fails)))
    return p


@pytest.fixture
def env(settings):
    settings.companies["dream_list"] = ["Nimbus"]
    tr = Tracker(settings=settings)
    tr.init()
    return settings, tr


def _open(tr):
    return [i for i in tr.list_action_items() if i["Type"] == "ghost_job"]


def test_one_item_per_company_for_prepare_worthy_jobs(env):
    s, tr = env
    for n in range(3):
        _job(s, n)
    _job(s, 9, fit=40)                       # below min_fit_to_prepare: no decision hangs on it
    _job(s, 10, fails=["location"])          # hard-filtered
    _job(s, 11, scored=False)                # not scored yet
    _job(s, 12, company="Orbit")             # not a dream company
    raise_ghost_items(s, today=TODAY)
    raise_ghost_items(s, today=TODAY)        # idempotent
    items = _open(tr)
    assert len(items) == 1 and items[0]["Company"] == "Nimbus"
    assert "3 jobs" in items[0]["What to do"] + str(items[0].get("Detail"))


def test_real_description_raises_nothing(env):
    s, tr = env
    _job(s, 1, desc=RICH)
    raise_ghost_items(s, today=TODAY)
    assert _open(tr) == []


def test_close_stale_marks_done_with_a_note_and_never_deletes(env):
    s, tr = env
    keep = _job(s, 1)
    gone = _job(s, 2, desc=RICH)             # new rule would not raise
    low = _job(s, 3, fit=10)
    for p in (keep, gone, low):
        tr.add_action_item("possible ghost", type="ghost_job", job_id=p.job_id, company=p.company)
    other = tr.add_action_item("call recruiter", type="other", job_id=gone.job_id)
    res = close_stale_ghost_items(s, today=TODAY)
    assert res == {"closed": 3, "covered": 1}  # per-job items are the old format: all close
    remaining = {i["ID"] for i in tr.list_action_items()}
    assert other in remaining
    done = {i["JobID"]: str(i["Detail"]) for i in tr.list_action_items(open_only=False)
            if i["Type"] == "ghost_job" and i["Done"] == "Y"}
    assert "no longer raised" in done[gone.job_id] and "no longer raised" in done[low.job_id]
    assert "company item" in done[keep.job_id]  # still flagged: the per-company item lists it


def test_dry_run_changes_nothing(env):
    s, tr = env
    low = _job(s, 3, fit=10)
    tr.add_action_item("possible ghost", type="ghost_job", job_id=low.job_id, company="Nimbus")
    res = close_stale_ghost_items(s, today=TODAY, dry_run=True)
    assert res == {"closed": 1, "covered": 0} and len(_open(tr)) == 1


def test_skipped_or_applied_jobs_raise_nothing(env):
    s, tr = env
    store = Store(s)
    store.set_status(_job(s, 1).job_id, "skipped", "location below min_fit_nonpreferred_location")
    store.set_status(_job(s, 2).job_id, "applied")
    p = _job(s, 3)
    raw = store.job_dir(p.job_id) / "score.json"
    import json
    raw.write_text(json.dumps({**json.loads(raw.read_text()), "decision": "skip", "skip_reason": "location"}))
    raise_ghost_items(s, today=TODAY)
    assert _open(tr) == []


def test_company_item_follows_new_flagged_jobs(env):
    s, tr = env
    _job(s, 1)
    raise_ghost_items(s, today=TODAY)
    _job(s, 2)
    raise_ghost_items(s, today=TODAY)
    (item,) = _open(tr)
    assert "2 jobs" in item["What to do"]
