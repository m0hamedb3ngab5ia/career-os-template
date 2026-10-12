"""Résumé annotations (DEC-016, TASK-030): one model for AI/user suggestions and comments on a draft.

profile/resumes/<rid>/annotations.json  {items: [{id, kind: suggestion|comment, target_id, base, author: user|ai,
status: open|accepted|rejected|outdated, proposed, text, replies: [{text, author, at, run?}], at, run?}]}
`run` = the writing run's id (CLI under CAREEROS_RUN_ID), absent for user/HTTP writes.
`target_id` = a draft bullet id or a top-level text field (e.g. summary); `base` = its text when made. `outdated` is
computed on read (open item whose target no longer holds `base`), never stored. Accept = a user action: base check
(409, both texts), then one draft change via the TASK-029 write path. AI suggestion: zero-fabrication guard (422),
change author=ai, bullet `origin` cleared (DEC-018 amendment: an AI text is never user-written). User suggestion:
no guard, change author=user. feedback.json items (the old review items) not yet stored are read as comments
(feedback.json is never written); they're saved on the next write.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from careeros import resume_feedback as fb
from careeros import resumes as store
from careeros.runs.atomic import write_json

KINDS = ("suggestion", "comment")
_OLD_STATE = {"applied": "accepted", "dismissed": "rejected"}  # open / redrafting -> open


def _path(root: Path, rid: str) -> Path:
    return store._dir(root, rid) / "annotations.json"


def _from_feedback(root: Path, rid: str) -> list[dict[str, Any]]:
    return [{"id": i["id"], "kind": "comment", "target_id": None, "base": (i.get("quotes") or [None])[0], "author": "ai",
             "status": _OLD_STATE.get(i.get("state"), "open"), "proposed": None,
             "text": f"{i['section']}: {i['issue']} {i['suggestion']}",
             "replies": [{"text": c["text"], "author": "user", "at": c.get("at")} for c in i.get("comments") or []],
             "at": None} for i in fb.load(root, rid)["items"]]


def _load(root: Path, rid: str) -> list[dict[str, Any]]:
    """Stored items + feedback.json items whose ids aren't stored yet (read-only: the review-save flow still writes
    feedback.json, so new review items stay visible; they're persisted here on the next write)."""
    p = _path(root, rid)
    items = json.loads(p.read_text(encoding="utf-8"))["items"] if p.is_file() else []
    have = {i["id"] for i in items}
    return items + [i for i in _from_feedback(root, rid) if i["id"] not in have]


def _next_id(items: list[dict[str, Any]]) -> str:
    nums = [int(i["id"][1:]) for i in items if i["id"][:1] == "a" and i["id"][1:].isdigit()]
    return f"a{max(nums, default=0) + 1}"


def _save(root: Path, rid: str, items: list[dict[str, Any]]) -> None:
    write_json(_path(root, rid), {"items": items}, ensure_ascii=False)


def _target(doc: dict[str, Any], tid: str) -> tuple[Any, dict[str, Any] | None]:
    """(current text, the bullet dict or None for a field); LookupError if `tid` is no bullet / text field."""
    flat = store._flat(doc)
    if ("bullet", tid) in flat:
        b = flat[("bullet", tid)][0]
        return b.get("text"), b
    if ("field", tid) in flat and isinstance(flat[("field", tid)][0], str):
        return flat[("field", tid)][0], None
    raise LookupError(f"draft has no bullet or text field {tid!r}")


def _get(items: list[dict[str, Any]], aid: str) -> dict[str, Any]:
    it = next((i for i in items if i["id"] == aid), None)
    if it is None:
        raise LookupError(f"no annotation {aid!r}")
    return it


def _by_run(it: dict[str, Any], run: str) -> bool:
    return it.get("run") == run or any(r.get("run") == run for r in it.get("replies") or [])


def run_count(root: Path, rid: str, run: str) -> int:
    """Annotations + replies written by one run (`run` = its CAREEROS_RUN_ID; TASK-033b)."""
    items = _load(root, rid)
    return sum(i.get("run") == run for i in items) + sum(r.get("run") == run for i in items for r in i["replies"])


