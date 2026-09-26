"""careeros.ui.services: meta, the Today status (stat tiles, counts) and the jobs list/detail, over the index."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import build_ui_data

from careeros.config import Settings
from careeros.models import ACTION_NEEDS, ACTION_TYPES, STATUSES
from careeros.runs.runner import STOP_REASONS
from careeros.ui.index import Index
from careeros.ui.services import jobs as jobs_svc
from careeros.ui.services import meta as meta_svc
from careeros.ui.services import status as status_svc

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)  # a Thursday


@pytest.fixture
def data(tmp_path):
    return build_ui_data(make_temp_root(tmp_path / "repo"), NOW)


@pytest.fixture
def idx(data):
    ix = Index(data["settings"])
    ix.rebuild()
    yield ix
    ix.close()


@pytest.fixture
def empty(tmp_path):
    s = Settings.load(make_temp_root(tmp_path / "empty"))
    ix = Index(s)
    ix.rebuild()
    yield s, ix
    ix.close()


# --- meta ------------------------------------------------------------------------------------------------------

def test_meta_lists_codes_from_config_and_models(data):
    m = meta_svc.meta(data["settings"])
    assert m["statuses"] == list(STATUSES)
    assert m["action_types"] == list(ACTION_TYPES) and m["action_needs"] == list(ACTION_NEEDS)
    assert m["tiers"] == ["A", "B", "C"] and m["priorities"] == ["H", "M", "L"]
    assert m["safety_verdicts"] == ["pass", "review", "block", "skip"]
    assert set(STOP_REASONS) <= set(m["stop_reasons"]) and "error" in m["stop_reasons"]
    assert set(m["clean_stops"]) <= set(m["stop_reasons"])
    assert m["presets"]["recommended"] == "medium" and m["presets"]["current"] == "medium"
    assert m["presets"]["values"]["small"] == {"max_score_jobs": 10, "max_prepare_jobs": 2, "max_minutes": 30}
    assert [c["name"] for c in m["pipeline"]["columns"]][0] == "Found"
    assert "rejected" in m["pipeline"]["closed"]
    assert m["ui"] == {"theme": "system", "undo_seconds": 8, "page_size": 100}


# --- status ----------------------------------------------------------------------------------------------------

def test_status_tiles(data, idx):
    st = status_svc.status(data["settings"], idx, NOW)
    t = st["tiles"]
    assert t["applied_week"]["value"] == 1
    assert [r["company"] for r in t["applied_week"]["rows"]] == ["Hooli"]
    assert t["applied_week"]["daily_cap"] >= 1
    assert (t["needs_you"]["value"], t["needs_you"]["high"]) == (3, 1)
    assert t["needs_you"]["rows"][0]["priority"] == "H"
    assert t["interviews"]["value"] == 1 and t["interviews"]["rows"][0]["company"] == "Stark Industries"
    # applied in the last 30 days: Hooli (2 d), Stark (12 d), Wayne (20 d); responded: Stark, Wayne
    rr = t["response_rate"]
    assert (rr["applied"], rr["responded"], rr["days"]) == (3, 2, 30)
    assert rr["rate"] == pytest.approx(2 / 3)
    assert "screening" in rr["definition"]


def test_status_counts_pipeline_and_runs(data, idx):
    st = status_svc.status(data["settings"], idx, NOW)
    cols = {c["name"]: c["count"] for c in st["pipeline"]["columns"]}
    assert cols == {"Found": 2, "Queued": 1, "Needs review": 1, "Applied": 1, "Screening · Interview": 1, "Offer": 0}
    assert st["pipeline"]["closed"] == {"count": 2, "by_status": {"rejected": 1, "skipped": 1}}
    assert st["counts"] == {"jobs": 8, "action_items_open": 3, "inbox": 2, "contacts": 2}
    assert [r["id"] for r in st["recent_runs"]] == [data["runs"]["prepare"], data["runs"]["score"]]
    assert st["recent_runs"][0]["stop_reason"] == "usage_limit"
    assert st["index"]["indexed_at"]
    assert st["paused"] is None and st["catch_up"] is None
    assert set(st["schedule"]["next"]) >= {"scout", "score", "prepare", "prune"}


def test_status_on_empty_data_is_all_zero(empty):
    s, ix = empty
    st = status_svc.status(s, ix, NOW)
    t = st["tiles"]
    assert (t["applied_week"]["value"], t["needs_you"]["value"], t["needs_you"]["high"], t["interviews"]["value"]) \
        == (0, 0, 0, 0)
    assert t["response_rate"]["rate"] is None and t["response_rate"]["applied"] == 0
    assert all(r == [] for r in (t["applied_week"]["rows"], t["needs_you"]["rows"], t["interviews"]["rows"]))
    assert st["counts"] == {"jobs": 0, "action_items_open": 0, "inbox": 0, "contacts": 0}
    assert all(c["count"] == 0 for c in st["pipeline"]["columns"]) and st["pipeline"]["closed"]["count"] == 0
    assert st["recent_runs"] == []


def test_status_shows_pause_and_catch_up(data, idx):
    from careeros.runs.store import RunStore

    rs = RunStore(data["settings"])
    rs.set_pause(NOW + timedelta(hours=1), "vacation", NOW)
    (rs.dir / "catch_up.json").write_text('{"kinds": {"score": {"slots": 3, "first_missed": "2026-09-23T20:00"}}}')
    st = status_svc.status(data["settings"], idx, NOW)
    assert st["paused"]["reason"] == "vacation"
    assert st["catch_up"]["kinds"]["score"]["slots"] == 3


def test_status_reports_a_broken_schedule_instead_of_failing(data, idx):
    data["settings"].pipeline["schedule"] = {"scout": "0 7 * * *"}
    st = status_svc.status(data["settings"], idx, NOW)
    assert st["schedule"]["next"] == {} and "schedule" in st["schedule"]["error"]


def test_interrupted_run_is_flagged(data, idx):
    from careeros.runs.store import RunStore

    rs = RunStore(data["settings"])
    run = rs.new_run("score", "manual", {}, NOW - timedelta(minutes=5))
    run["pid"] = 999_999_999
    rs.save_run(run)
    idx.sync()
    st = status_svc.status(data["settings"], idx, NOW)
    top = st["recent_runs"][0]
    assert top["id"] == run["id"] and top["status"] == "running" and top["interrupted"] is True


# --- jobs ------------------------------------------------------------------------------------------------------

def test_jobs_list_default_sort_and_paging(data, idx):
    page = jobs_svc.list_jobs(idx, limit=3)
    assert page["total"] == 8 and len(page["items"]) == 3 and page["next_cursor"] == "3"
    assert [j["fit"] for j in page["items"]] == [91, 88, 86]         # fit, high first
    rest = jobs_svc.list_jobs(idx, limit=10, cursor=page["next_cursor"])
    assert len(rest["items"]) == 5 and rest["next_cursor"] is None
    assert rest["items"][-1]["fit"] is None                          # unscored last


@pytest.mark.parametrize("kw,expect", [
    ({"status": ["applied", "interview"]}, {"Hooli", "Stark Industries"}),
    ({"tier": ["A"]}, {"Umbrella Labs", "Stark Industries"}),
    ({"safety": ["review"]}, {"Umbrella Labs"}),
    ({"category": ["swe_backend"], "q": "glob"}, {"Globex"}),
    ({"q": "platform"}, {"Initech"}),
    ({"q": "100%_"}, set()),
])
def test_jobs_list_filters(idx, kw, expect):
    assert {j["company"] for j in jobs_svc.list_jobs(idx, **kw)["items"]} == expect


def test_jobs_list_sorts(idx):
    by_company = jobs_svc.list_jobs(idx, sort="company")["items"]
    assert [j["company"] for j in by_company][:2] == ["Acme Robotics", "Globex"]
    newest = jobs_svc.list_jobs(idx, sort="-found_at")["items"]
    assert newest[0]["company"] == "Acme Robotics"
    with pytest.raises(ValueError):
        jobs_svc.list_jobs(idx, sort="nope; DROP TABLE jobs")
    with pytest.raises(ValueError):
        jobs_svc.list_jobs(idx, cursor="x")


def test_job_detail_reads_the_files(data, idx):
    jid = data["jobs"]["interview"]
    d = jobs_svc.job_detail(data["settings"], idx, jid)
    assert d["job"]["company"] == "Stark Industries" and d["job"]["status"] == "interview"
    assert d["posting"]["title"] == "Software Engineer" and "description_html" not in d["posting"]
    assert d["score"]["fit"] == 86 and d["safety"]["verdict"] == "pass"
    assert d["qa"][0]["passed"] is True
    assert {f["name"] for f in d["documents"]} >= {"resume.pdf", "cover_letter.md"}
    assert [c["name"] for c in d["contacts"]] == ["Pat Rivers", "Sam Lee"]
    assert [h["status"] for h in d["history"]][-1] == "interview"
    assert "status -> interview" in d["log"]
    assert d["apply_session"] is None and d["screenshots"] == []


def test_job_detail_unknown_or_unsafe_id(data, idx):
    assert jobs_svc.job_detail(data["settings"], idx, "nope000000") is None
    for bad in ("../config", "a/b", "", ".hidden"):
        assert jobs_svc.job_detail(data["settings"], idx, bad) is None
