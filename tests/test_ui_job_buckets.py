"""TASK-034 / REQ-127, REQ-128, REQ-130, DEC-022: Jobs buckets (recommended / saved / applied), Today top picks,
reasons line computed on read for returned rows only."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import build_ui_data

from careeros import resumes
from careeros.store import Store
from careeros.ui.index import Index
from careeros.ui.services import jobs as jobs_svc
from careeros.ui.services import today as today_svc

pytestmark = pytest.mark.unit

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
CLOSED = ["skipped", "rejected", "withdrawn", "ghosted"]


@pytest.fixture
def data(tmp_path):
    d = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    ids = d["jobs"]
    # Fixture jobs have no flag (= ticked). Untick everything a user has not saved.
    Store(d["settings"]).set_selected([ids[k] for k in ("found", "scored", "queued", "review", "applied",
                                                         "skipped")], False)
    return d


@pytest.fixture
def idx(data):
    ix = Index(data["settings"])
    ix.rebuild()
    yield ix
    ix.close()


def _companies(ix, tab, **kw):
    return [r["company"] for r in jobs_svc.list_jobs(ix, tab=tab, closed=CLOSED, sort="-fit", **kw)["items"]]


def test_buckets(idx, data):
    # recommended: scored, unticked, not skipped / applied / closed; fit first
    assert _companies(idx, "recommended") == ["Umbrella Labs", "Initech", "Globex"]
    Store(data["settings"]).set_selected([data["jobs"]["queued"]], True)
    idx.rebuild()
    assert _companies(idx, "saved") == ["Initech"]
    # applied: applied or later, incl. closed after applying (Q-028), whatever the tick
    assert _companies(idx, "applied") == ["Stark Industries", "Hooli", "Wayne Enterprises"]


def test_counts_equal_rows(idx):
    counts = {t["key"]: t["count"] for t in jobs_svc.tabs(idx, CLOSED)}
    assert list(counts) == ["recommended", "saved", "applied"]
    for key, n in counts.items():
        assert jobs_svc.list_jobs(idx, tab=key, closed=CLOSED, limit=jobs_svc.MAX_LIMIT)["total"] == n
        assert len(jobs_svc.list_jobs(idx, tab=key, closed=CLOSED, limit=jobs_svc.MAX_LIMIT)["items"]) == n


@pytest.mark.parametrize("old,want", [("active", ["Umbrella Labs", "Initech", "Globex"]),
                                      ("all", ["Umbrella Labs", "Initech", "Globex"]),
                                      ("tier_a", ["Umbrella Labs"])])
def test_old_tab_keys_map_not_400(idx, old, want):
    assert _companies(idx, old) == want


def test_old_review_tab_maps_to_saved(idx, data):
    # needs_review jobs were prepared, so ticked: nearest new tab is Saved
    Store(data["settings"]).set_selected([data["jobs"]["review"], data["jobs"]["queued"]], True)
    idx.rebuild()
    assert _companies(idx, "review") == ["Umbrella Labs"]


def test_unknown_tab_still_refused(idx):
    with pytest.raises(ValueError):
        jobs_svc.list_jobs(idx, tab="nope", closed=CLOSED)


def test_top_picks_subset_of_recommended_same_order(idx, data):
    picks = [p["job_id"] for p in today_svc.top_picks(idx, NOW, closed=CLOSED)]
    rec = [r["job_id"] for r in jobs_svc.list_jobs(idx, tab="recommended", closed=CLOSED, sort="-fit")["items"]]
    assert picks and set(picks) <= set(rec)
    assert picks == [j for j in rec if j in picks]
    # REQ-127: tier A/B only (Globex is C)
    assert data["jobs"]["scored"] not in picks


def test_reasons_only_for_returned_rows_and_texts_loaded_once(idx, data, monkeypatch):
    calls: list[str] = []
    loads: list[int] = []
    real = jobs_svc._resume_texts
    monkeypatch.setattr(jobs_svc, "_resume_texts", lambda s: loads.append(1) or real(s))

    def fake(settings, job_dir, texts=None):
        calls.append(job_dir.name)
        return {"scored": True, "resumes": [{"groups": {"required": {"hit": ["Python"], "missing": ["Go"]},
                                                          "preferred": {"hit": [], "missing": []}}}]}

    page = jobs_svc.list_jobs(idx, tab="recommended", closed=CLOSED, sort="-fit", limit=2)
    rows = jobs_svc.with_reasons(data["settings"], page["items"], matcher=fake)
    assert len(calls) == 2 == len(rows) and loads == [1]
    assert rows[0]["reasons"] == {"covered": 1, "total": 2, "missing": ["Go"]}


def test_reasons_real_match_and_pending(idx, data):
    root = data["settings"].root
    rid = resumes.add(root, "cv.pdf", b"%PDF-1.4\n", name="Main")["rid"]
    resumes.add_text(root, rid, "Python Kafka engineer", author="user", source="edit")
    jid = data["jobs"]["queued"]
    sc = Store(data["settings"]).job_dir(jid) / "score.json"
    import json
    sc.write_text(json.dumps({**json.loads(sc.read_text()), "required_skills": ["Python", "Kafka", "Go"],
                              "preferred_skills": ["Rust"]}))
    rows = jobs_svc.with_reasons(data["settings"], [{"job_id": jid}, {"job_id": data["jobs"]["found"]}])
    assert rows[0]["reasons"] == {"covered": 2, "total": 3, "missing": ["Go", "Rust"]}
    assert rows[1]["reasons"] is None   # not scored yet → "Match pending"


def test_corrupt_resume_meta_drops_reasons_not_500(idx, data):
    root = data["settings"].root
    bad = root / "profile" / "resumes" / "broken"
    bad.mkdir(parents=True)
    (bad / "meta.json").write_text("{not json")
    rows = jobs_svc.with_reasons(data["settings"], [{"job_id": data["jobs"]["queued"]}])
    assert rows[0]["reasons"] is None


def test_malformed_score_drops_that_rows_reasons_not_500(idx, data):
    import json
    jid = data["jobs"]["queued"]
    (Store(data["settings"]).job_dir(jid) / "score.json").write_text(json.dumps({"required_skills": 5}))
    rows = jobs_svc.with_reasons(data["settings"], [{"job_id": jid}])
    assert rows[0]["reasons"] is None
