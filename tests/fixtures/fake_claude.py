"""A stand-in for `claude -p ... --output-format stream-json` in tests. Never calls a model.

Copied to <tmp>/bin/claude by the runs tests and put first on PATH. It reads the prompt (last argv),
handles `/score-job data/jobs/<id>` and `/prepare-job data/jobs/<id>` like the real skills would at the
file level, and prints stream-json events: `system/init`, one `assistant`, then the final `result`.

Behaviour per job: FAKE_CLAUDE_MODE (env) or data/jobs/<id>/.fake_mode (file, wins) is one of
  ok (default) | skip | usage_limit | rate_event | auth | deny | garbage | error_result | hang | exit1
FAKE_CLAUDE_ARGV=<path> appends the argv (JSON) to that file, so tests can check the command line.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> int:
    argv = sys.argv[1:]
    log = os.environ.get("FAKE_CLAUDE_ARGV")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(argv) + "\n")
    prompt = argv[-1] if argv else ""
    skill, _, job_rel = prompt.partition(" ")
    job_dir = Path.cwd() / job_rel.strip()
    job_id = job_dir.name
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    if (job_dir / ".fake_mode").exists():
        mode = (job_dir / ".fake_mode").read_text().strip()
    sid = argv[argv.index("--session-id") + 1] if "--session-id" in argv else str(uuid.uuid4())
    emit({"type": "system", "subtype": "init", "session_id": sid, "tools": ["Read", "Bash"],
          "mcp_servers": [], "model": "fake"})
    if mode == "hang":
        time.sleep(600)
        return 0
    if mode == "exit1":
        sys.stderr.write("fatal: something broke\n")
        return 1
    if mode == "auth":
        emit({"type": "assistant", "session_id": sid, "error": "authentication_failed",
              "message": {"content": [{"type": "text", "text": "Invalid API key · Please run /login"}]}})
        emit({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
              "result": "Invalid API key · Please run /login", "num_turns": 1, "duration_ms": 10})
        return 1
    if mode == "usage_limit":
        emit({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
              "result": "You've hit your limit · resets 3pm", "num_turns": 1, "duration_ms": 10})
        return 1
    if mode == "rate_event":
        emit({"type": "rate_limit_event", "session_id": sid,
              "rate_limit_info": {"status": "rejected", "resetsAt": 1900000000}})
        emit({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
              "result": "", "num_turns": 0, "duration_ms": 5})
        return 1
    if mode == "garbage":
        emit({"type": "result", "subtype": "success", "is_error": False, "session_id": sid,
              "result": "I scored it, looks good!", "num_turns": 3, "duration_ms": 10})
        return 0
    if mode == "error_result":
        text = "RESULT: " + json.dumps({"job_id": job_id, "error": "posting.json missing or empty"})
        emit({"type": "result", "subtype": "success", "is_error": False, "session_id": sid, "result": text,
              "num_turns": 1, "duration_ms": 10})
        return 0
    denials = []
    if mode == "deny":
        denials = [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "rm -rf /"}}]
    if skill == "/score-job":
        decision = "skip" if mode == "skip" else "prepare"
        score = {"job_id": job_id, "category": "swe_backend", "fit": 80, "tier": "C", "decision": decision,
                 "skip_reason": "below_min_fit" if decision == "skip" else None, "hard_filter_fails": []}
        (job_dir / "score.json").write_text(json.dumps(score))
        res = {"skill": "score-job", "job_id": job_id, "category": "swe_backend", "fit": 80, "tier": "C",
               "decision": decision, "skip_reason": score["skip_reason"], "hard_filter_fails": [],
               "profile_gap": None, "urgent": False, "closes_at": None}
    elif skill == "/prepare-job":
        st = json.loads((job_dir / "status.json").read_text()) if (job_dir / "status.json").exists() else {}
        st["status"] = "queued"
        st.setdefault("history", []).append({"status": "queued", "at": "2026-01-01T00:00:00+00:00", "note": "fake"})
        (job_dir / "status.json").write_text(json.dumps(st))
        (job_dir / "prepare.json").write_text(json.dumps({"job_id": job_id, "status": "queued", "qa_pass": True}))
        res = {"skill": "prepare-job", "job_id": job_id, "status": "queued", "tier": "C", "fit": 80,
               "decision": "prepare", "skip_reason": None, "qa_pass": True, "ACTION_ITEMS": []}
    else:
        emit({"type": "result", "subtype": "success", "is_error": False, "session_id": sid,
              "result": f"unknown skill {skill}", "num_turns": 1, "duration_ms": 10})
        return 0
    emit({"type": "assistant", "session_id": sid,
          "message": {"content": [{"type": "text", "text": f"working on {job_id}"}]}})
    emit({"type": "result", "subtype": "success", "is_error": False, "session_id": sid,
          "result": f"done.\nRESULT: {json.dumps(res)}", "num_turns": 4, "duration_ms": 1200,
          "total_cost_usd": 0.0, "permission_denials": denials})
    return 0


if __name__ == "__main__":
    sys.exit(main())
