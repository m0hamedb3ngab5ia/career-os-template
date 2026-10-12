"""Résumé store (REQ-093, REQ-099, REQ-100; DEC-006, DEC-008).

profile/resumes/<rid>/meta.json  {rid, name, type, category, versions: [{n, author, source, at}]}
profile/resumes/<rid>/v<n>/      original.<ext>, text.txt, ats.json (careeros.extract)
                                  [+ resume.json, resume.pdf: snapshot of a tailored version's job files]
Exactly one résumé is `master` (the first upload; marking another demotes the old one to `variant`).
Structured résumés (`resume.json`, DEC-018) are read through `read_resume_json` / `migrate` (schema v1).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import shutil
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

MAX_BYTES = 5 * 1024 * 1024  # REQ-093 (Q-009)
MAGIC = {".pdf": b"%PDF", ".docx": b"PK"}  # DEC-006: extension + magic bytes
TYPES = ("master", "variant", "other", "tailored")
_RID = re.compile(r"[a-z0-9][a-z0-9-]*")
SCHEMA_VERSION = 1  # resume.json (templates/resume/resume_schema.md, DEC-018)
ENTRY_SECTIONS = ("experience", "projects", "leadership", "education")


class BadType(ValueError):
    """Not a PDF/DOCX (extension and magic bytes must agree) -> 415."""


class TooLarge(ValueError):
    """Over MAX_BYTES -> 413."""


class Refused(Exception):
    """A rule forbids it (deleting the master, the latest version, un-mastering) -> 409."""


class Stale(Refused):
    """A draft write carried an old `rev` (another tab saved first, DEC-014) -> 409, reload."""


def _base(root: Path) -> Path:
    return Path(root) / "profile" / "resumes"


def _dir(root: Path, rid: str) -> Path:
    d = _base(root) / rid
    if not _RID.fullmatch(rid) or not (d / "meta.json").is_file():
        raise LookupError(f"no résumé {rid!r}")
    return d


@contextmanager
def _locked(root: Path) -> Iterator[None]:
    """Serialise store mutations across threads/processes (one master, REQ-099). No-op without fcntl."""
    base = _base(root)
    base.mkdir(parents=True, exist_ok=True)
    with (base / ".lock").open("a") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)  # released on close
        yield


def _write(d: Path, meta: dict[str, Any]) -> None:
    tmp = d / f"meta.json.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(d / "meta.json")


def label(v: dict[str, Any]) -> str:
    """Plain name of a version: the upload is the Original, an AI rewrite applied review feedback, a hand edit."""
    return v.get("label") or ("Original" if v["n"] == 1 else "Edited" if v["source"] == "edit"
                              else "Feedback applied" if v["author"] == "ai" else "Uploaded")


def get(root: Path, rid: str) -> dict[str, Any]:
    meta = json.loads((_dir(root, rid) / "meta.json").read_text(encoding="utf-8"))
    for v in meta["versions"]:  # older meta.json has no labels
        v["label"] = label(v)
    return meta


def download_name(root: Path, rid: str, n: int) -> tuple[Path, str]:
    """Version n's stored file and its download name `{NN}_{Name}_{Label}.{ext}`, spaces removed."""
    meta = get(root, rid)
    v = next((v for v in meta["versions"] if v["n"] == n), None)
    files = list((_dir(root, rid) / f"v{n}").glob("original.*")) if v else []
    if not files:
        raise LookupError(f"résumé {rid!r} has no v{n}")
    stem = Path(meta["name"]).stem if Path(meta["name"]).suffix.lower() in (*MAGIC, ".txt") else meta["name"]
    def camel(t: str) -> str:
        return "".join(w[:1].upper() + w[1:] for w in t.split())
    return files[0], f"{n:02d}_{camel(stem)}_{camel(v['label'])}{files[0].suffix}"


def _all(root: Path) -> list[dict[str, Any]]:
    base = _base(root)
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("*/meta.json"))] if base.is_dir() else []


def list_resumes(root: Path) -> list[dict[str, Any]]:
    """name, type, latest version, date (REQ-100)."""
    return [{"rid": m["rid"], "name": m["name"], "type": m["type"], "category": m.get("category"),
             "latest": m["versions"][-1]["n"], "at": m["versions"][-1]["at"]} for m in _all(root)]


