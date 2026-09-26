from __future__ import annotations

import json

import pytest

from careeros.runs.config import load_runs_config
from careeros.runs.headless import (
    HeadlessResult,
    build_command,
    classify,
    parse_result_line,
    parse_stream,
    validate_result,
)

pytestmark = pytest.mark.unit


class S:
    pipeline: dict = {}


CFG = load_runs_config(S())


def lines(*events) -> list[str]:
    return [json.dumps(e) for e in events]


def ok_events(result_text: str, **extra):
    return lines({"type": "system", "subtype": "init", "session_id": "sid-1", "mcp_servers": []},
                 {"type": "assistant", "session_id": "sid-1", "message": {"content": [{"type": "text", "text": "hi"}]}},
                 {"type": "result", "subtype": "success", "is_error": False, "session_id": "sid-1",
                  "result": result_text, "num_turns": 3, "total_cost_usd": 0.01, **extra})


def test_build_command_appends_allowed_tools_session_and_prompt():
    cmd = build_command(CFG, "/score-job data/jobs/abc", session_id="u-1")
    assert cmd[0] == "claude" and cmd[-1] == "/score-job data/jobs/abc"
    i = cmd.index("--allowedTools")
    assert cmd[i + 1] == ",".join(CFG.allowed_tools)
    assert cmd[cmd.index("--session-id") + 1] == "u-1"


def test_build_command_adds_model_when_set():
    cfg = load_runs_config(type("S", (), {"pipeline": {"llm": {"model_hint": "sonnet"}}})())
    cmd = build_command(cfg, "/x", session_id="u")
    assert cmd[cmd.index("--model") + 1] == "sonnet"


def test_parse_stream_reads_init_and_final_result():
    r = parse_stream(ok_events("done\nRESULT: {}"))
    assert r.session_id == "sid-1" and r.result_text == "done\nRESULT: {}" and r.num_turns == 3
    assert r.saw_result and not r.is_error


def test_parse_stream_ignores_non_json_lines():
    r = parse_stream(["garbage", *ok_events("x")])
    assert r.saw_result and r.bad_lines == 1


def test_parse_result_line_takes_the_last_result():
    text = 'RESULT: {"a": 1}\nmore\nRESULT: {"job_id": "j", "decision": "prepare"}\n'
    assert parse_result_line(text) == {"job_id": "j", "decision": "prepare"}
    assert parse_result_line("no result here") is None
    assert parse_result_line("RESULT: {broken") is None


@pytest.mark.parametrize("stage,res,ok", [
    ("score", {"job_id": "j", "decision": "prepare"}, True),
    ("score", {"job_id": "j", "decision": "skip", "skip_reason": "below_min_fit"}, True),
    ("score", {"job_id": "j", "decision": "maybe"}, False),
    ("score", {"job_id": "other", "decision": "prepare"}, False),
    ("prepare", {"job_id": "j", "status": "queued"}, True),
    ("prepare", {"job_id": "j", "status": "needs_review"}, True),
    ("prepare", {"job_id": "j", "status": "applied"}, False),
    ("prepare", {"job_id": "j"}, False),
])
def test_validate_result(stage, res, ok):
    problems = validate_result(stage, "j", res)
    assert (problems == []) is ok, problems


def res_of(events, exit_code=0, **kw) -> HeadlessResult:
    r = parse_stream(events)
    r.exit_code = exit_code
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def test_classify_ok():
    r = res_of(ok_events('RESULT: {"job_id": "j", "decision": "prepare"}'))
    assert classify(r, CFG, "score", "j")[0] == "ok"


def test_classify_timeout_and_cancel_win():
    assert classify(res_of([], timed_out=True), CFG, "score", "j")[0] == "timeout"
    assert classify(res_of([], cancelled=True), CFG, "score", "j")[0] == "cancelled"


def test_classify_structured_auth_error():
    ev = lines({"type": "assistant", "error": "authentication_failed", "message": {"content": []}},
               {"type": "result", "is_error": True, "result": "whatever"})
    assert classify(res_of(ev, exit_code=1), CFG, "score", "j")[0] == "auth_required"


def test_classify_structured_rate_limit():
    ev = lines({"type": "assistant", "error": "rate_limit", "message": {"content": []}},
               {"type": "result", "is_error": True, "result": ""})
    assert classify(res_of(ev, exit_code=1), CFG, "score", "j")[0] == "usage_limit"


def test_classify_rate_limit_event_rejected_but_never_parses_reset_text():
    ev = lines({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1900000000}},
               {"type": "result", "is_error": True, "result": "limit reached, resets 3pm"})
    out, detail = classify(res_of(ev, exit_code=1), CFG, "score", "j")
    assert out == "usage_limit" and "3pm" not in detail


def test_classify_rate_limit_warning_is_not_a_stop():
    ev = [json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning"}}),
          *ok_events('RESULT: {"job_id": "j", "decision": "prepare"}')]
    assert classify(res_of(ev), CFG, "score", "j")[0] == "ok"


@pytest.mark.parametrize("text,want", [
    ("You've hit your limit · resets 3pm", "usage_limit"),
    ("Claude AI usage limit reached|1700000000", "usage_limit"),
    ("Invalid API key · Please run /login", "auth_required"),
    ("OAuth token has expired. Please obtain a new token", "auth_required"),
    ("Something else went wrong", "error"),
])
def test_classify_error_text_fallback(text, want):
    ev = lines({"type": "result", "is_error": True, "result": text})
    assert classify(res_of(ev, exit_code=1), CFG, "score", "j")[0] == want


def test_classify_mcp_needs_auth_only_for_required_servers():
    ev = [json.dumps({"type": "system", "subtype": "init", "mcp_servers": [{"name": "gmail", "status": "needs-auth"}]}),
          *ok_events('RESULT: {"job_id": "j", "decision": "prepare"}')[1:]]
    assert classify(res_of(ev), CFG, "score", "j")[0] == "ok"
    cfg = load_runs_config(type("S", (), {"pipeline": {"runs": {"required_mcp_servers": ["gmail"]}}})())
    assert classify(res_of(ev), cfg, "score", "j")[0] == "auth_required"


def test_classify_permission_denied():
    ev = ok_events("I could not run the command", permission_denials=[{"tool_name": "Bash"}])
    out, detail = classify(res_of(ev), CFG, "score", "j")
    assert out == "permission_denied" and "Bash" in detail


def test_denials_with_a_valid_result_are_ok_but_reported():
    ev = ok_events('RESULT: {"job_id": "j", "decision": "prepare"}', permission_denials=[{"tool_name": "WebFetch"}])
    r = res_of(ev)
    assert classify(r, CFG, "score", "j")[0] == "ok"
    assert r.permission_denials


def test_classify_invalid_and_skill_error():
    assert classify(res_of(ok_events("looks good")), CFG, "score", "j")[0] == "invalid_result"
    ev = ok_events('RESULT: {"job_id": "j", "error": "posting.json missing or empty"}')
    out, detail = classify(res_of(ev), CFG, "score", "j")
    assert out == "skill_error" and "posting.json" in detail


def test_classify_nonzero_exit_without_result():
    r = res_of([], exit_code=1, stderr_tail="fatal: boom")
    out, detail = classify(r, CFG, "score", "j")
    assert out == "error" and "boom" in detail


def test_missing_binary_is_an_error():
    r = res_of([], exit_code=127, stderr_tail="claude: not found")
    assert classify(r, CFG, "score", "j")[0] == "error"
