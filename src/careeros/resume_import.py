"""Import guard (DEC-019, TASK-032): extract-master's structured résumé becomes v2 only if every bullet and field
appears (whitespace-normalised) in v1 `text.txt`. The guard is the only path that marks uploaded bullets
`origin: "user"` (DEC-018 amendment): their text is the candidate's own upload.

profile/resumes/<rid>/import.json  {state: running|done|failed, run, reason, at, n, dropped: [{id, text, restored}]}
"""
from __future__ import annotations

import copy
import json
import re
import secrets
from pathlib import Path
from typing import Any

from careeros import resumes as store

_TOP = {"schema_version", "sections"}  # layout, not résumé content
_ITEM = {"id", "source", "origin"}  # ids/provenance on entries and bullets
_GLYPHS = "•·*- "
_HEAD = {"work", "professional", "experience", "employment", "history", "education", "skills", "technical",
         "projects", "summary", "profile", "certifications", "languages", "awards", "publications", "volunteer",
         "volunteering", "and", "key", "core", "competencies", "career", "objective", "references"}


class ImportRefused(ValueError):
    pass


def _path(root: Path, rid: str) -> Path:
    return store._dir(root, rid) / "import.json"


def load(root: Path, rid: str) -> dict[str, Any]:
    """A `running` import whose step process is gone (crashed) reads as failed, so Retry is offered."""
    from careeros.runs.locks import pid_alive

    p = _path(root, rid)
    st = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"state": None, "dropped": []}
    if st.get("state") == "running" and isinstance(st.get("pid"), int) and not pid_alive(st["pid"]):
        st = {**st, "state": "failed", "reason": "import run stopped without a guarded résumé"}
    return st


def set_state(root: Path, rid: str, state: str, **fields: Any) -> dict[str, Any]:
    """`running` starts afresh; other states merge into the current record (keeps n/dropped)."""
    from careeros.runs.atomic import write_json

    st = {"dropped": []} if state == "running" else load(root, rid)
    st.update({"state": state, "at": store._now()}, **{k: v for k, v in fields.items() if v is not None})
    write_json(_path(root, rid), st, ensure_ascii=False)
    return st


def _norm(s: str) -> str:
    from careeros.qa_ext.pdf_fidelity import normalize_text

    return " ".join(normalize_text(s).split())


def _key(s: str) -> str:
    return _norm(s).casefold()  # "verbatim" = whitespace-normalised, case-insensitive (DEC-019)


def _leaves(node: Any, at: str = "", skip: frozenset[str] | set[str] = _TOP) -> list[tuple[str, str]]:
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        node = str(node)
    if isinstance(node, str):
        return [(at, node)] if node.strip() else []
    if isinstance(node, dict):
        return [x for k, v in node.items() if k not in skip for x in _leaves(v, f"{at}.{k}" if at else k, set())]
    if isinstance(node, list):
        return [x for i, v in enumerate(node) for x in _leaves(v, f"{at}[{i}]", _ITEM)]
    return []


