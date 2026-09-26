"""Retention: which old files `careeros prune` removes, and what it must never touch."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from careeros import retention
from careeros.config import ConfigError
from careeros.models import Posting
from careeros.store import Store

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
LONG_TEXT = "Build data pipelines. " * 200


def _job(settings, status: str, days_ago: int, *, company: str = "Acme", shots: list[str] | None = None,
         history: bool = True) -> Path:
    store = Store(settings)
    p = Posting(company=company, title=f"Engineer {status} {days_ago}", ats="greenhouse",
                url=f"https://boards.greenhouse.io/acme/jobs/{status}{days_ago}", ats_job_id=f"{status}{days_ago}",
                description_text=LONG_TEXT, description_html="<p>" + LONG_TEXT + "</p>",
                raw={"source": "greenhouse", "resolved_from": "https://acme.example/careers"})
    store.save_posting(p)
    d = store.job_dir(p.job_id)
    at = (NOW - timedelta(days=days_ago)).isoformat()
    st = {"status": status, "updated_at": at}
    if history:
        st["history"] = [{"status": "found", "at": (NOW - timedelta(days=days_ago + 5)).isoformat(), "note": None},
                         {"status": status, "at": at, "note": None}]
    (d / "status.json").write_text(json.dumps(st))
    for name in shots or []:
        f = d / "screenshots" / name
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b"x" * 1000)
    return d


def _actions(items):
    return sorted((i.job_id, i.action) for i in items)


# --- config ---------------------------------------------------------------------------------


def test_config_defaults_when_missing(settings):
    settings.pipeline.pop("retention", None)
    cfg = retention.retention_config(settings)
    assert cfg == {"screenshots_after_closed_days": 30, "keep_confirmation_screenshot": True,
                   "unprepared_posting_days": 90, "run_logs_days": 30, "run_summaries_days": 365}


def test_config_reads_overrides(settings):
    settings.pipeline["retention"] = {"screenshots_after_closed_days": 7, "keep_confirmation_screenshot": False}
    cfg = retention.retention_config(settings)
    assert cfg["screenshots_after_closed_days"] == 7
    assert cfg["keep_confirmation_screenshot"] is False
    assert cfg["unprepared_posting_days"] == 90


def test_config_rejects_bad_values(settings):
    settings.pipeline["retention"] = {"unprepared_posting_days": -3}
    with pytest.raises(ConfigError):
        retention.retention_config(settings)
    settings.pipeline["retention"] = ["not", "a", "mapping"]
    with pytest.raises(ConfigError):
        retention.retention_config(settings)


def test_example_pipeline_ships_retention_and_weekly_prune(example_settings):
    r = example_settings.pipeline["retention"]
    assert r["screenshots_after_closed_days"] == 30
    assert r["unprepared_posting_days"] == 90
    assert r["keep_confirmation_screenshot"] is True
    assert r["run_logs_days"] == 30 and r["run_summaries_days"] == 365
    assert example_settings.pipeline["schedule"]["jobs"]["prune"] == {"every_days": 7}


# --- last change ----------------------------------------------------------------------------


def test_last_change_uses_latest_history_entry():
    st = {"updated_at": "2026-01-01T00:00:00+00:00",
          "history": [{"at": "2026-02-01T00:00:00+00:00"}, {"at": "2026-03-01T00:00:00+00:00"}]}
    assert retention.last_change(st) == datetime(2026, 3, 1, tzinfo=timezone.utc)


def test_last_change_falls_back_to_updated_at_and_handles_garbage():
    assert retention.last_change({"updated_at": "2026-01-01T00:00:00+00:00"}) == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert retention.last_change({"history": [{"at": "not a date"}]}) is None
    assert retention.last_change({}) is None


# --- screenshots ----------------------------------------------------------------------------


def test_closed_job_past_window_loses_step_screenshots_but_keeps_confirmation(settings):
    d = _job(settings, "rejected", 31, shots=["01_form.png", "02_upload.png", "09_confirmation.png"])
    items = retention.plan(settings, now=NOW)
    shot_items = [i for i in items if i.action == "delete_screenshots"]
    assert len(shot_items) == 1
    names = sorted(Path(p).name for p in shot_items[0].paths)
    assert names == ["01_form.png", "02_upload.png"]
    assert shot_items[0].bytes == 2000
    retention.execute(settings, items, now=NOW)
    assert sorted(f.name for f in (d / "screenshots").iterdir()) == ["09_confirmation.png"]
    assert "[prune]" in (d / "log.md").read_text()


def test_confirmation_deleted_too_when_not_kept(settings):
    settings.pipeline["retention"] = {"keep_confirmation_screenshot": False}
    _job(settings, "withdrawn", 40, shots=["01_form.png", "09_confirmation.png"])
    item = next(i for i in retention.plan(settings, now=NOW) if i.action == "delete_screenshots")
    assert len(item.paths) == 2


@pytest.mark.parametrize("status", ["applied", "screening", "interview", "offer", "needs_review", "queued", "prepared"])
def test_active_jobs_never_touched(settings, status):
    _job(settings, status, 400, shots=["01_form.png"])
    assert retention.plan(settings, now=NOW) == []


def test_closed_job_inside_window_kept(settings):
    _job(settings, "ghosted", 29, shots=["01_form.png"])
    assert retention.plan(settings, now=NOW) == []


def test_never_descends_into_submitted_or_subdirs_and_skips_finder_copies(settings):
    d = _job(settings, "rejected", 60, shots=["01_form.png", "01_form 2.png"])
    (d / "screenshots" / "nested").mkdir()
    (d / "screenshots" / "nested" / "x.png").write_bytes(b"x")
    (d / "submitted" / "20260901T000000Z").mkdir(parents=True)
    (d / "submitted" / "20260901T000000Z" / "resume.pdf").write_bytes(b"pdf")
    item = next(i for i in retention.plan(settings, now=NOW) if i.action == "delete_screenshots")
    assert [Path(p).name for p in item.paths] == ["01_form.png"]
    retention.execute(settings, [item], now=NOW)
    assert (d / "screenshots" / "01_form 2.png").exists()
    assert (d / "screenshots" / "nested" / "x.png").exists()
    assert (d / "submitted" / "20260901T000000Z" / "resume.pdf").exists()


def test_zero_days_disables_rule(settings):
    settings.pipeline["retention"] = {"screenshots_after_closed_days": 0, "unprepared_posting_days": 0}
    _job(settings, "rejected", 500, shots=["01_form.png"])
    _job(settings, "found", 500)
    assert retention.plan(settings, now=NOW) == []


# --- unprepared postings --------------------------------------------------------------------


@pytest.mark.parametrize("status", ["found", "scored", "skipped"])
def test_old_unprepared_posting_becomes_stub(settings, status):
    d = _job(settings, status, 91)
    before = (d / "posting.json").stat().st_size
    items = retention.plan(settings, now=NOW)
    assert _actions(items) == [(d.name, "stub_posting")]
    assert 0 < items[0].bytes < before
    for keep in ("status.json", "log.md"):
        assert (d / keep).exists()
    (d / "score.json").write_text("{}")
    retention.execute(settings, items, now=NOW)
    stub = json.loads((d / "posting.json").read_text())
    assert stub["pruned"] is True and stub["pruned_at"].startswith("2026-09-25")
    assert stub["description_html"] == ""
    assert len(stub["description_text"]) <= retention.STUB_TEXT_CHARS + 1
    for k in ("company", "title", "location", "ats", "ats_job_id", "url", "apply_url", "fetched_at", "posted_at"):
        assert k in stub
    assert stub["raw"]["resolved_from"] == "https://acme.example/careers"
    assert (d / "score.json").read_text() == "{}"
    # still loads, still listed, dedupe keys intact
    p = Store(settings).load_posting(d.name)
    assert p is not None and p.job_id == d.name
    assert d.name in [j["job_id"] for j in Store(settings).list_jobs()]


def test_stub_is_idempotent(settings):
    _job(settings, "skipped", 120)
    retention.execute(settings, retention.plan(settings, now=NOW), now=NOW)
    assert retention.plan(settings, now=NOW) == []


def test_recent_unprepared_posting_kept(settings):
    _job(settings, "found", 89)
    assert retention.plan(settings, now=NOW) == []


def test_status_without_history_uses_updated_at(settings):
    d = _job(settings, "found", 100, history=False)
    assert _actions(retention.plan(settings, now=NOW)) == [(d.name, "stub_posting")]


def test_shared_state_files_untouched(settings, tmp_path):
    data = settings.paths["jobs_dir"].parent
    data.mkdir(parents=True, exist_ok=True)
    guarded = {n: data / n for n in ("seen.json", "posting_history.json", "flagged_registry.yaml",
                                      "verified_companies.yaml")}
    for p in guarded.values():
        p.write_text("keep")
    _job(settings, "found", 200)
    _job(settings, "rejected", 200, shots=["01_form.png"])
    retention.execute(settings, retention.plan(settings, now=NOW), now=NOW)
    assert all(p.read_text() == "keep" for p in guarded.values())


def test_summary_totals(settings):
    _job(settings, "rejected", 60, shots=["01_a.png", "02_b.png"])
    _job(settings, "found", 200)
    items = retention.plan(settings, now=NOW)
    s = retention.summarize(items)
    assert s["jobs"] == 2
    assert s["files"] == 3
    assert s["bytes"] == sum(i.bytes for i in items)


# --- review fixes: stubbed postings leave the prepare queue; config strictness ----------------


@pytest.mark.parametrize("status", ["found", "scored"])
def test_stubbed_queue_posting_is_marked_skipped(settings, status):
    from careeros.tracker import Tracker

    d = _job(settings, status, 91)
    retention.execute(settings, retention.plan(settings, now=NOW), now=NOW)
    st = json.loads((d / "status.json").read_text())
    assert st["status"] == "skipped"
    assert st["history"][-1]["note"] == "retention stub (posting older than 90 days)"
    assert d.name not in [j["job_id"] for j in Store(settings).list_jobs(status)]
    assert Tracker(settings=settings).get_job(d.name)["Status"] == "skipped"


def test_stubbed_skipped_posting_status_unchanged(settings):
    d = _job(settings, "skipped", 120)
    hist_before = json.loads((d / "status.json").read_text())["history"]
    retention.execute(settings, retention.plan(settings, now=NOW), now=NOW)
    assert json.loads((d / "status.json").read_text())["history"] == hist_before


def test_stub_status_change_queues_when_tracker_locked(settings, monkeypatch):
    from careeros.tracker import Tracker

    d = _job(settings, "found", 100)

    def locked(self):
        raise PermissionError("locked")

    monkeypatch.setattr(Tracker, "_load", locked)
    with pytest.warns(UserWarning):
        retention.execute(settings, retention.plan(settings, now=NOW), now=NOW)
    assert json.loads((d / "status.json").read_text())["status"] == "skipped"
    assert Tracker(settings=settings).pending_count() == 1


def test_config_null_keep_confirmation_defaults_true(settings):
    settings.pipeline["retention"] = {"keep_confirmation_screenshot": None}
    assert retention.retention_config(settings)["keep_confirmation_screenshot"] is True
    d = _job(settings, "rejected", 40, shots=["01_form.png", "03_confirmation.png"])
    retention.execute(settings, retention.plan(settings, now=NOW), now=NOW)
    assert (d / "screenshots" / "03_confirmation.png").exists()
    assert not (d / "screenshots" / "01_form.png").exists()


@pytest.mark.parametrize("bad", ["no", "", [], 0, 1])
def test_config_rejects_non_bool_keep_confirmation(settings, bad):
    settings.pipeline["retention"] = {"keep_confirmation_screenshot": bad}
    with pytest.raises(ConfigError, match="keep_confirmation_screenshot must be true/false"):
        retention.retention_config(settings)


# --- run history (data/runs) ---------------------------------------------------------------------------------

def _run(settings, days_ago: int, status: str = "done") -> Path:
    from careeros.runs.store import RunStore

    rs = RunStore(settings)
    start = NOW - timedelta(days=days_ago)
    run = rs.new_run("score", "manual", {"preset": "medium"}, start, run_id=f"r{days_ago:04d}")
    run.update(status=status, ended_at=start.isoformat())
    rs.save_run(run)
    rs.log(run["id"], "hello")
    att = rs.run_dir(run["id"]) / "attempts"
    att.mkdir(exist_ok=True)
    (att / "001.json").write_text("{}")
    (att / "001.stream.jsonl").write_text("{}\n" * 100)
    return rs.run_dir(run["id"])


def test_run_logs_go_after_30_days_summaries_after_365(settings):
    young, mid, old = _run(settings, 5), _run(settings, 40), _run(settings, 400)
    items = retention.plan(settings, now=NOW)
    got = sorted((i.run_id, i.action) for i in items if i.run_id)
    assert got == [("r0040", "delete_run_logs"), ("r0400", "delete_run")]
    retention.execute(settings, items, now=NOW)
    assert (young / "run.log").exists()
    assert not (mid / "run.log").exists() and not (mid / "attempts" / "001.stream.jsonl").exists()
    assert (mid / "run.json").exists() and (mid / "attempts" / "001.json").exists()
    assert not old.exists()


def test_a_run_still_going_is_never_pruned(settings):
    from careeros.runs import locks
    from careeros.runs.store import RunStore

    _run(settings, 400, status="running")
    locks.acquire(RunStore(settings).runner_lock_path, owner="run:r0400", ttl_seconds=600)
    assert [i for i in retention.plan(settings, now=NOW) if i.run_id] == []


def test_run_retention_zero_turns_it_off(settings):
    _run(settings, 400)
    settings.pipeline["retention"] = {"run_logs_days": 0, "run_summaries_days": 0}
    assert [i for i in retention.plan(settings, now=NOW) if i.run_id] == []


def test_summaries_window_must_cover_logs_window(settings):
    settings.pipeline["retention"] = {"run_logs_days": 60, "run_summaries_days": 30}
    with pytest.raises(ConfigError):
        retention.retention_config(settings)
