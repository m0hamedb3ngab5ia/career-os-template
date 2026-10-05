"""Résumé review feedback lifecycle (REQ-094..097, UC-002, FLOW-002).

profile/resumes/<rid>/feedback.json  {review: {state: running|done|failed, run, v, at}, items: [{id, section, issue,
suggestion, state: open|redrafting|applied|dismissed, comments: [{text, at}], reason, v}]}
The review-resume skill saves items (`careeros resume review-save`); edit-resume rewrites one item's section
(`resume apply-edit`, guarded -> new version author=ai) or re-drafts a commented item (`resume redraft`).
A hand edit (UI only, PUT .../text) is a new version author=user with no guard (the user owns the facts).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from careeros import resumes as store
from careeros.qa import WORD_RE, number_tokens
from careeros.qa_ext.consistency import DEFAULT_SENIORITY_WORDS
from careeros.runs.atomic import write_text

# a rewrite may not upgrade the claim (REQ-095: supported -> led): verb stems (any inflection) + seniority words
STRONGER_STEMS = ("lead", "led", "manag", "own", "spearhead", "direct", "architect", "found", "launch", "champion",
                  "overs", "head", "drove", "driv", "buil")
NUMBER_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                "twenty", "thirty", "forty", "fifty", "hundred", "hundreds", "thousand", "thousands", "million",
                "millions", "billion", "half", "halved", "double", "doubled", "triple", "tripled", "twice",
                "quarter", "dozen", "dozens", "percent"}
GRAMMAR = {"i", "a", "an", "the", "and", "or", "of", "for", "with", "in", "on", "at", "to", "by", "from", "as", "is",
           "are", "was", "were", "be", "via", "per", "across", "into", "using", "vs"}
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


def _words(text: str) -> set[str]:
    return {w.strip(".,;:/").lower() for w in WORD_RE.findall(text)} - {""}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s", "ion", "e"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def guard(prev: str, new: str, allowed: str = "") -> list[str]:
    """Zero-fabrication check of an AI rewrite against the previous version (REQ-095). Empty = ok.
    ponytail: every new word (any case/position) must come from `prev` or `allowed` (the item's suggestion +
    comments), compared by crude stem; a synonym in neither is refused. Add a synonym list if refusals annoy."""
    words, new_words = _words(prev), _words(new)
    reasons = []
    if nums := sorted((number_tokens(new) - number_tokens(prev)) | ((new_words & NUMBER_WORDS) - words)):
        reasons.append(f"adds numbers/dates not in the previous version: {', '.join(nums)}")
    ok = {_stem(w) for w in words | _words(allowed)}
    if terms := sorted(w for w in new_words - words - GRAMMAR - NUMBER_WORDS if _stem(w) not in ok):
        reasons.append(f"adds words not in the previous version or the suggestion: {', '.join(terms)}")
    strong = {w for w in new_words - words if w in DEFAULT_SENIORITY_WORDS} | {
        s for s in STRONGER_STEMS if any(w.startswith(s) for w in new_words) and not any(w.startswith(s) for w in words)}
    if strong:
        reasons.append(f"makes a stronger claim than the previous version: {', '.join(sorted(strong))}")
    return reasons


def _allowed(it: dict[str, Any]) -> str:
    return " ".join([it["suggestion"], *(c["text"] for c in it["comments"])])


def apply(root: Path, rid: str, fid: str, text: str, *, base: int) -> dict[str, Any]:
    """Guarded AI rewrite of one open item, written from version `base` -> new version author=ai source=<fid>;
    item applied. Guard fails or `base` is not the latest -> Rejected, no version, item open with the reason.
    One lock for check + write, so a hand edit can't slip in between (and gets refused instead of overwritten)."""
    with store._locked(root):
        fb = load(root, rid)
        it = next((i for i in fb["items"] if i["id"] == fid), None)
        if it is None:
            raise LookupError(f"résumé {rid!r} has no feedback item {fid!r}")
        if it["state"] != "open":  # FLOW-002: only open items apply
            raise Rejected(f"feedback item {fid} is {it['state']}")
        latest = _latest(root, rid)
        reasons = [f"résumé changed since v{base}: latest is v{latest}; re-run Apply"] if base != latest else \
            guard(store.version(root, rid, latest)["text"], text, _allowed(it))
        if reasons:
            it.update(reason="; ".join(reasons))
            _save(root, rid, fb)
            raise Rejected("; ".join(reasons))
        meta = store.add_text(root, rid, text, author="ai", source=fid, lock=False)
        it.update(state="applied", reason=None, applied_v=meta["versions"][-1]["n"])
        _save(root, rid, fb)
        return meta


def reopen(root: Path, rid: str, fid: str, reason: str) -> None:
    """A redrafting item whose run never started or ended without a redraft goes back to open (FLOW-002)."""
    with store._locked(root):
        fb = load(root, rid)
        for it in fb["items"]:
            if it["id"] == fid and it["state"] == "redrafting":
                it.update(state="open", reason=reason)
                _save(root, rid, fb)


def check_edit_run(root: Path, rid: str, fid: str, before: int) -> list[int]:
    """After an edit-resume run: every version newer than `before` must be author=ai source=<fid> and pass the guard
    against its predecessor, else it is moved aside to rejected-v<n> (kept on disk, dropped from the list).
    ponytail: a UI hand edit made during the run is moved aside too; the user re-saves it."""
    import shutil

    with store._locked(root):
        meta, fb = store.get(root, rid), load(root, rid)
        it = next((i for i in fb["items"] if i["id"] == fid), None)
        allowed, bad, prev_n = _allowed(it) if it else "", [], before
        for v in [v for v in meta["versions"] if v["n"] > before]:
            if bad or v["author"] != "ai" or v["source"] != fid or guard(
                    store.version(root, rid, prev_n)["text"], store.version(root, rid, v["n"])["text"], allowed):
                bad.append(v["n"])
            else:
                prev_n = v["n"]
        if bad:
            d = store._dir(root, rid)
            for n in bad:
                dst = d / f"rejected-v{n}"
                shutil.move(str(d / f"v{n}"), str(dst if not dst.exists() else d / f"rejected-v{n}-{store._now()}"))
            meta["versions"] = [v for v in meta["versions"] if v["n"] not in bad]
            store._write(d, meta)
            if it:
                it.update(state="open", reason=f"unguarded edit v{', v'.join(map(str, bad))} rejected", applied_v=None)
                _save(root, rid, fb)
        return bad


def edit(root: Path, rid: str, text: str) -> dict[str, Any]:
    """Hand edit (REQ-097): new version author=user, previous versions unchanged, no guard."""
    return store.add_text(root, rid, text, author="user", source="edit")
