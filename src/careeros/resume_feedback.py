"""Résumé review feedback lifecycle (REQ-094..097, UC-002, FLOW-002).

profile/resumes/<rid>/feedback.json  {review: {state: running|done|failed, run, v, at}, items: [{id, section, issue,
suggestion, state: open|redrafting|applied|dismissed, comments: [{text, at}], reason, v}]}
The review-resume skill saves items (`careeros resume review-save`); edit-resume rewrites one item's section
(`resume apply-edit`, guarded -> new version author=ai) or re-drafts a commented item (`resume redraft`).
A hand edit (`edit`) is a new version author=user with no guard (the user owns the facts).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from careeros import resumes as store
from careeros.qa import TOOL_ALLOWLIST, WORD_RE, number_tokens
from careeros.qa_ext.consistency import DEFAULT_SENIORITY_WORDS
from careeros.runs.atomic import write_text

# a rewrite may not upgrade the claim (REQ-095: supported -> led); seniority words count too
STRONGER = {"led", "lead", "owned", "spearheaded", "headed", "directed", "managed", "drove", "architected",
            "founded", "launched", "championed", "oversaw", *DEFAULT_SENIORITY_WORDS}
ITEM_KEYS = ("section", "issue", "suggestion")


class Rejected(ValueError):
    """The zero-fabrication guard (or the item's state) refuses the rewrite -> 422; the item stays open."""


def _path(root: Path, rid: str) -> Path:
    return store._dir(root, rid) / "feedback.json"


def load(root: Path, rid: str) -> dict[str, Any]:
    p = _path(root, rid)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"review": None, "items": []}


def _save(root: Path, rid: str, fb: dict[str, Any]) -> dict[str, Any]:
    write_text(_path(root, rid), json.dumps(fb, indent=2, ensure_ascii=False) + "\n")
    return fb


def _latest(root: Path, rid: str) -> int:
    return store.get(root, rid)["versions"][-1]["n"]


def set_review(root: Path, rid: str, state: str, run: str | None = None) -> dict[str, Any]:
    with store._locked(root):
        fb = load(root, rid)
        fb["review"] = {"state": state, "run": run, "v": _latest(root, rid), "at": store._now()}
        return _save(root, rid, fb)


def save_review(root: Path, rid: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """A finished review's items replace the previous review's (REQ-094)."""
    if not isinstance(items, list) or not all(
            isinstance(i, dict) and all(isinstance(i.get(k), str) and i[k].strip() for k in ITEM_KEYS) for i in items):
        raise ValueError(f"feedback items need non-empty {', '.join(ITEM_KEYS)}")
    with store._locked(root):
        fb, v = load(root, rid), _latest(root, rid)
        fb["items"] = [{"id": f"f{n}", **{k: i[k].strip() for k in ITEM_KEYS}, "state": "open", "comments": [],
                        "reason": None, "v": v} for n, i in enumerate(items, 1)]
        fb["review"] = {**(fb.get("review") or {}), "state": "done", "v": v, "at": store._now()}
        return _save(root, rid, fb)


def _change(root: Path, rid: str, fid: str, **kw: Any) -> dict[str, Any]:
    with store._locked(root):
        fb = load(root, rid)
        it = next((i for i in fb["items"] if i["id"] == fid), None)
        if it is None:
            raise LookupError(f"résumé {rid!r} has no feedback item {fid!r}")
        if it["state"] in ("applied", "dismissed"):
            raise Rejected(f"feedback item {fid} is already {it['state']}")
        if "comment" in kw:
            it["comments"].append({"text": kw.pop("comment"), "at": store._now()})
        it.update(kw)
        _save(root, rid, fb)
        return it


def comment(root: Path, rid: str, fid: str, text: str) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("comment must not be empty")
    return _change(root, rid, fid, comment=text.strip(), state="redrafting")


def redraft(root: Path, rid: str, fid: str, suggestion: str) -> dict[str, Any]:
    if not suggestion.strip():
        raise ValueError("suggestion must not be empty")
    return _change(root, rid, fid, suggestion=suggestion.strip(), state="open", reason=None)


def dismiss(root: Path, rid: str, fid: str) -> dict[str, Any]:
    return _change(root, rid, fid, state="dismissed")


def _cap_terms(text: str) -> set[str]:
    """Capitalised words not at line/sentence start (employers, titles, tools), like qa's tool audit.
    ponytail: a lowercase new tool or one opening a line slips past; the stronger-verb and number checks still run."""
    out = set()
    for line in text.splitlines():
        for sent in re.split(r"(?<=[.!?])\s+", line.strip().lstrip("-•*·").strip()):
            out |= {w.rstrip(".,;:").strip("/") for w in WORD_RE.findall(sent)[1:] if w[0].isupper()}
    return {w for w in out if len(w) >= 2}


def guard(prev: str, new: str) -> list[str]:
    """Zero-fabrication check of an AI rewrite against the previous version (REQ-095). Empty = ok."""
    words = {w.rstrip(".,;:").lower() for w in WORD_RE.findall(prev)}
    reasons = []
    if nums := sorted(number_tokens(new) - number_tokens(prev)):
        reasons.append(f"adds numbers/dates not in the previous version: {', '.join(nums)}")
    if terms := sorted(t for t in _cap_terms(new) if t.lower() not in words and t.lower() not in TOOL_ALLOWLIST):
        reasons.append(f"adds names/titles/tools not in the previous version: {', '.join(terms)}")
    new_words = {w.rstrip(".,;:").lower() for w in WORD_RE.findall(new)}
    if strong := sorted((new_words & STRONGER) - words):
        reasons.append(f"makes a stronger claim than the previous version: {', '.join(strong)}")
    return reasons


def apply(root: Path, rid: str, fid: str, text: str) -> dict[str, Any]:
    """Guarded AI rewrite of one open item -> new version author=ai source=<fid>; item applied. Guard fails ->
    Rejected, no version, item open with the reason."""
    it = next((i for i in load(root, rid)["items"] if i["id"] == fid), None)
    if it is None:
        raise LookupError(f"résumé {rid!r} has no feedback item {fid!r}")
    if it["state"] != "open":  # FLOW-002: only open items apply
        raise Rejected(f"feedback item {fid} is {it['state']}")
    prev = store.version(root, rid, _latest(root, rid))["text"]
    if reasons := guard(prev, text):
        _change(root, rid, fid, state="open", reason="; ".join(reasons))
        raise Rejected("; ".join(reasons))
    meta = store.add_text(root, rid, text, author="ai", source=fid)
    _change(root, rid, fid, state="applied", reason=None, applied_v=meta["versions"][-1]["n"])
    return meta


def edit(root: Path, rid: str, text: str) -> dict[str, Any]:
    """Hand edit (REQ-097): new version author=user, previous versions unchanged, no guard."""
    return store.add_text(root, rid, text, author="user", source="edit")
