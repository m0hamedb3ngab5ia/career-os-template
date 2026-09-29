"""careeros.ui.services.runs.RunControl: start / cancel / pause / catch-up / queue / history / tail, with fakes
(no subprocess, no signals): a fake Popen, fake pid and command-line lookups, a tmp RunStore."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from careeros.models import Posting
from careeros.runs import locks
from careeros.runs.store import RunStore
from careeros.store import Store
from careeros.ui.services import step as step_mod
from careeros.ui.services.runs import Busy, NotSetUp, Paused, RunControl, classify_cmdline
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
    kw.setdefault("started", lambda pid: None)
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
    assert call["cmd"] == ["/venv/bin/python", "-m", "careeros.cli", "run", "score", "--preset", "small", "--json"]
    assert call["start_new_session"] is True and call["cwd"] == str(rc.settings.root)
    assert call["env"] == {"PATH": "/bin", "CAREEROS_ROOT": str(rc.settings.root)}  # root via env: no spaces in argv
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
    assert FakePopen.calls[0]["cmd"] == ["/venv/bin/python", "-m", "careeros.ui.services.step", "scout",
                                         "--run-id", out["run_id"]]
    assert "-scout-" in out["run_id"]
    assert FakePopen.calls[0]["env"]["CAREEROS_ROOT"] == str(rc.settings.root)
    assert FakePopen.calls[0]["start_new_session"] is True and out["kind"] == "scout"


def test_inbox_sync_is_not_set_up_while_disabled(rc):
    with pytest.raises(NotSetUp) as e:
        rc.start_step("inbox_sync")
    assert "inbox" in str(e.value).lower() and FakePopen.calls == []


def test_start_qa_step_passes_the_job_and_a_run_id(rc):
    out = rc.start_step("qa", "nw01")
    assert FakePopen.calls[0]["cmd"][3:] == ["qa", "--job", "nw01", "--run-id", out["run_id"]]
    assert "-qa-" in out["run_id"]


@pytest.mark.parametrize("kind,job", [("qa", None), ("scout", "nw01"), ("qa", "../x")])
def test_qa_step_needs_exactly_a_job_id(rc, kind, job):
    with pytest.raises(ValueError):
        rc.start_step(kind, job)
    assert FakePopen.calls == []


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


def test_qa_step_records_its_job_and_result(settings):
    res = {"pass": False, "summary": {"hard_fail": 1, "soft_fail": 0}}
    rec = step_mod.run_step(settings, "qa", job_id="nw01", run_id="r-qa-1",
                            actions={"qa": lambda: ("ok", "fail: 1 hard, 0 soft", lambda: res)})
    run = RunStore(settings).load_run("r-qa-1")
    assert rec["id"] == "r-qa-1" and run["job_id"] == "nw01" and run["result"] == res
    assert run["stop_reason"] == "completed"


def test_cancelled_scout_discards_what_it_stored(settings, monkeypatch):
    from careeros import scout
    from careeros.store import Store

    st = Store(settings)
    (st.jobs_dir / "old1").mkdir()
    st.seen_file.write_text("old\n")

    def partial(settings, store, *a, **k):
        (store.jobs_dir / "new1").mkdir()
        store.seen_file.write_text("old\nnew\n")
        store.history_file.write_text("{}")
        raise KeyboardInterrupt

    monkeypatch.setattr(scout, "run_scout", partial)
    rec = step_mod.run_step(settings, "scout")
    assert rec["stop_reason"] == "cancelled"
    assert sorted(d.name for d in st.jobs_dir.iterdir()) == ["old1"]
    assert st.seen_file.read_text() == "old\n" and not st.history_file.exists()



def test_cancel_during_the_scout_tracker_sync_discards_what_it_stored(settings, monkeypatch):
    from careeros import scout
    from careeros.runs import tick
    from careeros.store import Store

    st = Store(settings)
    st.seen_file.write_text("old\n")

    def stored(settings, store, *a, **k):
        (store.jobs_dir / "new1").mkdir()
        store.seen_file.write_text("old\nnew\n")
        return {}

    def sync(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(scout, "run_scout", stored)
    monkeypatch.setattr(scout, "sync_to_tracker", sync)
    monkeypatch.setattr(tick, "scout_detail", lambda s: "")
    rec = step_mod.run_step(settings, "scout")
    assert rec["stop_reason"] == "cancelled"
    assert list(st.jobs_dir.iterdir()) == [] and st.seen_file.read_text() == "old\n"

def test_step_output_streams_to_run_log_while_running(settings, rc):
    """Scout prints progress; each line reaches run.log (and so the tail endpoint) before the step ends."""
    import sys

    seen: list[list[str]] = []

    def scout():
        print("scanning board 1")
        print("half", end="")
        print(" line done", file=sys.stderr)
        rid = RunStore(settings).run_ids()[-1]
        seen.append([e["text"] for e in rc.tail(rid, follow=False) if e["type"] == "log"])
        return "ok", "fetched=1"

    rec = step_mod.run_step(settings, "scout", actions={"scout": scout})
    assert any(t.endswith("scanning board 1") for t in seen[0])
    log = RunStore(settings).read_log(rec["id"])
    assert "scanning board 1" in log and "half line done" in log


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



def test_cancel_before_the_step_holds_its_lock_stops_it_at_start(rc):
    rid = rc.start_step("scout")["run_id"]
    assert rc.cancel(rid)["status"] == "cancelling"
    assert rc.cancel("never-started")["status"] == "idle"  # only a step this UI spawned
    ran = []
    rec = step_mod.run_step(rc.settings, "scout", run_id=rid, actions={"scout": lambda: ran.append(1) or ("ok", "")})
    assert rec["stop_reason"] == "cancelled" and ran == []

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
            run.update(status="done", stop_reason="completed", counters={"attempted": 1, "ok": 0, "failed": 1})
            rs.save_run(run)

    rc2 = make_rc(rc.settings, sleep=sleep)
    events = list(rc2.tail(run["id"], follow=True, poll_s=0))
    # the counters ride on the end frame: a "completed" run whose only job failed must not chain to the next stage
    assert any("late line" in e.get("text", "") for e in events) and events[-1] == {
        "type": "end", "state": "done", "stop_reason": "completed", "counters": {"attempted": 1, "ok": 0, "failed": 1}}


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


# --- review round 1 ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cmd,want", [
    ("/v/bin/python -m careeros.cli --root /r run score --json", "run"),
    ("/v/bin/python -m careeros.cli --root /r run prepare --preset small --json", "run"),
    ("/v/bin/python -m careeros.cli --root /r run catch-up --json", "run"),
    ("/v/bin/careeros run score", "run"),
    ("/v/bin/python /v/bin/careeros --root /r run prepare", "run"),
    ("/v/bin/python -m careeros.ui.services.step --root /r scout", "step"),
    ("/v/bin/python -m careeros.ui.services.step --root /r inbox_sync", "step"),
    ("/v/bin/python -m careeros.cli --root /r tick", "tick"),
    ("/v/bin/python -m careeros.cli --root /r ui --port 8765", None),
    ("/v/bin/python -m careeros.cli run status", None),
    ("vim /repo/careeros/notes.txt", None),
    ("/usr/bin/python3 -m http.server careeros run score", None),
    ("/v/bin/python -m careeros.ui.services.step --root /r apply", None),
    ("", None),
])
def test_classify_cmdline_matches_argv_tokens(cmd, want):
    assert classify_cmdline(cmd) == want


def _held_run(rc, pid=777):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"], pid=pid)
    return run


def test_cancel_refuses_careeros_processes_that_are_not_a_run(rc):
    _held_run(rc)
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append(pid),
                  cmdline=lambda pid: "/v/bin/python -m careeros.cli --root /r ui --port 8765")
    assert rc2.cancel()["status"] == "refused" and sent == []


def test_cancel_refuses_a_pid_that_started_after_the_lock(rc):
    _held_run(rc)
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append(pid),
                  started=lambda pid: datetime.now(timezone.utc) + timedelta(minutes=5))
    out = rc2.cancel()
    assert out["status"] == "refused" and "reused" in out["detail"] and sent == []


def test_cancel_allows_a_pid_that_started_before_the_lock(rc):
    _held_run(rc)
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append(pid),
                  started=lambda pid: datetime.now(timezone.utc) - timedelta(minutes=5))
    assert rc2.cancel()["status"] == "cancelling" and sent == [777]


@pytest.mark.parametrize("exc,status", [(ProcessLookupError, "idle"), (PermissionError, "refused")])
def test_cancel_kill_errors(rc, exc, status):
    _held_run(rc)

    def kill(pid, sig):
        raise exc

    out = make_rc(rc.settings, kill=kill).cancel()
    assert out["status"] == status
    assert not list((RunStore(rc.settings).dir / "ui").glob("cancel-*"))


def test_run_state_rereads_a_run_that_finished_between_reads(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"], pid=777)

    def finishes(pid):  # the run completes while the lock is being checked
        done = {**run, "status": "done", "stop_reason": "completed"}
        rs.save_run(done)
        locks.release(rs.runner_lock_path, None, force=True)
        return False

    rc2 = make_rc(rc.settings, pid_alive=finishes)
    got = rc2.history()["runs"][0]
    assert got["state"] == "done" and got["stop_reason"] == "completed"


def test_catch_up_cancel_leaves_unstarted_kinds_pending(settings):
    import threading

    from careeros.runs.tick import load_catch_up, run_catch_up

    rs = RunStore(settings)
    rs.dir.mkdir(parents=True, exist_ok=True)
    (rs.dir / "catch_up.json").write_text(json.dumps({"kinds": {"score": {"slots": 1}, "prepare": {"slots": 1}}}))
    cancel = threading.Event()
    called = []

    def score(trigger):
        called.append("score")
        cancel.set()
        return "cancelled", "run x"

    out = run_catch_up(settings, cancel=cancel, actions={"score": score, "prepare": lambda t: called.append("p")})
    assert called == ["score"] and out["ran"] == ["score"] and out["left"] == ["prepare"]
    assert list(load_catch_up(rs)["kinds"]) == ["prepare"]


def test_default_actions_pass_cancel_to_batches_and_inbox(settings, monkeypatch):
    import threading

    from careeros.runs import service, tick

    seen = {}
    monkeypatch.setattr(service, "run_batch", lambda *a, **kw: seen.setdefault("batch", kw) and
                        {"stop_reason": "completed", "id": "r"} or {"stop_reason": "completed", "id": "r"})
    monkeypatch.setattr(service, "run_skill", lambda *a, **kw: seen.setdefault("skill", kw) and
                        {"stop_reason": "completed", "id": "r"} or {"stop_reason": "completed", "id": "r"})
    cancel = threading.Event()
    acts = tick.default_actions(settings, cancel=cancel)
    acts["score"]("catch_up")
    acts["inbox_sync"]("catch_up")
    assert seen["batch"]["cancel"] is cancel and seen["skill"]["cancel"] is cancel


def test_schedule_install_writes_the_plist_and_loads_it(rc, tmp_path):
    calls = []
    agents = tmp_path / "LaunchAgents"
    rc2 = make_rc(rc.settings, launchctl=lambda args: calls.append(args) or (0, "", ""), agents_dir=agents,
                  which=lambda name: None)
    out = rc2.schedule_install()
    import plistlib

    plist = plistlib.loads(Path(out["plist"]).read_bytes())
    assert Path(out["plist"]).parent == agents
    assert plist["ProgramArguments"][-3:] == ["--root", str(Path(rc.settings.root).absolute()), "tick"]
    assert plist["ProgramArguments"][0] == "/venv/bin/python"
    assert any(a[0] == "bootstrap" for a in calls) and "claude" in out["warning"]
    rc3 = make_rc(rc.settings, launchctl=lambda args: (0, "", ""), agents_dir=agents, which=lambda n: "/bin/claude")
    assert rc3.schedule_install()["warning"] is None


def test_schedule_uninstall_boots_out_and_removes(rc, tmp_path):
    calls = []
    agents = tmp_path / "LaunchAgents"
    rc2 = make_rc(rc.settings, launchctl=lambda args: calls.append(args) or (0, "", ""), agents_dir=agents,
                  which=lambda n: "/bin/claude")
    rc2.schedule_install()
    calls.clear()
    out = rc2.schedule_uninstall()
    assert out["removed"] is True and calls[0][0] == "bootout" and calls[0][1].endswith(out["label"])
    assert not Path(out["plist"]).exists()


@pytest.fixture
def inbox_on(rc):
    rc.settings.pipeline["schedule"]["jobs"]["inbox_sync"]["enabled"] = True
    return rc


def test_inbox_sync_busy_when_the_runner_lock_is_held(inbox_on):
    hold_runner(RunStore(inbox_on.settings), "20260926-110000-score-abcd")
    with pytest.raises(Busy):
        inbox_on.start_step("inbox_sync")


def test_inbox_sync_paused(inbox_on):
    RunStore(inbox_on.settings).set_pause(None, "", NOW - timedelta(hours=1))
    with pytest.raises(Paused):
        inbox_on.start_step("inbox_sync")


def test_inbox_sync_spawns_the_step(inbox_on):
    inbox_on.start_step("inbox_sync")
    assert FakePopen.calls[0]["cmd"] == ["/venv/bin/python", "-m", "careeros.ui.services.step", "inbox_sync"]


def test_step_main_exit_codes(temp_root, monkeypatch, capsys):
    from careeros.config import Settings

    rs = RunStore(Settings.load(temp_root))
    lk = locks.acquire(step_mod.step_lock_path(rs, "scout"), owner="step:x", ttl_seconds=600, pid=os.getpid())
    assert step_mod.main(["--root", str(temp_root), "scout"]) == 5
    locks.release(step_mod.step_lock_path(rs, "scout"), lk.token)

    def boom():
        raise RuntimeError("board down")

    monkeypatch.setattr(step_mod, "default_actions", lambda s, j=None: {"scout": boom})
    assert step_mod.main(["--root", str(temp_root), "scout"]) == 1
    monkeypatch.setattr(step_mod, "default_actions", lambda s, j=None: {"scout": lambda: ("ok", "fine")})
    assert step_mod.main(["--root", str(temp_root), "scout"]) == 0


def test_run_inbox_sync_turns_sigterm_into_cancel(settings, monkeypatch):
    from careeros.runs import service

    seen = {}
    before = signal.getsignal(signal.SIGTERM)

    def fake_run_skill(*a, cancel, **kw):
        os.kill(os.getpid(), signal.SIGTERM)
        seen["cancelled"] = cancel.wait(5)
        return {"id": "r", "stop_reason": "cancelled"}

    monkeypatch.setattr(service, "run_skill", fake_run_skill)
    assert step_mod.run_inbox_sync(settings)["stop_reason"] == "cancelled" and seen["cancelled"] is True
    assert signal.getsignal(signal.SIGTERM) == before


def test_tail_holds_back_a_half_written_line(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"])
    n, stream = rs.next_attempt(run["id"])
    line = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "whole"}]}})
    stream.write_text(line[:20])
    polls = {"n": 0}

    def sleep(_):
        polls["n"] += 1
        if polls["n"] == 1:
            with stream.open("a") as f:
                f.write(line[20:] + "\n")
        else:
            locks.release(rs.runner_lock_path, None, force=True)
            rs.save_run({**run, "status": "done", "stop_reason": "completed"})

    events = list(make_rc(rc.settings, sleep=sleep).tail(run["id"], follow=True, poll_s=0))
    assert [e for e in events if e["type"] == "assistant"] == [{"type": "assistant", "text": "whole", "attempt": 1}]


def test_ps_cmdline_of_this_process_is_not_truncated():
    from careeros.ui.services.runs import ps_cmdline

    # A child with a known argv well past 80 columns; under pytest-xdist this process's own argv has no "pytest".
    marker = "careeros-cmdline-probe-" + "x" * 120
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", marker])
    try:
        got = ps_cmdline(child.pid)  # an exact argv on Linux, a joined line on macOS
    finally:
        child.kill()
        child.wait()
    assert marker in (" ".join(got) if isinstance(got, list) else got)


# --- review round 2 ------------------------------------------------------------------------------------------

SPACED = "/Users/a/My Jobs/career-os"


@pytest.mark.parametrize("cmd,root,want", [
    ("/Users/a/My Jobs/career-os/.venv/bin/python -m careeros.cli run score --json", SPACED, "run"),
    (f"/v/bin/python -m careeros.cli --root {SPACED} run prepare --json", SPACED, "run"),
    (f"/v/bin/python -m careeros.ui.services.step --root {SPACED} scout", SPACED, "step"),
    (f"/v/bin/python -m careeros.cli --root {SPACED} tick", SPACED, "tick"),
    ("/Users/a/My Jobs/career-os/.venv/bin/careeros run catch-up", SPACED, "run"),
    (["/v/bin/python", "-m", "careeros.cli", "--root", SPACED, "run", "score", "--json"], None, "run"),
    (["/v/bin/python", "-m", "careeros.ui.services.step", "--root", SPACED, "prune"], None, "step"),
    (["/v/bin/python", "-m", "careeros.cli", "--root", SPACED, "ui"], None, None),
])
def test_classify_with_a_root_that_has_spaces(cmd, root, want):
    assert classify_cmdline(cmd, root=root) == want


def test_tail_rereads_the_run_before_its_end_event(rc):
    rs = RunStore(rc.settings)
    run = running_run(rs)
    hold_runner(rs, run["id"], pid=777)
    calls = {"n": 0}

    def alive(pid):  # the run finishes while tail checks the lock
        calls["n"] += 1
        rs.save_run({**run, "status": "done", "stop_reason": "completed"})
        locks.release(rs.runner_lock_path, None, force=True)
        return False

    events = list(make_rc(rc.settings, pid_alive=alive).tail(run["id"], follow=True, poll_s=0))
    assert events[-1] == {"type": "end", "state": "done", "stop_reason": "completed", "counters": run.get("counters")}


def test_cancel_reaches_a_catch_up_between_batches(rc):
    """A catch-up running scout or prune holds only tick.lock; Cancel must still reach it."""
    rs = RunStore(rc.settings)
    locks.acquire(rs.dir / "tick.lock", owner="catch-up", ttl_seconds=600, pid=888, pid_alive=lambda p: True)
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append((pid, sig)),
                  cmdline=lambda pid: "/v/bin/python -m careeros.cli run catch-up --json")
    out = rc2.cancel()
    assert out["status"] == "cancelling" and sent == [(888, signal.SIGTERM)]


def test_cancel_ignores_a_scheduled_tick_lock(rc):
    rs = RunStore(rc.settings)
    locks.acquire(rs.dir / "tick.lock", owner="tick", ttl_seconds=600, pid=888, pid_alive=lambda p: True)
    assert make_rc(rc.settings, kill=lambda *a: pytest.fail("no kill")).cancel()["status"] == "idle"


def test_cancel_reaches_a_later_catch_up_after_an_earlier_one_was_cancelled(rc):
    """The cancel marker belongs to one holder: a later catch-up (new pid) must not look 'already stopping'."""
    rs = RunStore(rc.settings)
    tick = rs.dir / "tick.lock"
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append((pid, sig)),
                  cmdline=lambda pid: "/v/bin/python -m careeros.cli run catch-up --json")
    locks.acquire(tick, owner="catch-up", ttl_seconds=600, pid=888, pid_alive=lambda p: True)
    assert rc2.cancel()["status"] == "cancelling"
    assert rc2.cancel()["status"] == "already_stopping"
    locks.release(tick, None, force=True)
    locks.acquire(tick, owner="catch-up", ttl_seconds=600, pid=889, pid_alive=lambda p: True)
    out = rc2.cancel()
    assert out["status"] == "cancelling" and sent == [(888, signal.SIGTERM), (889, signal.SIGTERM)]


# --- review round 2 ------------------------------------------------------------------------------------------

def test_starting_a_step_keeps_the_live_catch_up_cancel_marker(rc):
    rs = RunStore(rc.settings)
    locks.acquire(rs.dir / "tick.lock", owner="catch-up", ttl_seconds=3600, pid=888, pid_alive=lambda p: True)
    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append((pid, sig)),
                  cmdline=lambda pid: "/venv/bin/python -m careeros.cli --root /r run catch-up --json")
    assert rc2.cancel()["status"] == "cancelling"
    rc2.start_step("scout")
    out = rc2.cancel()
    assert out["status"] == "already_stopping" and out["run_id"] == "catch-up" and sent == [(888, signal.SIGTERM)]


def test_cancel_marker_removed_between_exists_and_read_is_no_marker(rc, monkeypatch):
    _held_run(rc)
    marker_dir = RunStore(rc.settings).dir / "ui"
    marker_dir.mkdir(parents=True, exist_ok=True)
    real = Path.read_text

    def racing(self, *a, **kw):
        if self.name.startswith("cancel-"):
            self.unlink()
            raise FileNotFoundError(self)
        return real(self, *a, **kw)

    sent = []
    rc2 = make_rc(rc.settings, kill=lambda pid, sig: sent.append(pid))
    (marker_dir / f"cancel-{rc2._holder_of(None)[0]}").write_text("1 old\n")
    monkeypatch.setattr(Path, "read_text", racing)
    assert rc2.cancel()["status"] == "cancelling" and sent == [777]


# --- one job (`--job`) -----------------------------------------------------------------------------------------

def _prepared(settings, jid: str, tier: str = "B", status: str = "queued") -> None:
    store = Store(settings)
    store._write(jid, "score.json", {"job_id": jid, "category": "swe_backend", "fit": 80, "tier": tier,
                                     "decision": "prepare", "reasons": ["t"]})
    store._write(jid, "prepare.json", {"job_id": jid, "qa_pass": True, "status": status})
    store.set_status(jid, status, "test")


def test_start_one_job_spawns_run_with_job_force_and_a_run_id(rc, settings):
    (jid,) = add_jobs(settings, 1)
    out = rc.start("score", job_id=jid)
    cmd = FakePopen.calls[0]["cmd"]
    assert cmd[:5] == ["/venv/bin/python", "-m", "careeros.cli", "run", "score"]
    assert cmd[cmd.index("--job") + 1] == jid and "--force" not in cmd and "--max-jobs" not in cmd
    assert cmd[cmd.index("--run-id") + 1] == out["run_id"] and cmd[-1] == "--json"
    assert out["run_id"].startswith(NOW.astimezone().strftime("%Y%m%d-%H%M%S") + "-score-")
    assert out["kind"] == "score" and out["started"]


def test_start_one_job_refuses_a_job_that_is_not_a_candidate_before_spawning(rc, settings):
    from careeros.runs.runner import JobNotRunnable

    (jid,) = add_jobs(settings, 1)
    Store(settings).set_status(jid, "skipped", "t")
    with pytest.raises(JobNotRunnable) as e:
        rc.start("prepare", job_id=jid)
    assert e.value.reasons == {jid: "status skipped"} and FakePopen.calls == []
    with pytest.raises(JobNotRunnable) as e:
        rc.start("prepare", job_id=add_jobs(settings, 2)[1])
    assert list(e.value.reasons.values()) == ["not scored"]
    with pytest.raises(JobNotRunnable) as e:
        rc.start("score", job_id="nope")
    assert e.value.reasons == {"nope": "not found"}


def test_apply_needs_a_job_and_runs_tier_a_and_b(rc, settings):
    with pytest.raises(ValueError):
        rc.start("apply")
    jid, other = add_jobs(settings, 2)
    _prepared(settings, jid, tier="A")
    out = rc.start("apply", job_id=jid)
    cmd = FakePopen.calls[0]["cmd"]
    assert cmd[3:5] == ["run", "apply"] and cmd[cmd.index("--job") + 1] == jid and out["kind"] == "apply"
    _prepared(settings, other, tier="B")
    rc.start("apply", job_id=other)
    assert FakePopen.calls[-1]["cmd"][FakePopen.calls[-1]["cmd"].index("--job") + 1] == other


def test_force_is_passed_through_for_a_rerun(rc, settings):
    (jid,) = add_jobs(settings, 1)
    _prepared(settings, jid, status="queued")
    rc.start("prepare", job_id=jid, force=True)
    assert "--force" in FakePopen.calls[0]["cmd"]


def test_active_run_for_names_the_running_job_run(rc, settings):
    (jid,) = add_jobs(settings, 1)
    assert rc.active_run_for(jid) is None
    run = rc.rs.new_run("apply", "manual", {"max_jobs": 1, "max_minutes": 30}, NOW, counters={"attempted": 0},
                        queue=[{"job_id": jid, "rank": 1, "score": 1, "why": ""}])
    locks.acquire(rc.rs.runner_lock_path, owner=f"run:{run['id']}", ttl_seconds=3600, pid=999, note="apply",
                  pid_alive=lambda p: True)
    assert rc.active_run_for(jid) is None and rc.queued_in_run(jid) == run["id"]  # picked, not yet in flight
    locks.acquire(rc.rs.job_lock_path(jid), owner=f"run:{run['id']}", ttl_seconds=600, pid=999,
                  note=f"apply {jid}", pid_alive=lambda p: True)
    assert rc.active_run_for(jid) == run["id"] and rc.active_run_for("other") is None


def test_active_run_for_is_only_the_job_in_flight_and_queued_jobs_are_reported_apart(rc, settings):
    jid, other = add_jobs(settings, 2)
    run = rc.rs.new_run("prepare", "manual", {"max_jobs": 2, "max_minutes": 30}, NOW, counters={"attempted": 0},
                        queue=[{"job_id": jid, "rank": 1, "score": 1, "why": ""},
                               {"job_id": other, "rank": 2, "score": 1, "why": ""}])
    locks.acquire(rc.rs.runner_lock_path, owner=f"run:{run['id']}", ttl_seconds=3600, pid=999, note="prepare",
                  pid_alive=lambda p: True)
    locks.acquire(rc.rs.job_lock_path(jid), owner=f"run:{run['id']}", ttl_seconds=600, pid=999,
                  note=f"prepare {jid}", pid_alive=lambda p: True)
    assert rc.active_run_for(jid) == run["id"] and rc.queued_in_run(jid) is None
    assert rc.active_run_for(other) is None and rc.queued_in_run(other) == run["id"]
    assert rc.active_run_for("nope") is None and rc.queued_in_run("nope") is None


def _exhaust(settings, kind, jid, n=2):
    from careeros.runs.failures import Failures
    from careeros.runs.store import RunStore

    for _ in range(n):
        Failures(RunStore(settings)).record(kind, jid, "invalid_result", "bad json", "r1", NOW)


def test_start_one_job_refuses_a_job_out_of_retries_before_spawning(rc, settings):
    from careeros.runs.runner import JobNotRunnable

    (jid,) = add_jobs(settings, 1)
    _exhaust(settings, "score", jid)
    with pytest.raises(JobNotRunnable) as e:
        rc.start("score", job_id=jid)
    assert e.value.reasons == {jid: "failed 2 times (last: invalid_result); see Action Items"}
    assert FakePopen.calls == []


def test_start_error_reads_the_refusal_the_spawned_run_wrote(rc, settings):
    (jid,) = add_jobs(settings, 1)
    out = rc.start("score", job_id=jid)
    assert out["run_id"] in Path(out["output"]).name
    assert rc.start_error(out["run_id"]) is None  # nothing written yet
    Path(out["output"]).write_text('{"error": "run score: x: status skipped", "kind": "score"}\n')
    assert rc.start_error(out["run_id"]) == "run score: x: status skipped"
    Path(out["output"]).write_text("Traceback ...\n")
    assert rc.start_error(out["run_id"]) is None
    assert rc.start_error("../etc") is None and rc.start_error("nope") is None
