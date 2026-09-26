"""careeros.ui.services.runs.RunControl: start / cancel / pause / catch-up / queue / history / tail, with fakes
(no subprocess, no signals): a fake Popen, fake pid and command-line lookups, a tmp RunStore."""
from __future__ import annotations

import json
import os
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from careeros.models import Posting
from careeros.runs import locks
from careeros.runs.store import RunStore
from careeros.store import Store
from careeros.ui.services import step as step_mod
from careeros.ui.services.runs import Busy, NotSetUp, Paused, RunControl
from careeros.ui.services.stream import parse_event

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


class FakePopen:
    calls: list[dict] = []

    def __init__(self, cmd, **kw):
        self.cmd, self.kw, self.pid = cmd, kw, 4242
        FakePopen.calls.append({"cmd": cmd, **kw})


@pytest.fixture(autouse=True)
def _reset():
    FakePopen.calls = []


@pytest.fixture
def rc(settings):
    settings.root = Path(settings.paths["jobs_dir"]).parents[1]
    return make_rc(settings)


def make_rc(settings, **kw) -> RunControl:
    kw.setdefault("popen", FakePopen)
    kw.setdefault("python", "/venv/bin/python")
    kw.setdefault("env", {"PATH": "/bin"})
    kw.setdefault("pid_alive", lambda pid: True)
    kw.setdefault("cmdline", lambda pid: "/venv/bin/python -m careeros.cli --root /r run score --json")
    kw.setdefault("now", lambda: NOW)
    return RunControl(settings, **kw)


def add_jobs(settings, n: int) -> list[str]:
    store = Store(settings)
    ids = []
    for i in range(n):
        p = Posting(company=f"Co{i}", title="Backend Software Engineer", ats="greenhouse", ats_job_id=f"r{i}",
                    url=f"https://boards.greenhouse.io/co/jobs/{i}", description_text="python apis " * 40,
                    posted_at=(datetime.now(timezone.utc) - timedelta(hours=50 + i)).isoformat())
        store.save_posting(p)
        ids.append(p.job_id)
    return ids


def hold_runner(rs: RunStore, rid: str, pid: int = 999, note: str = "score (manual)") -> None:
    locks.acquire(rs.runner_lock_path, owner=f"run:{rid}", ttl_seconds=3600, pid=pid, note=note,
                  pid_alive=lambda p: True)


def running_run(rs: RunStore, kind: str = "score", rid: str | None = None, **extra) -> dict:
    run = rs.new_run(kind, "manual", {"preset": "small", "max_jobs": 4, "max_minutes": 30}, NOW - timedelta(minutes=6),
                     run_id=rid, counters={"candidates": 5, "attempted": 1, "ok": 1, "failed": 0}, **extra)
    return run


# --- start ---------------------------------------------------------------------------------------------------

def test_start_spawns_a_detached_cli_run_with_the_preset(rc):
    out = rc.start("score", preset="small")
    call = FakePopen.calls[0]
    assert call["cmd"] == ["/venv/bin/python", "-m", "careeros.cli", "--root", str(rc.settings.root), "run", "score",
                           "--preset", "small", "--json"]
    assert call["start_new_session"] is True and call["cwd"] == str(rc.settings.root)
    assert call["env"] == {"PATH": "/bin"}
    assert out["pid"] == 4242 and out["kind"] == "score" and out["started"] is True
    assert Path(out["output"]).parent == RunStore(rc.settings).dir / "ui"


def test_start_passes_custom_limits(rc):
    rc.start("prepare", max_jobs=3, max_minutes=40)
    cmd = FakePopen.calls[0]["cmd"]
    assert cmd[cmd.index("--max-jobs") + 1] == "3" and cmd[cmd.index("--max-minutes") + 1] == "40"
    assert "--preset" not in cmd


@pytest.mark.parametrize("args", [dict(kind="apply"), dict(kind="score", preset="huge"),
                                  dict(kind="score", max_jobs=0)])
def test_start_rejects_bad_input_before_spawning(rc, args):
    with pytest.raises(ValueError):
        rc.start(**args)
    assert FakePopen.calls == []


