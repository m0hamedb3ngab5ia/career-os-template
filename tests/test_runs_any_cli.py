"""REQ-158: `careeros run` drives Claude Code, Codex CLI or Gemini CLI (`pipeline.yaml: llm.cli`).

Commands are only constructed and streams only parsed here: no real CLI is ever called."""
from __future__ import annotations

import json

import pytest

from careeros.config import ConfigError
from careeros.doctor import FAIL, PASS, check_tools
from careeros.runs.config import CLI_CMDS, DEFAULT_HEADLESS_CMD, load_runs_config
from careeros.runs.headless import build_command, parse_result_line, parse_stream


def cfg_for(**llm):
    return load_runs_config(type("S", (), {"pipeline": {"llm": llm}})())


def lines(*events) -> list[str]:
    return [json.dumps(e) for e in events]


def test_cli_defaults_to_claude_and_each_cli_has_its_own_command():
    assert cfg_for().cli == "claude" and cfg_for().headless_cmd == DEFAULT_HEADLESS_CMD
    assert cfg_for(cli="codex").headless_cmd == CLI_CMDS["codex"]
    assert cfg_for(cli="gemini").headless_cmd == CLI_CMDS["gemini"]


def test_unknown_cli_is_a_config_error():
    with pytest.raises(ConfigError, match="llm.cli"):
        cfg_for(cli="aider")


def test_headless_cmd_for_another_binary_is_a_config_error():
    with pytest.raises(ConfigError, match="llm.cli"):
        cfg_for(cli="codex", headless_cmd=DEFAULT_HEADLESS_CMD)


def test_codex_command_is_non_interactive_sandboxed_and_reads_the_skill_file():
    cmd = build_command(cfg_for(cli="codex", model_hint="gpt-5"), "/score-job data/jobs/abc", session_id="s1",
                        kind="score")
    assert cmd[:3] == ["codex", "exec", "--json"]
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"
    assert cmd[cmd.index("-m") + 1] == "gpt-5"
    for claude_only in ("--allowedTools", "--append-system-prompt", "--setting-sources", "--session-id", "-p"):
        assert claude_only not in cmd
    assert cmd[-1] == "Read .claude/skills/score-job/SKILL.md and follow it for: data/jobs/abc"


def test_gemini_command_streams_and_passes_the_prompt_with_p():
    cmd = build_command(cfg_for(cli="gemini"), "/prepare-job data/jobs/abc", kind="prepare")
    assert cmd[0] == "gemini" and cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--approval-mode" in cmd and "--allowedTools" not in cmd
    assert cmd[-2:] == ["-p", "Read .claude/skills/prepare-job/SKILL.md and follow it for: data/jobs/abc"]


def test_claude_keeps_the_slash_command():
    assert build_command(cfg_for(), "/score-job data/jobs/abc", kind="score")[-1] == "/score-job data/jobs/abc"


def test_codex_stream_yields_the_last_agent_message_as_the_result():
    r = parse_stream(lines(
        {"type": "thread.started", "thread_id": "t-1"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "working"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": 'done\nRESULT: {"status": "ok"}'}},
        {"type": "turn.completed", "usage": {"input_tokens": 1}}))
    assert r.saw_init and r.saw_result and not r.is_error and r.session_id == "t-1"
    assert parse_result_line(r.result_text) == {"status": "ok"}


def test_codex_failed_turn_is_an_error():
    r = parse_stream(lines({"type": "thread.started", "thread_id": "t-1"},
                           {"type": "turn.failed", "error": {"message": "usage limit reached"}}))
    assert r.saw_result and r.is_error and "usage limit reached" in r.result_text


def test_gemini_stream_joins_assistant_deltas_and_reads_status():
    r = parse_stream(lines(
        {"type": "init", "session_id": "g-1", "model": "gemini-2.5-pro"},
        {"type": "message", "role": "user", "content": "go"},
        {"type": "message", "role": "assistant", "content": "done\nRESULT: ", "delta": True},
        {"type": "message", "role": "assistant", "content": '{"status": "ok"}', "delta": True},
        {"type": "result", "status": "success", "stats": {}}))
    assert r.saw_init and r.saw_result and not r.is_error and r.session_id == "g-1"
    assert parse_result_line(r.result_text) == {"status": "ok"}
    bad = parse_stream(lines({"type": "init", "session_id": "g-1"}, {"type": "result", "status": "error"}))
    assert bad.is_error


@pytest.mark.parametrize("cli", ["codex", "gemini"])
def test_doctor_checks_the_configured_cli_binary(cli):
    missing = {c.name: c.level for c in check_tools(lambda t: None, env={}, cli=cli)}
    assert missing[cli] == FAIL and "claude" not in missing
    found = {c.name: c.level for c in check_tools(lambda t: f"/bin/{t}", env={}, cli=cli)}
    assert found[cli] == PASS
