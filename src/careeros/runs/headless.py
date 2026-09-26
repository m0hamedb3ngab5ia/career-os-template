"""One headless skill call: build the `claude -p` command, stream its output, classify the outcome.

`claude -p "/score-job data/jobs/<id>"` expands the skill. With `--output-format stream-json --verbose` the CLI
prints one JSON event per line: `system/init` (session id, MCP server status), `assistant` / `user` turns, an
optional `rate_limit_event`, and one final `result` event whose `result` is the skill's text. The skill's last
line is `RESULT: {json}`; `validate_result` checks it names this job and has the stage's required fields.

Classification prefers structured signals: the assistant message `error` field (`authentication_failed`,
`rate_limit`, `billing_error`), a `rate_limit_event` with status `rejected`, `permission_denials` on the result,
MCP servers reported `needs-auth`. Only when the call failed with none of those does it match the error text
against `runs.usage_limit_patterns` / `runs.auth_patterns`. A reset time in the text is never parsed or trusted.

Outcomes: ok | usage_limit | auth_required | permission_denied | timeout | cancelled | skill_error |
invalid_result | error.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from careeros.runs.config import RunsConfig

OUTCOMES = ("ok", "usage_limit", "auth_required", "permission_denied", "timeout", "cancelled", "skill_error",
            "invalid_result", "error")
# An outcome that ends the whole run at once (the next job would hit the same wall).
HARD_STOPS = ("usage_limit", "auth_required", "permission_denied", "cancelled")
RESULT_RE = re.compile(r"^\s*RESULT:\s*(\{.*\})\s*$")
SCORE_DECISIONS = ("prepare", "skip")
PREPARE_STATUSES = ("queued", "needs_review", "skipped")
_AUTH_ERRORS = ("authentication_failed",)
_LIMIT_ERRORS = ("rate_limit", "billing_error")


@dataclass
class HeadlessResult:
    exit_code: int | None = None
    timed_out: bool = False
    cancelled: bool = False
    session_id: str | None = None
    saw_result: bool = False
    result_text: str = ""
    is_error: bool = False
    subtype: str | None = None
    num_turns: int | None = None
    cost_usd: float | None = None
    permission_denials: list[dict[str, Any]] = field(default_factory=list)
    api_errors: list[str] = field(default_factory=list)
    rate_limit_rejected: bool = False
    mcp_status: dict[str, str] = field(default_factory=dict)
    stderr_tail: str = ""
    bad_lines: int = 0
    events: int = 0
    duration_s: float = 0.0

    def summary(self) -> dict[str, Any]:
        return {"exit_code": self.exit_code, "timed_out": self.timed_out, "cancelled": self.cancelled,
                "session_id": self.session_id, "subtype": self.subtype, "is_error": self.is_error,
                "num_turns": self.num_turns, "cost_usd": self.cost_usd,
                "permission_denials": [d.get("tool_name") for d in self.permission_denials],
                "api_errors": self.api_errors, "events": self.events, "duration_s": round(self.duration_s, 1)}


def build_command(cfg: RunsConfig, prompt: str, session_id: str | None = None) -> list[str]:
    cmd = list(cfg.headless_cmd)
    if cfg.allowed_tools and "--allowedTools" not in cmd and "--allowed-tools" not in cmd:
        cmd += ["--allowedTools", ",".join(cfg.allowed_tools)]
    if cfg.model and "--model" not in cmd:
        cmd += ["--model", cfg.model]
    if session_id and "--session-id" not in cmd:
        cmd += ["--session-id", session_id]
    return cmd + [prompt]


def feed(r: HeadlessResult, line: str) -> None:
    """Fold one stream-json line into `r`."""
    line = line.strip()
    if not line:
        return
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        r.bad_lines += 1
        return
    if not isinstance(ev, dict):
        r.bad_lines += 1
        return
    r.events += 1
    r.session_id = ev.get("session_id") or r.session_id
    kind = ev.get("type")
    if kind == "system" and ev.get("subtype") == "init":
        for s in ev.get("mcp_servers") or []:
            if isinstance(s, dict) and s.get("name"):
                r.mcp_status[str(s["name"])] = str(s.get("status") or "")
    elif kind == "assistant" and ev.get("error"):
        r.api_errors.append(str(ev["error"]))
    elif kind == "rate_limit_event":
        info = ev.get("rate_limit_info") or {}
        if str(info.get("status") or "").lower() == "rejected":
            r.rate_limit_rejected = True
    elif kind == "result":
        r.saw_result = True
        r.result_text = str(ev.get("result") or "")
        r.is_error = bool(ev.get("is_error"))
        r.subtype = ev.get("subtype")
        r.num_turns = ev.get("num_turns")
        r.cost_usd = ev.get("total_cost_usd")
        r.permission_denials = [d for d in ev.get("permission_denials") or [] if isinstance(d, dict)]


def parse_stream(lines: Iterable[str]) -> HeadlessResult:
    r = HeadlessResult(exit_code=0)
    for line in lines:
        feed(r, line)
    return r


def parse_result_line(text: str) -> dict[str, Any] | None:
    """The last `RESULT: {json}` line in the skill's text, parsed; None when absent or not JSON."""
    for line in reversed((text or "").splitlines()):
        m = RESULT_RE.match(line)
        if m:
            try:
                got = json.loads(m.group(1))
            except json.JSONDecodeError:
                return None
            return got if isinstance(got, dict) else None
    return None