def test_start_refuses_while_another_run_holds_the_lock(rc):
    hold_runner(RunStore(rc.settings), "20260926-110000-score-abcd")
    with pytest.raises(Busy) as e:
        rc.start("score")
    assert e.value.holder["owner"] == "run:20260926-110000-score-abcd"
    assert FakePopen.calls == []


def test_start_refuses_while_paused(rc):
    RunStore(rc.settings).set_pause(None, "holiday", NOW - timedelta(hours=1))
    with pytest.raises(Paused):
        rc.start("score")
    assert FakePopen.calls == []


def test_dry_run_returns_the_selection_and_spawns_nothing(rc):
    ids = add_jobs(rc.settings, 3)
    out = rc.start("score", preset="small", dry_run=True)
    assert out["dry_run"] is True and FakePopen.calls == []
    assert {s["job_id"] for s in out["selected"]} == set(ids)
    assert (RunStore(rc.settings).dir / "queue-score.json").exists()


def test_launch_outputs_are_trimmed(rc):
    ui = RunStore(rc.settings).dir / "ui"
    ui.mkdir(parents=True)
    for i in range(60):
        (ui / f"20260101-0000{i:02d}-score.out").write_text("x")
    rc.start("score")
    assert len(list(ui.glob("*.out"))) <= 50


# --- steps (scout, tracker, prune, inbox) --------------------------------------------------------------------

def test_start_step_spawns_the_step_runner(rc):
    out = rc.start_step("scout")
    assert FakePopen.calls[0]["cmd"] == ["/venv/bin/python", "-m", "careeros.ui.services.step", "--root",
                                         str(rc.settings.root), "scout"]
    assert FakePopen.calls[0]["start_new_session"] is True and out["kind"] == "scout"


def test_inbox_sync_is_not_set_up_while_disabled(rc):
    with pytest.raises(NotSetUp) as e:
        rc.start_step("inbox_sync")
    assert "inbox" in str(e.value).lower() and FakePopen.calls == []


def test_unknown_step(rc):
    with pytest.raises(ValueError):
        rc.start_step("apply")


def test_step_already_running_is_busy(rc):
    rs = RunStore(rc.settings)
    locks.acquire(step_mod.step_lock_path(rs, "scout"), owner="step:x", ttl_seconds=600, pid=1,
                  pid_alive=lambda p: True)
    with pytest.raises(Busy):
        rc.start_step("scout")


def test_prune_plan_is_synchronous(rc):
    out = rc.prune_plan()
    assert out["dry_run"] is True and out["items"] == [] and "summary" in out


# --- the step runner records a run -------------------------------------------------------------------------

def test_step_run_records_completed(settings):
    rec = step_mod.run_step(settings, "tracker", actions={"tracker": lambda: ("ok", "synced 3 jobs")})
    run = RunStore(settings).load_run(rec["id"])
    assert run["kind"] == "tracker" and run["status"] == "done" and run["stop_reason"] == "completed"
    assert run["detail"] == "synced 3 jobs" and "synced 3 jobs" in RunStore(settings).read_log(rec["id"])
    assert not step_mod.step_lock_path(RunStore(settings), "tracker").exists()


def test_step_run_records_error(settings):
    def boom():
        raise RuntimeError("board down")

    rec = step_mod.run_step(settings, "scout", actions={"scout": boom})
    assert rec["stop_reason"] == "error" and "board down" in rec["detail"] and rec["status"] == "failed"


def test_step_run_records_cancel(settings):
    def interrupted():
        raise KeyboardInterrupt

    rec = step_mod.run_step(settings, "prune", actions={"prune": interrupted})
    assert rec["stop_reason"] == "cancelled"


def test_step_run_busy_when_locked(settings):
    rs = RunStore(settings)
    locks.acquire(step_mod.step_lock_path(rs, "scout"), owner="step:x", ttl_seconds=600, pid=1,
                  pid_alive=lambda p: True)
    with pytest.raises(Busy):
        step_mod.run_step(settings, "scout", actions={"scout": lambda: ("ok", "")})


# --- cancel --------------------------------------------------------------------------------------------------

def test_cancel_when_idle(rc):
    assert rc.cancel()["status"] == "idle"


def test_cancel_sends_sigterm_to_a_careeros_run(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"], pid=777)
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append((pid, sig)))
    out = rc2.cancel()
    assert out == {"status": "cancelling", "run_id": run["id"], "pid": 777}
    assert sent == [(777, signal.SIGTERM)]
    assert rc2.cancel()["status"] == "already_stopping" and len(sent) == 1