def list_items(root: Path, rid: str, run: str | None = None) -> list[dict[str, Any]]:
    """`run`: only the annotations that run created or replied to (Apply-comment polling, TASK-033b)."""
    items = _load(root, rid)
    if run is not None:
        items = [i for i in items if _by_run(i, run)]
    try:
        doc = store.get_draft(root, rid)["resume"]
    except LookupError:  # no structured version: nothing to compare against
        return items
    for it in items:
        if it["status"] == "open" and it.get("target_id") is not None:
            try:
                cur = _target(doc, it["target_id"])[0]
            except LookupError:
                cur = None
            if cur != it["base"]:
                it["status"] = "outdated"
    return items


def create(root: Path, rid: str, *, kind: str, target_id: str | None, text: str = "", proposed: str | None = None,
           author: str = "user", run: str | None = None) -> dict[str, Any]:
    if kind not in KINDS or author not in ("user", "ai"):
        raise ValueError("kind must be suggestion|comment and author user|ai")
    if kind == "suggestion" and (not isinstance(proposed, str) or not proposed.strip() or target_id is None):
        raise ValueError("a suggestion needs a target_id and non-empty proposed text")
    if kind == "comment" and not text.strip():
        raise ValueError("a comment needs text")
    with store._locked(root):
        base = None if target_id is None else _target(store.get_draft(root, rid)["resume"], target_id)[0]
        items = _load(root, rid)
        it = {"id": _next_id(items), "kind": kind, "target_id": target_id, "base": base, "author": author,
              "status": "open", "proposed": proposed.strip() if kind == "suggestion" else None,
              "text": text.strip(), "replies": [], "at": store._now(), **({"run": run} if run else {})}
        _save(root, rid, [*items, it])
        return it


def reply(root: Path, rid: str, aid: str, text: str, *, author: str = "user", run: str | None = None) -> dict[str, Any]:
    if not text.strip() or author not in ("user", "ai"):
        raise ValueError("a reply needs text and author user|ai")
    with store._locked(root):
        items = _load(root, rid)
        it = _get(items, aid)
        it["replies"].append({"text": text.strip(), "author": author, "at": store._now(), **({"run": run} if run else {})})
        _save(root, rid, items)
        return it


def reject(root: Path, rid: str, aid: str) -> dict[str, Any]:
    with store._locked(root):
        items = _load(root, rid)
        it = _get(items, aid)
        if it["status"] != "open":
            raise store.Refused(f"annotation {aid} is {it['status']}")
        it["status"] = "rejected"
        _save(root, rid, items)
        return it


def accept(root: Path, rid: str, aid: str) -> dict[str, Any]:
    """Apply an open suggestion to the draft as one change by its author. Returns get_draft's shape.
    AI suggestion: zero-fabrication guard, change author=ai, bullet `origin` cleared. User suggestion: the user's
    own words, so no guard and a change author=user with `origin` left as is (as put_draft, the user-edit path).
    One lock for check + write, so a concurrent draft save can't slip in between."""
    with store._locked(root):
        items = _load(root, rid)
        it = _get(items, aid)
        if it["kind"] != "suggestion" or it["status"] != "open":
            raise store.Refused(f"annotation {aid} is a {it['status']} {it['kind']}, not an open suggestion")
        d, prev, latest = store._draft_state(root, rid)
        doc = store.migrate(copy.deepcopy(prev["resume"]))
        try:
            cur, bullet = _target(doc, it["target_id"])
        except LookupError:
            cur, bullet = None, None
        if cur != it["base"]:
            raise store.Conflict(f"{it['target_id']!r} changed since the suggestion: expected {it['base']!r}, "
                                 f"now {cur!r}", it["base"], cur)
        ai = it["author"] != "user"
        if ai:  # allowed words: the user's replies only (an AI annotation's own text never widens the guard)
            allowed = " ".join(r["text"] for r in it["replies"] if r.get("author") == "user")
            if reasons := fb.guard(it["base"] or "", it["proposed"], allowed):
                raise fb.Rejected("; ".join(reasons))
        if bullet is None:
            doc[it["target_id"]] = it["proposed"]
        else:
            bullet["text"] = it["proposed"]
            if ai:
                bullet.pop("origin", None)
        out = store._commit(d, prev, doc, latest, "ai" if ai else "user")
        it["status"] = "accepted"
        _save(root, rid, items)
        return out
