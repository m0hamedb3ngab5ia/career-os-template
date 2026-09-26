"""The scheduled inbox_sync job: one headless /inbox-sync call, Gmail MCP must be logged in (fake invoker)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from careeros.runs.headless import parse_stream
from careeros.runs.runner import RunBusy
from careeros.runs.service import run_skill
from careeros.runs import locks
from careeros.runs.store import RunStore

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 27, 8, 5, tzinfo=timezone.utc)


def init(status="connected"):
    return json.dumps({"type": "system", "subtype": "init", "session_id": "s1",
                       "mcp_servers": [{"name": "claude.ai Gmail", "status": status}]})


def result(res: dict):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "s1",
                       "result": "RESULT: " + json.dumps(res)})


class Fake:
    def __init__(self, lines):
        self.lines, self.calls = lines, []

    def __call__(self, cmd, cwd, env, timeout_s, stream_path):
        self.calls.append({"cmd": cmd, "timeout_s": timeout_s})
        Path(stream_path).write_text("{}")
        return parse_stream(self.lines)


def go(settings, fake, **kw):
    settings.pipeline = {**settings.pipeline, "runs": {"preflight_doctor": False}}
    return run_skill(settings, "inbox_sync", "inbox-sync", mcp_servers=["gmail"],
                     allowed_tools_extra=["mcp__claude_ai_Gmail__search_threads"], invoke=fake,
                     now=lambda: NOW, **kw)


def test_ok_run_is_recorded_with_the_gmail_tools(settings):
    fake = Fake([init(), result({"skill": "inbox-sync", "updated": 2})])
    rec = go(settings, fake, trigger="schedule")
    assert rec["kind"] == "inbox_sync" and rec["stop_reason"] == "completed" and rec["trigger"] == "schedule"
    cmd = fake.calls[0]["cmd"]
    assert cmd[-1] == "/inbox-sync"
    assert "mcp__claude_ai_Gmail__search_threads" in cmd[cmd.index("--allowedTools") + 1]
    assert fake.calls[0]["timeout_s"] == 20 * 60
    (att,) = RunStore(settings).load_attempts(rec["id"])
    assert att["outcome"] == "ok" and att["result"]["updated"] == 2


def test_gmail_needing_auth_stops_with_auth_required(settings):
    rec = go(settings, Fake([init("needs-auth"), result({"skill": "inbox-sync"})]))
    assert rec["stop_reason"] == "auth_required" and "gmail" in rec["detail"].lower()


def test_skill_reporting_gmail_unavailable_is_auth_required(settings):
    rec = go(settings, Fake([init(), result({"skill": "inbox-sync", "error": "gmail_mcp_unavailable"})]))
    assert rec["stop_reason"] == "auth_required"


def test_other_failure_is_an_error_stop(settings):
    rec = go(settings, Fake([init(), json.dumps({"type": "result", "result": "done, no RESULT"})]))
    assert rec["stop_reason"] == "error" and rec["counters"]["failed"] == 1


def test_busy_runner(settings):
    settings.pipeline = {**settings.pipeline, "runs": {"preflight_doctor": False}}
    locks.acquire(RunStore(settings).runner_lock_path, owner="run:x", ttl_seconds=600, now=NOW)
    with pytest.raises(RunBusy):
        run_skill(settings, "inbox_sync", "inbox-sync", invoke=Fake([]), now=lambda: NOW)


def test_paused_does_not_call(settings):
    RunStore(settings).set_pause(until=None, reason="x", now=NOW)
    fake = Fake([])
    rec = go(settings, fake)
    assert rec["stop_reason"] == "paused" and fake.calls == []