def test_cancel_refuses_a_process_that_is_not_careeros(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"], pid=777)
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append(pid), cmdline=lambda pid: "/usr/bin/vim notes.txt")
    assert rc2.cancel()["status"] == "refused" and sent == []


def test_cancel_refuses_a_scheduled_tick(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"], pid=777)
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append(pid),
                  cmdline=lambda pid: "/venv/bin/python -m careeros.cli --root /r tick")
    out = rc2.cancel()
    assert out["status"] == "refused" and "pause" in out["detail"].lower() and sent == []


def test_cancel_a_dead_holder(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"], pid=777)
    rc2 = make_rc(rc.settings, pid_alive=lambda pid: False, kill=lambda *a: pytest.fail("no kill"))
    assert rc2.cancel()["status"] == "idle"


def test_cancel_a_step_by_run_id(rc):
    rs = RunStore(rc.settings)
    run = rs.new_run("scout", "manual", {}, NOW)
    locks.acquire(step_mod.step_lock_path(rs, "scout"), owner=f"step:{run['id']}", ttl_seconds=600, pid=555,
                  pid_alive=lambda p: True)
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append(pid),
                  cmdline=lambda pid: "/venv/bin/python -m careeros.ui.services.step --root /r scout")
    assert rc2.cancel(run["id"])["status"] == "cancelling" and sent == [555]


# --- pause, resume, catch-up ---------------------------------------------------------------------------------

def test_pause_and_resume(rc):
    p = rc.pause(until=NOW + timedelta(hours=1), reason="ui")
    assert p["until"] and RunStore(rc.settings).pause_state(NOW)
    assert rc.resume() is True and rc.resume() is False


def test_catch_up_dismiss_runs_in_process(rc):
    rs = RunStore(rc.settings)
    rs.dir.mkdir(parents=True, exist_ok=True)
    (rs.dir / "catch_up.json").write_text(json.dumps({"kinds": {"score": {"slots": 2}}}))
    out = rc.catch_up(dismiss=True)
    assert out["dismissed"] is True and not (rs.dir / "catch_up.json").exists() and FakePopen.calls == []


def test_catch_up_spawns_the_cli(rc):
    rs = RunStore(rc.settings)
    rs.dir.mkdir(parents=True, exist_ok=True)
    (rs.dir / "catch_up.json").write_text(json.dumps({"kinds": {"score": {"slots": 2}}}))
    rc.catch_up()
    assert FakePopen.calls[0]["cmd"][-3:] == ["run", "catch-up", "--json"]


def test_catch_up_with_nothing_missed_spawns_nothing(rc):
    assert rc.catch_up()["pending"] is False and FakePopen.calls == []


# --- current, history, detail, queue -------------------------------------------------------------------------

def test_current_none_when_idle(rc):
    assert rc.current() is None


