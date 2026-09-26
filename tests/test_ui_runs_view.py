"""careeros.ui.services.runs_view: what the Runs screen shows, built on RunControl's public methods with fakes
(no subprocess, no signals, no launchctl): the current run's job rows and step pills, the queue's why chips,
the schedule panel and the pause `until` parser."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from careeros.models import Posting
from careeros.runs import locks
from careeros.runs.store import RunStore
from careeros.store import Store
from careeros.ui.services import runs_view as view
from careeros.ui.services.runs import RunControl

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def fake_launchctl(args):
    return 1, "", "not loaded"


@pytest.fixture
def rc(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    settings.root = Path(settings.paths["jobs_dir"]).parents[1]
    return RunControl(settings, popen=lambda *a, **k: None, pid_alive=lambda pid: True,
                      cmdline=lambda pid: "python -m careeros.cli run prepare --json", now=lambda: NOW,
                      launchctl=fake_launchctl)


def add_job(settings, key: str, company: str, title: str = "Backend Engineer") -> str:
    p = Posting(company=company, title=title, ats="greenhouse", ats_job_id=key,
                url=f"https://boards.example.com/{key}", description_text="python apis " * 40,
                posted_at=(NOW - timedelta(hours=20)).isoformat())
    Store(settings).save_posting(p)
    return p.job_id


# --- why chips -------------------------------------------------------------------------------------------------

def test_reasons_split_the_why_text_into_chips_with_points():
    got = view.reasons("posted 20h ago (+60); dream company (+25); closes 2026-09-30 (+15); fit 86 (+43); "
                       "retry after a failed attempt (+30); fit-first within Globex")
    assert [r["code"] for r in got] == ["fresh", "dream", "deadline", "fit", "retry", "other"]
    assert got[0] == {"code": "fresh", "text": "posted 20h ago", "points": 60.0}
    assert got[-1] == {"code": "other", "text": "fit-first within Globex", "points": None}
    assert view.reasons("") == [] and view.reasons(None) == []


# --- pause until -----------------------------------------------------------------------------------------------

def test_parse_until_accepts_a_future_iso_time_or_none():
    assert view.parse_until(None, NOW) is None
    assert view.parse_until("2026-09-26T13:00:00Z", NOW) == NOW + timedelta(hours=1)
    assert view.parse_until("+2h", NOW) == NOW + timedelta(hours=2)
    for bad in ("2026-09-26T11:00:00Z", "soon", "2026-09-26T13:00:00", ""):
        with pytest.raises(ValueError):
            view.parse_until(bad, NOW)


# --- current run -----------------------------------------------------------------------------------------------

def test_current_is_none_when_idle(rc):
    assert view.current_view(rc) is None


def test_current_lists_done_active_and_queued_jobs_with_steps(rc):
    s = rc.settings
    a, b, c = add_job(s, "a", "Acme Robotics"), add_job(s, "b", "Globex"), add_job(s, "c", "Initech")
    rs = RunStore(s)
    run = rs.new_run("prepare", "manual", {"preset": "small", "max_jobs": 3, "max_minutes": 30},
                     NOW - timedelta(minutes=6), counters={"attempted": 1, "ok": 1},
                     queue=[{"job_id": j, "rank": i, "score": 1, "why": ""} for i, j in enumerate((a, b, c), 1)])
    rs.save_attempt(run["id"], {"n": 1, "job_id": a, "company": "Acme Robotics", "title": "Backend Engineer",
                                "outcome": "ok", "duration_s": 400, "detail": ""})
    locks.acquire(rs.runner_lock_path, owner=f"run:{run['id']}", ttl_seconds=3600, pid=999, note="prepare",
                  pid_alive=lambda p: True)
    locks.acquire(rs.job_lock_path(b), owner=f"run:{run['id']}", ttl_seconds=3600, pid=999, pid_alive=lambda p: True)
    store = Store(s)
    (store.job_dir(b) / "score.json").write_text("{}")
    (store.job_dir(b) / "resume.pdf").write_bytes(b"%PDF")

    cur = view.current_view(rc)
    assert cur["id"] == run["id"] and cur["scheduled"] is False
    rows = {r["job_id"]: r for r in cur["jobs"]}
    assert [r["job_id"] for r in cur["jobs"]] == [a, b, c]
    assert rows[a]["state"] == "done" and rows[a]["company"] == "Acme Robotics" and rows[a]["duration_s"] == 400
    assert [st["state"] for st in rows[a]["steps"]] == ["done"] * 4
    assert rows[b]["state"] == "active" and rows[b]["company"] == "Globex"
    assert [(st["name"], st["state"]) for st in rows[b]["steps"]] == [
        ("Score", "done"), ("Tailor", "done"), ("Cover", "active"), ("QA", "pending")]
    assert rows[c]["state"] == "queued" and {st["state"] for st in rows[c]["steps"]} == {"pending"}
    assert "cap" in cur  # prepare runs show today's apply cap


def test_current_marks_a_scheduled_batch(rc):
    rs = RunStore(rc.settings)
    run = rs.new_run("score", "schedule", {"preset": "small", "max_jobs": 2, "max_minutes": 30},
                     NOW - timedelta(minutes=1))
    locks.acquire(rs.runner_lock_path, owner=f"run:{run['id']}", ttl_seconds=3600, pid=999, note="score",
                  pid_alive=lambda p: True)
    cur = view.current_view(rc)
    assert cur["scheduled"] is True and cur["cap"] is None and cur["jobs"] == []


# --- queue -----------------------------------------------------------------------------------------------------

def test_queue_adds_reason_chips_and_names_excluded_jobs(rc):
    s = rc.settings
    a = add_job(s, "a", "Acme Robotics")
    b = add_job(s, "b", "Globex")
    raw = Store(s)._read(b, "posting.json")
    Store(s)._write(b, "posting.json", {**raw, "pruned": True})
    q = view.queue_view(rc, "score", limit=10)
    assert q["total"] == 1 and q["items"][0]["job_id"] == a
    assert q["items"][0]["reasons"][0]["code"] == "fresh"
    assert q["excluded"] == [{"job_id": b, "reason": "pruned", "company": "Globex", "title": "Backend Engineer"}]
    assert q["excluded_total"] == 1


def test_queue_rejects_unknown_kinds(rc):
    with pytest.raises(ValueError):
        view.queue_view(rc, "apply", limit=5)


# --- schedule --------------------------------------------------------------------------------------------------

def test_schedule_describes_each_job_and_the_agent(rc):
    sch = view.schedule_view(rc)
    jobs = {j["kind"]: j for j in sch["jobs"]}
    assert list(jobs) == ["scout", "inbox_sync", "score", "prepare", "prune"]
    assert jobs["scout"]["every_minutes"] == 180 and jobs["scout"]["at"] == []
    assert jobs["score"]["at"] == ["01:00"] and jobs["score"]["next"]
    assert jobs["inbox_sync"]["enabled"] is False and jobs["inbox_sync"]["next"] is None
    assert sch["quiet_hours"] == {"start": "09:00", "end": "18:00"}
    assert sch["installed"] is False and sch["loaded"] is False and sch["last_tick"] is None
    assert sch["catch_up"] is None and sch["paused"] is None and sch["inbox_ready"] is False


# --- history / detail ------------------------------------------------------------------------------------------

def test_detail_names_the_jobs_of_its_attempts(rc):
    s = rc.settings
    a = add_job(s, "a", "Acme Robotics")
    rs = RunStore(s)
    run = rs.new_run("score", "manual", {}, NOW)
    run.update(status="done", stop_reason="completed")
    rs.save_run(run)
    rs.save_attempt(run["id"], {"n": 1, "job_id": a, "outcome": "ok", "duration_s": 3})
    d = view.detail_view(rc, run["id"])
    assert d["attempts"][0]["company"] == "Acme Robotics"
    assert view.detail_view(rc, "20260101-000000-score-ffff") is None
    with pytest.raises(ValueError):
        view.detail_view(rc, "../config")
