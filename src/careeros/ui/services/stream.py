"""stream-json events (`claude -p --output-format stream-json`) -> short plain events for the Runs log pane."""
from __future__ import annotations

import json
from typing import Any

_TOOL_ARG_KEYS = ("file_path", "path", "pattern", "command", "url", "query")


def _tool_line(block: dict[str, Any]) -> str:
    args = block.get("input") or {}
    arg = next((str(args[k]) for k in _TOOL_ARG_KEYS if isinstance(args, dict) and args.get(k)), "")
    return f"→ {block.get('name', 'tool')}" + (f" {arg[:160]}" if arg else "")


def parse_event(raw: Any) -> dict[str, Any] | None:
    """One stream-json line (str or dict) -> {type, text[, error]}, or None for noise (tool results, bad JSON)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    if kind == "system":
        return {"type": "system", "text": f"{raw.get('subtype') or 'system'} (model {raw.get('model') or '?'})"}
    if kind == "assistant":
        parts = []
        for b in (raw.get("message") or {}).get("content") or []:
            if b.get("type") == "text" and b.get("text"):
                parts.append(str(b["text"]).strip())
            elif b.get("type") == "tool_use":
                parts.append(_tool_line(b))
        return {"type": "assistant", "text": "\n".join(p for p in parts if p)} if parts else None
    if kind == "result":
        return {"type": "result", "text": str(raw.get("result") or ""), "error": bool(raw.get("is_error"))}
    if kind == "rate_limit_event":
        info = raw.get("rate_limit_info") or {}
        return {"type": "system", "text": f"rate limit: {info.get('status') or 'unknown'}"}
    return None