def test_current_reports_budget_use_and_the_job_in_flight(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"])
    locks.acquire(rs.job_lock_path("abc123"), owner=f"run:{run['id']}", ttl_seconds=600, pid=999,
                  note="score abc123", pid_alive=lambda p: True)
    rs.save_attempt(run["id"], {"n": 1, "job_id": "old1", "outcome": "ok"})
    cur = rc.current()
    assert cur["id"] == run["id"] and cur["state"] == "running"
    assert cur["used"] == {"jobs": 1, "max_jobs": 4, "minutes": 6.0, "max_minutes": 30}
    assert cur["current_job"] == "abc123" and [a["job_id"] for a in cur["attempts"]] == ["old1"]


def test_history_marks_dead_runs_interrupted_and_pages(rc):
    rs = RunStore(rc.settings)
    ids = []
    for i in range(3):
        r = rs.new_run("score" if i != 1 else "scout", "manual", {}, NOW, run_id=f"20260926-10000{i}-x-000{i}")
        if i != 2:
            r.update(status="done", stop_reason="completed")
            rs.save_run(r)
        ids.append(r["id"])
    page = rc.history(limit=2)
    assert [r["id"] for r in page["runs"]] == [ids[2], ids[1]]
    assert page["runs"][0]["state"] == "interrupted" and page["runs"][0]["stop_reason"] == "interrupted"
    assert page["next_cursor"] == ids[1]
    rest = rc.history(limit=2, cursor=page["next_cursor"])
    assert [r["id"] for r in rest["runs"]] == [ids[0]] and rest["next_cursor"] is None
    assert [r["id"] for r in rc.history(kind="scout")["runs"]] == [ids[1]]


def test_detail(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    run.update(status="done", stop_reason="completed")
    rs.save_run(run)
    rs.save_attempt(run["id"], {"n": 1, "job_id": "j1", "outcome": "ok"})
    rs.log(run["id"], "hello")
    d = rc.detail(run["id"])
    assert d["attempts"][0]["job_id"] == "j1" and "hello" in d["log"] and d["state"] == "done"
    assert rc.detail("nope") is None


def test_queue_is_live_with_excluded_reasons(rc):
    ids = add_jobs(rc.settings, 2)
    Store(rc.settings).set_status(ids[1], "skipped", "not a fit")
    q = rc.queue("score", limit=5)
    assert [i["job_id"] for i in q["items"]] == [ids[0]] and "why" in q["items"][0]
    assert isinstance(q["excluded"], list)
    with pytest.raises(ValueError):
        rc.queue("scout")


# --- tail ----------------------------------------------------------------------------------------------------

def test_parse_event_plain_text():
    assert parse_event({"type": "system", "subtype": "init", "model": "m"})["type"] == "system"
    ev = parse_event({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Reading posting"}, {"type": "tool_use", "name": "Read", "input": {"file_path": "a"}}]}})
    assert ev == {"type": "assistant", "text": "Reading posting\n→ Read a"}
    assert parse_event({"type": "result", "result": "RESULT: {}", "is_error": False}) == {
        "type": "result", "text": "RESULT: {}", "error": False}
    assert parse_event({"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}) is None
    assert parse_event("not json") is None


def test_tail_reads_the_stream_and_the_log(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    run.update(status="done", stop_reason="completed")
    rs.save_run(run)
    n, stream = rs.next_attempt(run["id"])
    stream.write_text(json.dumps({"type": "system", "subtype": "init", "model": "fake"}) + "\n"
                      + json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}})
                      + "\n" + "{broken\n")
    rs.log(run["id"], "attempt 1 score j1 -> ok")
    events = list(rc.tail(run["id"], follow=False))
    assert {"type": "assistant", "text": "hi", "attempt": 1} in events
    assert any(e["type"] == "log" and "attempt 1" in e["text"] for e in events)


def test_tail_follows_until_the_run_ends(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"])
    polls = {"n": 0}

    def sleep(_):
        polls["n"] += 1
        if polls["n"] == 1:
            rs.log(run["id"], "late line")
        else:
            locks.release(rs.runner_lock_path, None, force=True)
            run.update(status="done", stop_reason="completed")
            rs.save_run(run)

    rc2 = make_rc(rc.settings, sleep=sleep)
    events = list(rc2.tail(run["id"], follow=True, poll_s=0))
    assert any("late line" in e.get("text", "") for e in events) and events[-1] == {"type": "end", "state": "done",
                                                                                   "stop_reason": "completed"}


# --- schedule, storage, advice -------------------------------------------------------------------------------

def test_schedule_status_with_a_fake_launchctl(rc):
    rc2 = make_rc(rc.settings, launchctl=lambda args: (1, "", ""))
    st = rc2.schedule_status()
    assert st["installed"] is False and st["loaded"] is False and set(st["next"]) >= {"scout", "score", "prepare"}


def test_storage_has_measure_and_snapshots(rc):
    out = rc.storage()
    assert "bytes" in out and "disk" in out and out["snapshots"] == []


def test_advise_and_apply_unknown(rc):
    assert "recommendations" in rc.advise()
    with pytest.raises(LookupError):
        rc.advise_apply("nope")


def test_stale_cancel_markers_are_cleared_on_the_next_start(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    run.update(status="done", stop_reason="cancelled")
    rs.save_run(run)
    marker = rs.dir / "ui" / f"cancel-{run['id']}"
    marker.parent.mkdir(parents=True)
    marker.write_text("x")
    rc.start("score")
    assert not marker.exists()