def _has(hay: str, needle: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", hay) is not None


def _header(line: str, doc: dict[str, Any]) -> bool:
    words = re.findall(r"\w+", line)
    return 0 < len(words) <= 4 and set(words) <= _HEAD | {k.casefold() for k in doc}


def _lines(text: str) -> list[tuple[str, bool]]:
    """Normalised v1 lines without their bullet glyph, and whether they had one."""
    return [(k.lstrip(_GLYPHS), k[0] in _GLYPHS.strip()) for k in map(_key, text.splitlines()) if k]


def _guard(doc: dict[str, Any], text: str) -> None:
    """A bullet = whole consecutive v1 lines (a wrapped bullet; never across a new bullet or a header); any other
    field = word-bounded inside one v1 line."""
    lines = _lines(text)
    spans = {" ".join(x for x, _ in lines[i:j]) for i in range(len(lines)) for j in range(i + 1, min(i + 6, len(lines) + 1))
             if not any(g or _header(x, doc) for x, g in lines[i + 1:j])}
    for at, s in _leaves(doc):
        k = _key(s)
        if not (k in spans if re.search(r"\.bullets\[\d+\](\.text)?$", at) else any(_has(x, k) for x, _ in lines)):
            raise ImportRefused(f"{at} not in the uploaded text: {s!r}")


def _dropped(doc: dict[str, Any], text: str) -> list[dict[str, Any]]:
    """Whole v1 lines the structured résumé doesn't carry ("Not carried over", E2E-001-04); headers skipped."""
    leaves = [_key(s) for _, s in _leaves(doc)]
    out = []
    for line in text.splitlines():
        k = _key(line).lstrip(_GLYPHS)
        if not k or _header(k, doc) or any(_has(x, k) for x in leaves):
            continue
        for x in leaves:
            k = re.sub(rf"(?<!\w){re.escape(x)}(?!\w)", " ", k)
        if re.search(r"\w", k):
            out.append({"id": f"d{len(out) + 1}", "text": " ".join(line.split()).lstrip(_GLYPHS), "restored": False})
    return out


def save(root: Path, rid: str, doc: dict[str, Any]) -> dict[str, Any]:
    """The import run's result: guard, then publish v<n+1> (author user, source import). Refused -> import.json
    failed with the reason, nothing published (v1 kept). Only a running import of a user upload may save, so AI
    text is never marked user and a stray call can't clobber later versions."""
    v1 = store.get(root, rid)["versions"][0]
    if (v1.get("author"), v1.get("source")) != ("user", "upload"):
        raise ImportRefused(f"résumé {rid!r} v1 is not a user upload; only an upload is imported")
    if load(root, rid).get("state") != "running":
        raise ImportRefused(f"no import run is running for {rid!r}; Retry starts one")
    text = (store._dir(root, rid) / "v1" / "text.txt").read_text(encoding="utf-8")
    try:
        doc = store.migrate(doc)
        _guard(doc, text)
    except (ValueError, TypeError, AttributeError) as e:
        set_state(root, rid, "failed", reason=str(e)[:500])
        raise ImportRefused(str(e)) from None
    for _, b in store.placed_bullets(doc):
        b["origin"] = "user"  # verbatim in the candidate's upload (DEC-018 amendment); any AI mark is overwritten
    with store._locked(root):
        d = store._dir(root, rid)
        p = d / "draft.json"
        prev = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"rev": 0, "resume": None}
        rev = store._commit(d, prev, doc, store._latest_json(root, rid), "user")["rev"]
    try:  # rev: a user edit landing between the commit and the publish is not published as the import
        out = store.publish(root, rid, key=f"import-{secrets.token_hex(4)}", source="import", rev=rev)
    except store.Refused as e:
        set_state(root, rid, "failed", reason=str(e)[:500])
        raise ImportRefused(str(e)) from None
    return set_state(root, rid, "done", reason="", n=out["n"], dropped=_dropped(doc, text))


def restore(root: Path, rid: str, did: str, entry: str | None = None) -> dict[str, Any]:
    """Restore a "Not carried over" line: a user bullet appended to `entry` (default: the first entry) in the draft."""
    from careeros.runs.atomic import write_json

    with store._locked(root):
        st = load(root, rid)
        item = next((x for x in st["dropped"] if x["id"] == did), None)
        if item is None:
            raise LookupError(f"résumé {rid!r} has no dropped line {did!r}")
        if item["restored"]:
            raise store.Refused(f"{did} is already restored")
        d, prev, latest = store._draft_state(root, rid)
        doc = store.migrate(copy.deepcopy(prev["resume"]))
        target = next((e for sec in store.ENTRY_SECTIONS for e in doc.get(sec) or []
                       if isinstance(e, dict) and (entry is None or e.get("id") == entry)), None)
        if target is None:
            raise store.Refused(f"no entry {entry!r} to restore into" if entry else "no entry to restore into")
        bullets = target.setdefault("bullets", [])
        if not any(isinstance(b, dict) and b.get("text") == item["text"] for b in bullets):  # crash before import.json
            bullets.append({"text": item["text"], "origin": "user"})
        out = store._commit(d, prev, store.migrate(doc), latest, "user")
        item["restored"] = True
        write_json(_path(root, rid), st, ensure_ascii=False)
        return out