def _check(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in MAGIC or not data.startswith(MAGIC[ext]):
        raise BadType(f"{filename}: only PDF or DOCX résumés are accepted")
    if len(data) > MAX_BYTES:
        raise TooLarge(f"{filename}: larger than {MAX_BYTES // (1024 * 1024)} MB")
    return ext


def _store(d: Path, n: int, ext: str, data: bytes) -> None:
    from careeros.extract import ats_view

    v = d / f"v{n}"
    v.mkdir(parents=True)
    (v / f"original{ext}").write_bytes(data)
    ats = ats_view(v / f"original{ext}")
    (v / "text.txt").write_text(ats["text"] + "\n", encoding="utf-8")
    (v / "ats.json").write_text(json.dumps(ats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add(root: Path, filename: str, data: bytes, *, name: str | None = None, type: str | None = None) -> dict[str, Any]:
    """Store an uploaded résumé as v1 (author=user). Bad type/size -> nothing stored."""
    ext = _check(filename, data)
    if type is not None and type not in TYPES:
        raise ValueError(f"type must be one of {', '.join(TYPES)}")
    name = (name or Path(filename).stem).strip() or "résumé"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "resume"
    rid = f"{slug}-{secrets.token_hex(2)}"
    d = _base(root) / rid
    with _locked(root):
        d.mkdir(parents=True)
        has_master = any(m["type"] == "master" for m in _all(root))
        try:
            _store(d, 1, ext, data)
            meta = {"rid": rid, "name": name, "type": "variant" if has_master else "master", "category": None,
                    "versions": [{"n": 1, "author": "user", "source": "upload", "at": _now()}]}
            _write(d, meta)
        except BaseException:
            shutil.rmtree(d, ignore_errors=True)
            raise
        # first one is master
        return _update(root, rid, type=type) if type and has_master and type != meta["type"] else meta


def add_tailored(root: Path, text: str, *, category: str | None, source: str,
                 files: dict[str, Path] | None = None, below_threshold: bool = False) -> dict[str, Any]:
    """AI tailored/tweaked résumé text as a `tailored` résumé (DEC-008) so later jobs of the category reuse it.
    `files` (e.g. resume.json, resume.pdf) are snapshotted into the version dir, so a later reuse never reads the
    source job's (possibly re-prepared) files. A re-prepare of the same `source` job adds a version, not a résumé."""
    if not text.strip():
        raise ValueError("résumé text must not be empty")
    with _locked(root):
        old = next((m for m in _all(root) if m["type"] == "tailored" and m["versions"][0]["source"] == source), None)
        if old:
            meta = _append(root, old["rid"], ".txt", text.encode("utf-8"), "ai", source, lock=False)
            d = _dir(root, meta["rid"])
        else:
            name = f"{category or 'general'} (tailored)"
            rid = f"{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40]}-{secrets.token_hex(2)}"
            d = _base(root) / rid
            d.mkdir(parents=True)
            try:
                _store(d, 1, ".txt", text.encode("utf-8"))
                meta = {"rid": rid, "name": name, "type": "tailored", "category": category,
                        "versions": [{"n": 1, "author": "ai", "source": source, "at": _now()}]}
                _write(d, meta)
            except BaseException:
                shutil.rmtree(d, ignore_errors=True)
                raise
        for dst, src in (files or {}).items():
            if Path(src).is_file():
                shutil.copyfile(src, d / f"v{meta['versions'][-1]['n']}" / dst)
        if below_threshold:  # REQ-116: kept although it missed the match threshold
            meta["versions"][-1]["below_threshold"] = True
            _write(d, meta)
        return meta


def add_version(root: Path, rid: str, filename: str, data: bytes, *, author: str, source: str) -> dict[str, Any]:
    """New version vN+1 (author user|ai; source upload|edit|<feedback id>)."""
    return _append(root, rid, _check(filename, data), data, author, source)


def add_text(root: Path, rid: str, text: str, *, author: str, source: str, lock: bool = True) -> dict[str, Any]:
    """New version from edited/rewritten text (REQ-095 ai rewrite, REQ-097 hand edit): v<n>/original.txt.
    lock=False: the caller already holds `_locked` (flock is not re-entrant)."""
    if not text.strip():
        raise ValueError("résumé text must not be empty")
    return _append(root, rid, ".txt", text.encode("utf-8"), author, source, lock)


def _append(root: Path, rid: str, ext: str, data: bytes, author: str, source: str, lock: bool = True) -> dict[str, Any]:
    with _locked(root) if lock else nullcontext():
        d, meta = _dir(root, rid), get(root, rid)
        n = meta["versions"][-1]["n"] + 1
        _store(d, n, ext, data)
        entry = {"n": n, "author": author, "source": source, "at": _now()}
        meta["versions"].append({**entry, "label": label(entry)})
        _write(d, meta)
        return meta


def version(root: Path, rid: str, n: int) -> dict[str, Any]:
    """One version's entry plus its extracted text and ATS view."""
    d, meta = _dir(root, rid), get(root, rid)
    entry = next((v for v in meta["versions"] if v["n"] == n), None)
    if entry is None:
        raise LookupError(f"résumé {rid!r} has no v{n}")
    ats = json.loads((d / f"v{n}" / "ats.json").read_text(encoding="utf-8"))
    return {**entry, "rid": rid, "text": ats["text"], "ats": ats}


def update(root: Path, rid: str, *, name: str | None = None, type: str | None = None) -> dict[str, Any]:
    """Rename / retype. Marking master demotes the old master to variant (REQ-099)."""
    with _locked(root):
        return _update(root, rid, name=name, type=type)


def _update(root: Path, rid: str, *, name: str | None = None, type: str | None = None) -> dict[str, Any]:
    d, meta = _dir(root, rid), get(root, rid)
    if name is not None:  # validate everything before any write
        if not name.strip():
            raise ValueError("name must not be empty")
        meta["name"] = name.strip()
    if type is not None and type != meta["type"]:
        if type not in TYPES:
            raise ValueError(f"type must be one of {', '.join(TYPES)}")
        if meta["type"] == "master":
            raise Refused("this is the master résumé; mark another résumé master instead")
        if type == "master":
            for other in _all(root):
                if other["type"] == "master":
                    other["type"] = "variant"
                    _write(_base(root) / other["rid"], other)
        meta["type"] = type
    _write(d, meta)
    return meta


def delete(root: Path, rid: str) -> None:
    with _locked(root):
        d, meta = _dir(root, rid), get(root, rid)
        if meta["type"] == "master":
            raise Refused("the master résumé can't be deleted; mark another résumé master first")
        shutil.rmtree(d)


def delete_version(root: Path, rid: str, n: int) -> dict[str, Any]:
    """Only non-latest versions (REQ-100); delete the whole résumé to drop the latest."""
    with _locked(root):
        d, meta = _dir(root, rid), get(root, rid)
        if n not in [v["n"] for v in meta["versions"]]:
            raise LookupError(f"résumé {rid!r} has no v{n}")
        if n == meta["versions"][-1]["n"]:
            raise Refused(f"v{n} is the latest version" + (" of the master résumé" if meta["type"] == "master" else ""))
        meta["versions"] = [v for v in meta["versions"] if v["n"] != n]
        _write(d, meta)
        shutil.rmtree(d / f"v{n}", ignore_errors=True)
        return meta


def migrate(doc: dict[str, Any]) -> dict[str, Any]:
    """resume.json -> schema v1 in memory (DEC-018); returns a copy, never writes.

    No `schema_version` = pre-v1: each entry/bullet `id` was a profile/master.yaml id, so it moves to `source`.
    Missing ids are assigned from position (`sec-<type>`, `<section>-<n>`, `<entry id>.b<n>`), so the same file
    gets the same ids on every read; an id already in use gets a `-<k>` suffix. A repeated id keeps its first
    occurrence; later ones are reassigned the same way."""
    doc = copy.deepcopy(doc)
    version = doc.get("schema_version")
    if version is not None and not (type(version) is int and version == SCHEMA_VERSION):
        raise ValueError(f"unknown resume.json schema_version {version!r} (supported: {SCHEMA_VERSION})")
    old = version is None
    nodes: list[tuple[dict[str, Any], str]] = []  # (node, positional id), parents before their bullets
    for s in doc.get("sections") or []:
        if isinstance(s, dict):
            nodes.append((s, f"sec-{s.get('type')}"))
    for section in ENTRY_SECTIONS:
        for i, e in enumerate(doc.get(section) or [], 1):
            if not isinstance(e, dict):
                continue
            if old and e.get("id"):
                e.setdefault("source", e.pop("id"))
            nodes.append((e, f"{section}-{i}"))
            for b in e.get("bullets") or []:
                if isinstance(b, dict) and old and b.get("id"):
                    b.setdefault("source", b.pop("id"))
    used = {str(n["id"]) for n, _ in nodes if n.get("id")}
    used |= {str(b["id"]) for n, _ in nodes for b in n.get("bullets") or [] if isinstance(b, dict) and b.get("id")}

    def fresh(want: str) -> str:
        nid, k = want, 1
        while nid in used:
            k += 1
            nid = f"{want}-{k}"
        used.add(nid)
        return nid

    seen: set[str] = set()

    def assign(node: dict[str, Any], want: str) -> None:
        if not node.get("id") or str(node["id"]) in seen:
            node["id"] = fresh(want)
        seen.add(str(node["id"]))

    for n, want in nodes:
        assign(n, want)
        for j, b in enumerate(n.get("bullets") or [], 1):
            if isinstance(b, dict):
                assign(b, f"{n['id']}.b{j}")
    doc["schema_version"] = SCHEMA_VERSION
    return doc


def read_resume_json(path: Path) -> dict[str, Any]:
    """Read a resume.json (any supported schema) migrated to the current one (DEC-018)."""
    return migrate(json.loads(Path(path).read_text(encoding="utf-8")))


def bullets(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Every bullet dict of a résumé.json's entry sections."""
    return [b for sec in ENTRY_SECTIONS for e in doc.get(sec) or [] if isinstance(e, dict)
            for b in e.get("bullets") or [] if isinstance(b, dict)]


def _check_origin(doc: dict[str, Any], prev: dict[str, Any] | None, author: str) -> None:
    """DEC-018 amendment: only a user-authored write may mark a bullet `origin: "user"`; an AI write may only keep
    a mark the previous draft already carried on the same id and text under the same section entry."""
    if author not in ("user", "ai"):
        raise ValueError(f"author must be user or ai, not {author!r}")

    def placed(d: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:  # JSON key: ids/text may be any JSON
        return [(json.dumps([sec, e.get("id"), b.get("id"), b.get("text")], sort_keys=True), b) for sec in ENTRY_SECTIONS
                for e in d.get(sec) or [] if isinstance(e, dict) for b in e.get("bullets") or [] if isinstance(b, dict)]

    marked = [(k, b) for k, b in placed(doc) if "origin" in b]
    if any(b["origin"] != "user" for _, b in marked):
        raise ValueError('bullet origin may only be "user"')
    kept = {k for k, b in placed(prev or {}) if b.get("origin") == "user"}
    if author == "ai" and any(k not in kept for k, _ in marked):
        raise ValueError('an AI write may not set bullet origin "user"')


def _latest_json(root: Path, rid: str) -> dict[str, Any] | None:
    p = _dir(root, rid) / f"v{get(root, rid)['versions'][-1]['n']}" / "resume.json"
    return read_resume_json(p) if p.is_file() else None


def _hash(doc: dict[str, Any] | None) -> str | None:
    return None if doc is None else hashlib.sha256(
        json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


_NO_BASE = "résumé {!r} has no structured version to draft from"


def get_draft(root: Path, rid: str) -> dict[str, Any]:
    """`draft.json` {rev, resume} (DEC-014); no draft yet = the latest version's resume.json at rev 0.
    `draft` = hash(draft) != hash(latest), so an edit undone by hand clears it."""
    p, latest = _dir(root, rid) / "draft.json", _latest_json(root, rid)
    if p.is_file():
        d = json.loads(p.read_text(encoding="utf-8"))
        rev, doc = d["rev"], migrate(d["resume"])
    elif latest is not None:
        rev, doc = 0, latest
    else:
        raise LookupError(_NO_BASE.format(rid))
    return {"rev": rev, "resume": doc, "draft": _hash(doc) != _hash(latest)}


def put_draft(root: Path, rid: str, doc: dict[str, Any], *, rev: int, author: str) -> dict[str, Any]:
    """Autosave (DEC-014): replace the draft atomically if `rev` is current, else Stale. Returns what it wrote, in
    get_draft's shape. A corrupt draft.json is a ValueError (422); no recovery beyond a manual delete."""
    from careeros.runs.atomic import write_json

    try:
        doc = migrate(doc)
    except (TypeError, AttributeError) as e:  # odd shapes, e.g. "bullets": 5
        raise ValueError(f"malformed résumé: {e}") from None
    with _locked(root):
        p, latest = _dir(root, rid) / "draft.json", _latest_json(root, rid)
        if not p.is_file() and latest is None:
            raise LookupError(_NO_BASE.format(rid))
        prev = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"rev": 0, "resume": latest}
        cur = prev["rev"]
        if rev != cur:
            raise Stale(f"draft changed since rev {rev} (now rev {cur}); reload")
        _check_origin(doc, prev["resume"] and migrate(prev["resume"]), author)
        write_json(p, {"rev": cur + 1, "resume": doc}, ensure_ascii=False)
        return {"rev": cur + 1, "resume": doc, "draft": _hash(doc) != _hash(latest)}


def cleanup_tmp(root: Path, max_age: float = 600) -> int:
    """Remove temp files (`*.tmp`; never dirs or symlinks) a crashed write left in résumé dirs; run on UI startup. Younger than
    `max_age` seconds = maybe a write in flight from another process (CLI, runner): kept. Returns the count."""
    old = time.time() - max_age
    stale = [p for p in _base(root).glob("*/*.tmp")
             if not p.is_symlink() and p.is_file() and p.lstat().st_mtime < old]
    for p in stale:
        p.unlink(missing_ok=True)
    return len(stale)
