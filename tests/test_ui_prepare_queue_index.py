"""Today's "Prepare queued (N)" comes from the SQLite index (data/careeros.db), ranked exactly like
`careeros run status` / runner.select_candidates ranks the job folders on disk."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import add_prepare_candidates, build_ui_data

from careeros.config import ConfigError
from careeros.runs import runner
from careeros.runs.config import load_runs_config
from careeros.store import Store
from careeros.ui.index import Index
from careeros.ui.services import today as today_svc

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def data(tmp_path):
    d = build_ui_data(make_temp_root(tmp_path / "repo"), NOW)
    d["prep"] = add_prepare_candidates(d["settings"], NOW)
    return d


@pytest.fixture
def idx(data):
    ix = Index(data["settings"])
    ix.rebuild()
    yield ix
    ix.close()


@pytest.mark.parametrize("kind", ["prepare", "score"])
def test_index_ranking_matches_select_candidates(data, idx, kind):
    s = data["settings"]
    cfg = load_runs_config(s)
    disk = runner.select_candidates(s, kind, cfg, NOW)
    assert today_svc.ranked_from_index(s, idx, kind, cfg, NOW) == disk
    if kind == "prepare":
        ranked, excluded = disk
        prep = data["prep"]
        assert prep["p_req"] in {r["job_id"] for r in ranked}             # deferred requeue counts
        assert prep["p_done"] not in {r["job_id"] for r in ranked}
        assert {"job_id": prep["p_pruned"], "reason": "pruned"} in excluded
        globex = [r["job_id"] for r in ranked if r["company"] == "Globex"]
        assert globex == [prep["p_hi"], prep["p_lo"]]                       # fit-first within a company


def test_prepare_queue_reads_the_index_not_the_job_folders(data, idx, monkeypatch):
    s = data["settings"]
    expected = len(runner.select_candidates(s, "prepare", load_runs_config(s), NOW)[0])
    assert expected >= 4
    monkeypatch.setattr(Store, "iter_job_ids", lambda self: (_ for _ in ()).throw(AssertionError("disk read")))
    assert today_svc.prepare_queue(s, idx, NOW) == {"total": expected, "error": None}


def test_prepare_queue_follows_a_job_change_once_reindexed(data, idx):
    s = data["settings"]
    before = today_svc.prepare_queue(s, idx, NOW)["total"]
    Store(s)._write(data["prep"]["p_hi"], "prepare.json", {"qa_pass": True})
    idx.update_jobs([data["prep"]["p_hi"]])
    assert today_svc.prepare_queue(s, idx, NOW)["total"] == before - 1


def test_prepare_queue_reports_a_config_error(data, idx, monkeypatch):
    def boom(settings):
        raise ConfigError("bad runs config")

    monkeypatch.setattr("careeros.runs.config.load_runs_config", boom)
    assert today_svc.prepare_queue(data["settings"], idx, NOW) == {"total": None, "error": "bad runs config"}
