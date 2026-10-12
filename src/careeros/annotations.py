"""Résumé annotations (DEC-016, TASK-030): one model for AI/user suggestions and comments on a draft.

profile/resumes/<rid>/annotations.json  {items: [{id, kind: suggestion|comment, target_id, base, author: user|ai,
status: open|accepted|rejected|outdated, proposed, text, replies: [{text, author, at}], at}]}
`target_id` = a draft bullet id or a top-level text field (e.g. summary); `base` = its text when made. `outdated` is
computed on read (open item whose target no longer holds `base`), never stored. Accept = a user action: base check
(409, both texts) + the zero-fabrication guard (422), then one draft change author=ai via the TASK-029 write path;
accepting clears the bullet's `origin` (DEC-018 amendment: an AI text is never user-written).
No annotations.json yet: feedback.json items (the old review items) are read as comments; saved on the first write.
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
    return [{"id": i["id"], "kind": "comment", "target_id": None, "base": i.get("quote"), "author": "ai",
             "status": _OLD_STATE.get(i.get("state"), "open"), "proposed": None,
             "text": f"{i['section']}: {i['issue']} {i['suggestion']}",
             "replies": [{"text": c["text"], "author": "user", "at": c.get("at")} for c in i.get("comments") or []],
             "at": None} for i in fb.load(root, rid)["items"]]


def _load(root: Path, rid: str) -> list[dict[str, Any]]:
    p = _path(root, rid)
    return json.loads(p.read_text(encoding="utf-8"))["items"] if p.is_file() else _from_feedback(root, rid)


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


def list_items(root: Path, rid: str) -> list[dict[str, Any]]:
    items = _load(root, rid)
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
           author: str = "user") -> dict[str, Any]:
    if kind not in KINDS or author not in ("user", "ai"):
        raise ValueError("kind must be suggestion|comment and author user|ai")
    if kind == "suggestion" and (not isinstance(proposed, str) or not proposed.strip() or target_id is None):
        raise ValueError("a suggestion needs a target_id and non-empty proposed text")
    if kind == "comment" and not text.strip():
        raise ValueError("a comment needs text")
    with store._locked(root):
        base = None if target_id is None else _target(store.get_draft(root, rid)["resume"], target_id)[0]
        items = _load(root, rid)
        it = {"id": f"a{len(items) + 1}", "kind": kind, "target_id": target_id, "base": base, "author": author,
              "status": "open", "proposed": proposed.strip() if kind == "suggestion" else None,
              "text": text.strip(), "replies": [], "at": store._now()}
        _save(root, rid, [*items, it])
        return it


def reply(root: Path, rid: str, aid: str, text: str, *, author: str = "user") -> dict[str, Any]:
    if not text.strip() or author not in ("user", "ai"):
        raise ValueError("a reply needs text and author user|ai")
    with store._locked(root):
        items = _load(root, rid)
        it = _get(items, aid)
        it["replies"].append({"text": text.strip(), "author": author, "at": store._now()})
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
    """Apply an open suggestion to the draft as a change author=ai. Returns get_draft's shape.
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
        # allowed words: the annotation's own text + the user's replies (as apply's suggestion + comments)
        allowed = " ".join([it.get("text") or "", *(r["text"] for r in it["replies"] if r.get("author") == "user")])
        if reasons := fb.guard(it["base"], it["proposed"], allowed):
            raise fb.Rejected("; ".join(reasons))
        if bullet is None:
            doc[it["target_id"]] = it["proposed"]
        else:
            bullet["text"] = it["proposed"]
            bullet.pop("origin", None)
        out = store._commit(d, prev, doc, latest, "ai")
        it["status"] = "accepted"
        _save(root, rid, items)
        return out