def validate_result(stage: str, job_id: str, res: dict[str, Any]) -> list[str]:
    """Problems with a skill RESULT for this stage (empty = valid). A RESULT with `error` is valid here:
    `classify` reports it as `skill_error`."""
    probs = []
    if stage == "inbox_sync":  # not about one job; any RESULT object is its summary
        return probs
    if str(res.get("job_id") or "") != job_id:
        probs.append(f"RESULT job_id {res.get('job_id')!r} is not {job_id!r}")
    if "error" in res:
        return probs
    if stage == "score" and res.get("decision") not in SCORE_DECISIONS:
        probs.append(f"RESULT decision {res.get('decision')!r} not in {SCORE_DECISIONS}")
    if stage == "prepare" and res.get("status") not in PREPARE_STATUSES:
        probs.append(f"RESULT status {res.get('status')!r} not in {PREPARE_STATUSES}")
    return probs


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def classify(r: HeadlessResult, cfg: RunsConfig, stage: str, job_id: str) -> tuple[str, str]:
    """(outcome, detail). `detail` is for humans; it never carries a reset time parsed from text."""
    if r.cancelled:
        return "cancelled", "run cancelled"
    if r.timed_out:
        return "timeout", f"no final result within {cfg.job_timeout_minutes.get(stage)} min; process killed"
    if any(e in _AUTH_ERRORS for e in r.api_errors):
        return "auth_required", "Claude Code is not logged in (authentication_failed): run `claude` and /login"
    if r.rate_limit_rejected or any(e in _LIMIT_ERRORS for e in r.api_errors):
        return "usage_limit", "subscription usage limit reached; the run stops and retries at the next slot"
    need_auth = [n for n in cfg.required_mcp_servers
                 if any(n.lower() in name.lower() and st in ("needs-auth", "needs_auth", "failed")
                        for name, st in r.mcp_status.items())]
    if need_auth:
        return "auth_required", f"MCP server(s) {', '.join(need_auth)} need auth: run `claude` and /mcp once"
    res = parse_result_line(r.result_text) if r.saw_result else None
    failed = r.is_error or (r.exit_code not in (0, None)) or not r.saw_result
    if failed and res is None:
        text = f"{r.result_text}\n{r.stderr_tail}"
        if _matches(cfg.usage_limit_patterns, text):
            return "usage_limit", "subscription usage limit reached (from the error text)"
        if _matches(cfg.auth_patterns, text):
            return "auth_required", "Claude Code needs a login (from the error text): run `claude` and /login"
        if r.permission_denials:
            return "permission_denied", _denied(r)
        tail = (r.stderr_tail or r.result_text).strip().splitlines()[-1:] or [""]
        return "error", f"exit {r.exit_code}{'' if r.saw_result else ', no result event'}: {tail[0][:200]}"
    if res is None:
        if r.permission_denials:
            return "permission_denied", _denied(r)
        return "invalid_result", "no RESULT line in the skill output"
    probs = validate_result(stage, job_id, res)
    if probs:
        return "invalid_result", "; ".join(probs)
    if "error" in res:
        if "mcp_unavailable" in str(res["error"]).lower():
            return "auth_required", f"the skill could not use its MCP server ({res['error']}): run `claude`, /mcp"
        return "skill_error", str(res["error"])[:200]
    return "ok", ""


def _denied(r: HeadlessResult) -> str:
    tools = sorted({str(d.get("tool_name")) for d in r.permission_denials})
    return (f"tool(s) denied: {', '.join(tools)}; add them to pipeline.yaml llm.allowed_tools if the skill "
            "needs them")


# --------------------------------------------------------------------------------------------------------
# process runner (the default; tests inject their own `invoke`)
# --------------------------------------------------------------------------------------------------------

Invoke = Callable[[list[str], str, dict[str, str], float, Path], HeadlessResult]


def invoke(cmd: list[str], cwd: str, env: dict[str, str], timeout_s: float, stream_path: Path,
           cancel: threading.Event | None = None) -> HeadlessResult:
    """Run `cmd`, tee stdout (stream-json) to `stream_path`, fold events into a HeadlessResult. Kills the whole
    process group on timeout or cancel."""
    r = HeadlessResult()
    start = time.monotonic()
    stream_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True, bufsize=1)
    except (FileNotFoundError, PermissionError) as e:
        r.exit_code, r.stderr_tail = 127, f"{cmd[0]}: {e}"
        return r
    err_chunks: list[str] = []

    def pump_out() -> None:
        with stream_path.open("a", encoding="utf-8") as f:
            for line in proc.stdout:  # type: ignore[union-attr]
                f.write(line)
                f.flush()
                feed(r, line)

    def pump_err() -> None:
        for line in proc.stderr:  # type: ignore[union-attr]
            err_chunks.append(line)
            del err_chunks[:-50]

    threads = [threading.Thread(target=pump_out, daemon=True), threading.Thread(target=pump_err, daemon=True)]
    for t in threads:
        t.start()
    deadline = start + timeout_s
    while proc.poll() is None:
        if cancel is not None and cancel.is_set():
            r.cancelled = True
            _kill(proc)
            break
        if time.monotonic() >= deadline:
            r.timed_out = True
            _kill(proc)
            break
        time.sleep(0.1)
    proc.wait()
    for t in threads:
        t.join(timeout=5)
    r.exit_code = proc.returncode
    r.stderr_tail = "".join(err_chunks)[-2000:]
    r.duration_s = time.monotonic() - start
    return r


def _kill(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
