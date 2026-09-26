"""careeros.ui.watch: file changes -> one coalesced plan -> index updates -> one SSE event per batch."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import build_ui_data

from careeros.store import Store
from careeros.ui.index import Index
from careeros.ui.watch import Roots, Watcher, plan_changes

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def roots(tmp_path):
    data = tmp_path / "data"
    return Roots(jobs=data / "jobs", runs=data / "runs", config=tmp_path / "config",
                 tracker=tmp_path / "JobTracker.xlsx", index=data / "careeros.db")


def test_plan_groups_changes_by_kind(roots):
    j, r = roots.jobs, roots.runs
    plan = plan_changes([
        j / "abc123" / "status.json", j / "abc123" / "log.md", j / "def456" / "screenshots" / "01_x.png",
        r / "20260924-010000-score-ab12" / "run.json", r / "20260924-010000-score-ab12" / "attempts" / "001.json",
        r / "queue-score.json", r / "pause.json",
        roots.config / "pipeline.yaml", roots.tracker, roots.tracker.with_name("JobTracker.xlsx.pending.json"),
    ], roots)
    assert plan.jobs == {"abc123", "def456"}
    assert plan.runs == {"20260924-010000-score-ab12"}
    assert plan.tracker and plan.config and plan.status
    assert plan.any


@pytest.mark.parametrize("name", [
    "careeros.db", "careeros.db-wal", "careeros.db-shm", "careeros.db-journal",
])
def test_plan_ignores_the_index_itself(roots, name):
    assert not plan_changes([roots.index.with_name(name)], roots).any


def test_plan_ignores_temp_files_locks_and_finder_copies(roots):
    j = roots.jobs
    plan = plan_changes([
        j / "abc123" / "status.json.123.tmp", j / "abc123" / ".status.json.99.tmp", j / "abc123 2" / "posting.json",
        j / "abc123" / "posting 2.json", roots.tracker.with_name(".JobTracker.xlsx.lock"), j / "_example" / "x.json",
        roots.config / "pipeline 2.yaml",
    ], roots)
    assert not plan.any


def test_plan_other_data_files_mark_status(roots):
    plan = plan_changes([roots.jobs.parent / "seen.json"], roots)
    assert plan.status and not plan.jobs


@pytest.fixture
def data(tmp_path):
    return build_ui_data(make_temp_root(tmp_path / "repo"), NOW)


class FakeBroker:
    def __init__(self):
        self.sent = []

    def publish(self, event, payload):
        self.sent.append((event, payload))
        return len(self.sent)


def test_handle_reindexes_and_publishes_once(data):
    ix = Index(data["settings"])
    ix.rebuild()
    b = FakeBroker()
    w = Watcher(data["settings"], ix, b)
    jid = data["jobs"]["queued"]
    store = Store(data["settings"])
    store.set_status(jid, "prepared")
    jd = store.job_dir(jid)
    payload = w.handle([jd / "status.json", jd / "log.md", jd / "status.json"])
    assert b.sent == [("changed", payload)]
    assert payload["jobs"] == [jid] and payload["runs"] == [] and payload["actions"] is False
    assert ix.query("SELECT status FROM jobs WHERE job_id = ?", (jid,))[0]["status"] == "prepared"
    ix.close()


def test_handle_skips_publish_when_nothing_changed(data):
    ix = Index(data["settings"])
    ix.rebuild()
    b = FakeBroker()
    w = Watcher(data["settings"], ix, b)
    jd = Store(data["settings"]).job_dir(data["jobs"]["queued"])
    assert w.handle([jd / "status.json"]) is None          # same signature as indexed
    assert w.handle([ix.path]) is None
    assert b.sent == []
    ix.close()


def test_handle_config_change_calls_reload(data):
    ix = Index(data["settings"])
    ix.rebuild()
    b = FakeBroker()
    seen = []
    w = Watcher(data["settings"], ix, b, on_config=lambda: seen.append(1))
    payload = w.handle([data["settings"].root / "config" / "pipeline.yaml"])
    assert seen == [1] and payload["config"] is True
    ix.close()


def test_handle_status_files_publish_without_reindex(data):
    from careeros.runs.store import RunStore

    ix = Index(data["settings"])
    ix.rebuild()
    b = FakeBroker()
    w = Watcher(data["settings"], ix, b)
    payload = w.handle([RunStore(data["settings"]).pause_path])
    assert payload["status"] is True and payload["jobs"] == []
    ix.close()


def test_watcher_roots_come_from_settings(data):
    ix = Index(data["settings"])
    w = Watcher(data["settings"], ix, FakeBroker())
    s = data["settings"]
    assert w.roots.jobs == s.paths["jobs_dir"].resolve()
    assert w.roots.tracker == s.paths["tracker_xlsx"].resolve()
    assert w.roots.index == ix.path.resolve()
    assert set(w.watch_dirs()) >= {w.roots.jobs, w.roots.config}
    ix.close()


def test_loop_passes_the_quiet_window_as_step(data, monkeypatch):
    import watchfiles

    seen = {}

    def fake_watch(*dirs, **kw):
        seen.update(kw, dirs=dirs)
        return iter(())

    monkeypatch.setattr(watchfiles, "watch", fake_watch)
    ix = Index(data["settings"])
    w = Watcher(data["settings"], ix, FakeBroker(), debounce_ms=300)
    w._loop([w.roots.jobs], True)
    assert seen["step"] == 300 and seen["debounce"] == 1600 and seen["recursive"] is True
    w = Watcher(data["settings"], ix, FakeBroker(), debounce_ms=1000)
    w._loop([w.roots.jobs], False)
    assert seen["step"] == 1000 and seen["debounce"] == 5000 and seen["recursive"] is False
    ix.close()
