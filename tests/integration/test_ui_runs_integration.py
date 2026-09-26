"""RunControl end to end: real detached subprocesses on a temp repo root with the fake `claude` first on PATH
(tests/fixtures/fake_claude.py: prints stream-json, never calls a model). Start, watch, cancel (SIGTERM ->
stop reason cancelled), tail, step runs (tracker sync) and the in-process dry run."""
from __future__ import annotations

import json
import os
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import FIXTURES, PY, personalize, subprocess_env

from careeros.config import Settings
from careeros.models import Posting
from careeros.runs.store import RunStore
from careeros.store import Store
from careeros.ui.services.runs import Busy, RunControl

pytestmark = pytest.mark.integration


@pytest.fixture
def root(temp_root: Path) -> Path:
    return personalize(temp_root)  # doctor must pass: runs refuse to start on the example candidate


@pytest.fixture
def env(root: Path, tmp_path: Path) -> dict[str, str]:
    home, b = tmp_path / "home", tmp_path / "bin"
    home.mkdir()
    b.mkdir()
    exe = b / "claude"
    exe.write_text(f"#!{PY}\n" + (FIXTURES / "fake_claude.py").read_text())
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    e = subprocess_env(root, home)
    e["PATH"] = f"{b}{os.pathsep}{e['PATH']}"
    e.pop("CLAUDECODE", None)
    return e


def add_jobs(root: Path, n: int) -> list[str]:
    store = Store(Settings.load(root))
    now = datetime.now(timezone.utc)
    ids = []
    for i in range(n):
        p = Posting(company=f"Co{i}", title="Backend Software Engineer", ats="greenhouse", ats_job_id=f"r{i}",
                    url=f"https://boards.greenhouse.io/co/jobs/{i}", description_text="python apis " * 40,
                    posted_at=(now - timedelta(hours=50 + i * 10)).isoformat())
        store.save_posting(p)
        ids.append(p.job_id)
    return ids


def wait_for(fn, timeout: float = 60, every: float = 0.2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = fn()
        if got:
            return got
        time.sleep(every)
    raise AssertionError("timed out waiting")


def finished(rc: RunControl, kind: str):
    runs = rc.history(kind=kind)["runs"]
    return runs[0] if runs and runs[0]["state"] != "running" else None


def test_dry_run_in_process_writes_the_queue_and_no_run(root, env):
    ids = add_jobs(root, 3)
    rc = RunControl(Settings.load(root), env=env)
    out = rc.start("score", max_jobs=2, dry_run=True)
    assert [s["job_id"] for s in out["selected"]] == ids[:2]
    assert rc.history()["runs"] == [] and (RunStore(rc.settings).dir / "queue-score.json").exists()


def test_start_runs_a_batch_detached_and_history_shows_it(root, env):
    add_jobs(root, 2)
    rc = RunControl(Settings.load(root), env=env)
    out = rc.start("score", preset="small")
    run = wait_for(lambda: finished(rc, "score"))
    assert run["stop_reason"] == "completed" and run["counters"]["ok"] == 2
    assert Path(out["output"]).exists() and json.loads(Path(out["output"]).read_text())["id"] == run["id"]
    events = list(rc.tail(run["id"], follow=False))
    assert any(e["type"] == "system" for e in events) and any(e["type"] == "result" for e in events)
    assert any(e["type"] == "log" and "stop completed" in e["text"] for e in events)


def test_cancel_stops_a_hung_run_with_stop_reason_cancelled(root, env):
    ids = add_jobs(root, 2)
    for jid in ids:
        (root / "data" / "jobs" / jid / ".fake_mode").write_text("hang")
    rc = RunControl(Settings.load(root), env=env)
    rc.start("score")
    cur = wait_for(lambda: (c := rc.current()) and c.get("current_job") and c)
    assert cur["kind"] == "score" and cur["state"] == "running"
    with pytest.raises(Busy):
        rc.start("prepare")
    wait_for(lambda: any(e["type"] == "system" for e in rc.tail(cur["id"], follow=False)))  # claude is up
    assert rc.cancel()["status"] == "cancelling"
    run = wait_for(lambda: finished(rc, "score"), timeout=30)
    assert run["stop_reason"] == "cancelled" and run["counters"]["attempted"] == 1 and rc.current() is None


def test_tracker_step_records_a_run(root, env):
    add_jobs(root, 2)
    rc = RunControl(Settings.load(root), env=env)
    rc.start_step("tracker")
    run = wait_for(lambda: finished(rc, "tracker"))
    assert run["stop_reason"] == "completed" and "synced 2 jobs" in run["detail"]
    assert (root / "JobTracker.xlsx").exists()
