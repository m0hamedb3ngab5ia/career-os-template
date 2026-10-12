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

_SKIP = {"id", "source", "origin", "schema_version", "sections"}  # ids/provenance/layout, not résumé content


class ImportRefused(ValueError):
    pass


def _path(root: Path, rid: str) -> Path:
    return store._dir(root, rid) / "import.json"


def load(root: Path, rid: str) -> dict[str, Any]:
    p = _path(root, rid)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"state": None, "dropped": []}


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


def _leaves(node: Any, at: str = "") -> list[tuple[str, str]]:
    if isinstance(node, str):
        return [(at, node)] if node.strip() else []
    if isinstance(node, dict):
        return [x for k, v in node.items() if k not in _SKIP for x in _leaves(v, f"{at}.{k}" if at else k)]
    if isinstance(node, list):
        return [x for i, v in enumerate(node) for x in _leaves(v, f"{at}[{i}]")]
    return []


def _guard(doc: dict[str, Any], text: str) -> None:
    src = _norm(text)
    for at, s in _leaves(doc):
        if _norm(s) not in src:
            raise ImportRefused(f"{at} not in the uploaded text: {s!r}")


def _dropped(doc: dict[str, Any], text: str) -> list[dict[str, Any]]:
    """v1 lines with a word the structured résumé lacks ("Not carried over", E2E-001-04)."""
    words = set(re.findall(r"\w+", _norm(" ".join([*(s for _, s in _leaves(doc)), *doc]))))
    out = []
    for line in text.splitlines():
        if set(re.findall(r"\w+", _norm(line))) - words:
            out.append({"id": f"d{len(out) + 1}", "text": " ".join(line.split()).lstrip("•·*- "), "restored": False})
    return out


def save(root: Path, rid: str, doc: dict[str, Any]) -> dict[str, Any]:
    """The import run's result: guard, then publish v<n+1> (author user, source import). Refused -> import.json
    failed with the reason, nothing published (v1 kept)."""
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
        store._commit(d, prev, doc, store._latest_json(root, rid), "user")
    out = store.publish(root, rid, key=f"import-{secrets.token_hex(4)}", source="import")
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
        target.setdefault("bullets", []).append({"text": item["text"], "origin": "user"})
        out = store._commit(d, prev, store.migrate(doc), latest, "user")
        item["restored"] = True
        write_json(_path(root, rid), st, ensure_ascii=False)
        return out
