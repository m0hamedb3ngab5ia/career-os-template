"""`careeros run catch-up` cancel: batches stop at a safe point (the cancel event), steps without one (scout, prune)
are interrupted, and whatever did not run stays pending."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from careeros.runs import locks
from careeros.runs.store import RunStore
from careeros.runs.tick import CancelFlag, load_catch_up, run_catch_up

pytestmark = pytest.mark.unit


def pending(settings, kinds):
    rs = RunStore(settings)
    rs.dir.mkdir(parents=True, exist_ok=True)
    (rs.dir / "catch_up.json").write_text(json.dumps({"kinds": {k: {"slots": 1} for k in kinds}}))
    return rs


def test_soft_only_while_a_batch_is_in_flight(settings):
    pending(settings, ["scout", "score", "prune"])
    cancel = CancelFlag()
    seen = {}

    def act(kind):
        def run(trigger):
            seen[kind] = cancel.soft
            return "ok", ""
        return run

    run_catch_up(settings, cancel=cancel, actions={k: act(k) for k in ("scout", "score", "prune")})
    assert seen == {"scout": False, "score": True, "prune": False}


def test_interrupted_scout_keeps_the_rest_pending_and_frees_tick_lock(settings):
    rs = pending(settings, ["scout", "score"])
    called = []

    def scout(trigger):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_catch_up(settings, cancel=CancelFlag(), actions={"scout": scout, "score": lambda t: called.append(1)})
    assert called == [] and set(load_catch_up(rs)["kinds"]) == {"scout", "score"}
    assert locks.read(rs.dir / "tick.lock") is None


def test_kinds_that_ran_before_an_interrupt_are_not_pending_again(settings):
    rs = pending(settings, ["scout", "score", "prune"])

    def prune(trigger):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_catch_up(settings, cancel=CancelFlag(), actions={"scout": lambda t: ("ok", ""),
                                                            "score": lambda t: ("completed", ""), "prune": prune})
    assert set(load_catch_up(rs)["kinds"]) == {"prune"}


def test_signal_handler_hard_when_no_batch_or_second_signal():
    from careeros.cli import _cancel_on_signals

    with _cancel_on_signals(hard=True) as cancel:
        cancel.soft = False
        with pytest.raises(KeyboardInterrupt):
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(1)
    with _cancel_on_signals(hard=True) as cancel:
        cancel.soft = True
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(0.05)
        assert cancel.is_set()
        with pytest.raises(KeyboardInterrupt):
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(1)
    with _cancel_on_signals() as cancel:  # `careeros run score`: always soft
        os.kill(os.getpid(), signal.SIGTERM)
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(0.05)
        assert cancel.is_set()


def test_headless_invoke_kills_its_child_when_interrupted(tmp_path):
    import _thread

    from careeros.runs.headless import invoke

    pidfile = tmp_path / "pid"
    child = [sys.executable, "-c", f"import os,time; open({str(pidfile)!r},'w').write(str(os.getpid())); "
             "time.sleep(60)"]
    t = threading.Timer(1.0, _thread.interrupt_main)
    t.start()
    with pytest.raises(KeyboardInterrupt):
        invoke(child, str(tmp_path), dict(os.environ), 30, tmp_path / "s.jsonl")
    pid = int(pidfile.read_text())
    for _ in range(50):
        if subprocess.run(["ps", "-o", "pid=", "-p", str(pid)], capture_output=True).returncode != 0:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, signal.SIGKILL)
        pytest.fail("child survived")
