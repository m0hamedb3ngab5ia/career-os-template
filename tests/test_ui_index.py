"""careeros.ui.index: the SQLite read index (data/careeros.db) rebuilt from the job, run and tracker files."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import build_ui_data

from careeros.store import Store
from careeros.ui import index as index_mod
from careeros.ui.index import Index

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


def _jobs(ix):
    return {r["job_id"]: r for r in ix.query("SELECT * FROM jobs")}


def test_default_path_is_next_to_data_jobs(data):
    ix = Index(data["settings"])
    assert ix.path == data["settings"].paths["jobs_dir"].parent / "careeros.db"
    ix.close()


def test_rebuild_indexes_every_job_with_its_fields(idx, data):
    jobs = _jobs(idx)
    assert set(jobs) == set(data["jobs"].values())
    r = jobs[data["jobs"]["review"]]
    assert (r["company"], r["title"], r["status"], r["fit"], r["tier"], r["safety"], r["category"]) == (
        "Umbrella Labs", "Infrastructure Engineer", "needs_review", 91, "A", "review", "swe_backend")
    assert r["qa_passed"] == 1 and r["qa_score"] == pytest.approx(8.5)
    assert jobs[data["jobs"]["found"]]["fit"] is None and jobs[data["jobs"]["found"]]["qa_passed"] is None
    assert jobs[data["jobs"]["applied"]]["applied_at"].startswith("2026-09-22")
    assert jobs[data["jobs"]["found"]]["applied_at"] is None


def test_status_history_rows(idx, data):
    rows = idx.query("SELECT status FROM status_history WHERE job_id = ? ORDER BY seq", (data["jobs"]["interview"],))
    assert [r["status"] for r in rows] == ["found", "scored", "queued", "applied", "screening", "interview"]


def test_action_items_and_contacts_and_runs(idx, data):
    acts = {r["id"]: r for r in idx.query("SELECT * FROM action_items")}
    assert set(acts) == set(data["actions"].values())
    assert acts[data["actions"]["done"]]["done"] == 1 and acts[data["actions"]["high"]]["priority"] == "H"
    assert acts[data["actions"]["high"]]["link"] == "https://boards.example.com/review"
    contacts = idx.query("SELECT * FROM contacts ORDER BY name")
    assert [(c["name"], c["linkedin_degree"], c["mutuals"]) for c in contacts] == [("Pat Rivers", 1, None),
                                                                                   ("Sam Lee", None, 0)]
    runs = {r["id"]: r for r in idx.query("SELECT * FROM runs")}
    assert runs[data["runs"]["prepare"]]["stop_reason"] == "usage_limit"
    att = idx.query("SELECT * FROM attempts WHERE run_id = ?", (data["runs"]["score"],))
    assert att[0]["outcome"] == "ok" and att[0]["job_id"] == data["jobs"]["queued"]


def test_wal_mode_and_schema_version(idx):
    assert idx.query("PRAGMA journal_mode")[0]["journal_mode"] == "wal"
    assert idx.get_meta("schema_version") == str(index_mod.SCHEMA_VERSION)
    assert idx.get_meta("indexed_at")


def test_sync_skips_unchanged_jobs_and_picks_up_changes(idx, data):
    assert idx.sync()["jobs_changed"] == []
    jid = data["jobs"]["queued"]
    Store(data["settings"]).set_status(jid, "prepared", "docs ready")
    assert idx.sync()["jobs_changed"] == [jid]
    assert _jobs(idx)[jid]["status"] == "prepared"


def test_update_jobs_by_id(idx, data):
    jid = data["jobs"]["found"]
    Store(data["settings"]).set_status(jid, "scored")
    assert idx.update_jobs([jid]) == [jid]
    assert idx.update_jobs([jid]) == []          # same files -> skipped
    assert _jobs(idx)[jid]["status"] == "scored"


def test_deleted_job_leaves_the_index(idx, data):
    import shutil

    jid = data["jobs"]["skipped"]
    shutil.rmtree(Store(data["settings"]).job_dir(jid))
    res = idx.sync()
    assert jid in res["jobs_removed"] and jid not in _jobs(idx)
    assert idx.query("SELECT COUNT(*) AS n FROM status_history WHERE job_id = ?", (jid,))[0]["n"] == 0
    other = data["jobs"]["rejected"]                                     # by id (the watcher's path): also removes
    shutil.rmtree(Store(data["settings"]).job_dir(other))
    assert idx.update_jobs([other]) == [other] and other not in _jobs(idx)
    assert idx.update_jobs([other]) == []


def test_finder_copies_are_ignored(idx, data):
    import shutil

    jd = Store(data["settings"]).job_dir(data["jobs"]["found"])
    shutil.copytree(jd, jd.with_name(jd.name + " 2"))
    idx.sync()
    assert not any(" " in j for j in _jobs(idx))


def test_schema_bump_rebuilds(data, monkeypatch):
    ix = Index(data["settings"])
    ix.rebuild()
    ix.close()
    con = sqlite3.connect(Index(data["settings"]).path)
    con.execute("UPDATE meta SET value = '0' WHERE key = 'schema_version'")
    con.execute("DELETE FROM jobs")
    con.commit()
    con.close()
    ix = Index(data["settings"])
    ix.sync()
    assert len(_jobs(ix)) == len(data["jobs"]) and ix.get_meta("schema_version") == str(index_mod.SCHEMA_VERSION)
    ix.close()


def test_tracker_reindexed_only_when_it_changes(idx, data):
    from careeros.tracker import Tracker

    assert idx.update_tracker() is False
    Tracker(settings=data["settings"]).mark_action_done(data["actions"]["high"])
    st = data["settings"].paths["tracker_xlsx"]
    os.utime(st, (st.stat().st_atime, st.stat().st_mtime + 5))
    assert idx.update_tracker() is True
    assert idx.query("SELECT done FROM action_items WHERE id = ?", (data["actions"]["high"],))[0]["done"] == 1


def test_missing_tracker_is_empty_and_never_created(tmp_path):
    from careeros.config import Settings

    s = Settings.load(make_temp_root(tmp_path / "repo"))
    ix = Index(s)
    ix.rebuild()
    assert ix.query("SELECT COUNT(*) AS n FROM action_items")[0]["n"] == 0
    assert not s.paths["tracker_xlsx"].exists()
    assert ix.query("SELECT COUNT(*) AS n FROM jobs")[0]["n"] == 0
    ix.close()


def test_broken_json_does_not_stop_the_index(idx, data):
    jid = data["jobs"]["scored"]
    (Store(data["settings"]).job_dir(jid) / "score.json").write_text("{not json", encoding="utf-8")
    idx.update_jobs([jid])
    row = _jobs(idx)[jid]
    assert row["fit"] is None and row["company"] == "Globex"


def test_run_updates(idx, data):
    from careeros.runs.store import RunStore

    rs = RunStore(data["settings"])
    run = rs.load_run(data["runs"]["score"])
    run["stop_reason"] = "cancelled"
    rs.save_run(run)
    assert idx.update_runs([run["id"]]) == [run["id"]]
    assert idx.query("SELECT stop_reason FROM runs WHERE id = ?", (run["id"],))[0]["stop_reason"] == "cancelled"
    assert idx.sync()["runs_changed"] == []


def test_contacts_json_parse_errors_are_skipped(idx, data):
    jd = Store(data["settings"]).job_dir(data["jobs"]["interview"])
    (jd / "contacts.json").write_text(json.dumps({"contacts": "nope"}), encoding="utf-8")
    idx.update_jobs([data["jobs"]["interview"]])
    assert idx.query("SELECT COUNT(*) AS n FROM contacts")[0]["n"] == 0


def test_corrupt_index_file_is_replaced(data):
    path = Index(data["settings"]).path
    for suffix in ("", "-wal", "-shm"):
        p = path.with_name(path.name + suffix)
        if p.exists():
            p.unlink()
    path.write_bytes(b"not a database at all, just bytes" * 10)
    ix = Index(data["settings"])
    ix.sync()
    assert ix.query("SELECT COUNT(*) AS n FROM jobs")[0]["n"] == len(data["jobs"])
    ix.close()
