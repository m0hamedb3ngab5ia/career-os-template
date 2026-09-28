"""Opt-in smoke test against the real `claude` CLI: CAREEROS_LIVE_SMOKE=1 pytest -m live.

Fakes in test_runs_headless.py cannot catch CLI behaviour changes (e.g. the claude-in-chrome MCP loading only with
--chrome in headless mode). This runs the exact apply command once, with a trivial prompt, and checks the init event.
Needs Chrome open with the Claude extension signed in. Costs one short Claude turn.
"""
import os
import shutil
import subprocess

import pytest

from careeros.runs.config import RunsConfig
from careeros.runs.headless import build_command, chrome_connected, parse_stream

# conftest points HOME at a temp dir for every test; the real CLI needs the real one for its login.
REAL_HOME = os.environ.get("HOME", "")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("CAREEROS_LIVE_SMOKE") != "1", reason="set CAREEROS_LIVE_SMOKE=1"),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not on PATH"),
]


def test_real_apply_command_loads_claude_in_chrome(tmp_path):
    cmd = build_command(RunsConfig(), "Reply with the single word ok.", kind="apply")
    cmd[-1:-1] = ["--max-turns", "1"]
    out = subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True, timeout=180,
                         env={**os.environ, "HOME": REAL_HOME}).stdout
    r = parse_stream(out.splitlines())
    assert r.saw_init, f"no init event; stdout head: {out[:300]}"
    assert chrome_connected(r), f"claude-in-chrome not connected at startup: {r.mcp_status}"
