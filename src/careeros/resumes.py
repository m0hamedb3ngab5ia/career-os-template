"""Résumé store (REQ-093, REQ-099, REQ-100; DEC-006, DEC-008).

profile/resumes/<rid>/meta.json  {rid, name, type, category, versions: [{n, author, source, at}]}
profile/resumes/<rid>/v<n>/      original.<ext>, text.txt, ats.json (careeros.extract)
                                  [+ resume.json, resume.pdf: snapshot of a tailored version's job files]
profile/resumes/<rid>/v<n>/      resume.json, changes.jsonl  (published by `publish`, DEC-017/020: JSON only;
                                  text/ATS/.tex via `version` / `rendered`, PDF via `render_pdf` -> cache/)
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
                              else "Published" if v["source"] == "publish"
                              else "Feedback applied" if v["author"] == "ai" else "Uploaded")


def get(root: Path, rid: str) -> dict[str, Any]:
    meta = json.loads((_dir(root, rid) / "meta.json").read_text(encoding="utf-8"))
    for v in meta["versions"]:  # older meta.json has no labels
        v["label"] = label(v)
    return meta


def download_name(root: Path, rid: str, n: int) -> tuple[Path | bytes, str]:
    """Version n's file and its download name `{NN}_{Name}_{Label}.{ext}`, spaces removed. Uploaded versions:
    the stored original.*; the latest published version: its rendered PDF bytes (DEC-020); an older published
    version or no LaTeX engine: Refused."""
    meta = get(root, rid)
    v = next((v for v in meta["versions"] if v["n"] == n), None)
    files = list((_dir(root, rid) / f"v{n}").glob("original.*")) if v else []
    data: Path | bytes
    if files:
        data, ext = files[0], files[0].suffix
    elif v and v["source"] == "publish":
        if n != meta["versions"][-1]["n"]:
            raise Refused(f"v{n} is an older published version: only the latest version has a PDF; open it in the editor")
        try:
            pdf = render_pdf(root, rid, n)
        except RuntimeError as e:  # render.CompileError: LaTeX could not build this résumé
            raise Refused(f"could not build the PDF: {e}") from e
        if pdf is None:
            raise Refused("no LaTeX engine installed (`brew install tectonic`), so no PDF")
        data, ext = pdf, ".pdf"
    else:
        raise LookupError(f"résumé {rid!r} has no v{n}")
    stem = Path(meta["name"]).stem if Path(meta["name"]).suffix.lower() in (*MAGIC, ".txt") else meta["name"]
    def camel(t: str) -> str:
        return "".join(w[:1].upper() + w[1:] for w in t.split())
    return data, f"{n:02d}_{camel(stem)}_{camel(v['label'])}{ext}"


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
        _recover(d, meta)
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
    a = d / f"v{n}" / "ats.json"
    if a.is_file():
        ats = json.loads(a.read_text(encoding="utf-8"))
    else:  # published version: JSON only, text/ATS rendered on demand (DEC-020)
        import tempfile

        from careeros.extract import ats_view

        with tempfile.TemporaryDirectory() as t:
            ats = ats_view(_render_into(_published_json(root, rid, n), Path(t)) / "resume.txt")
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
        if next(v for v in meta["versions"] if v["n"] == n)["source"] == "publish":
            raise Refused(f"v{n} is a published version; published versions are kept (DEC-020)")
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


def placed_bullets(doc: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(key, bullet) per bullet; key = JSON of (section, entry id, bullet id, text), since ids/text may be any JSON."""
    return [(json.dumps([sec, e.get("id"), b.get("id"), b.get("text")], sort_keys=True), b) for sec in ENTRY_SECTIONS
            for e in doc.get(sec) or [] if isinstance(e, dict) for b in e.get("bullets") or [] if isinstance(b, dict)]


def _check_origin(doc: dict[str, Any], prev: dict[str, Any] | None, author: str) -> None:
    """DEC-018 amendment: only a user-authored write may mark a bullet `origin: "user"`; an AI write may only keep
    a mark the previous draft already carried on the same id and text under the same section entry."""
    if author not in ("user", "ai"):
        raise ValueError(f"author must be user or ai, not {author!r}")

    marked = [(k, b) for k, b in placed_bullets(doc) if "origin" in b]
    if any(b["origin"] != "user" for _, b in marked):
        raise ValueError('bullet origin may only be "user"')
    kept = {k for k, b in placed_bullets(prev or {}) if b.get("origin") == "user"}
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
    try:
        doc = migrate(doc)
    except (TypeError, AttributeError) as e:  # odd shapes, e.g. "bullets": 5
        raise ValueError(f"malformed résumé: {e}") from None
    with _locked(root):
        d, prev, latest = _draft_state(root, rid)
        if rev != prev["rev"]:
            raise Stale(f"draft changed since rev {rev} (now rev {prev['rev']}); reload")
        return _commit(d, prev, doc, latest, author)


def _draft_state(root: Path, rid: str) -> tuple[Path, dict[str, Any], dict[str, Any] | None]:
    p, latest = _dir(root, rid) / "draft.json", _latest_json(root, rid)
    if not p.is_file() and latest is None:
        raise LookupError(_NO_BASE.format(rid))
    prev = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"rev": 0, "resume": latest}
    return p.parent, prev, latest


def _commit(d: Path, prev: dict[str, Any], doc: dict[str, Any], latest: dict[str, Any] | None, author: str,
            reverts: str | None = None) -> dict[str, Any]:
    """Under `_locked`: write draft.json, then append its changes to draft.changes.jsonl (DEC-015). A crash between
    the two loses log lines, never invents them, so DEC-020 provenance fails closed."""
    from careeros.runs.atomic import write_json

    old = prev["resume"] and migrate(prev["resume"])
    _check_origin(doc, old, author)
    rev = prev["rev"] + 1
    write_json(d / "draft.json", {"rev": rev, "resume": doc}, ensure_ascii=False)
    lines = [{"id": f"{rev}.{k}", "at": _now(), "author": author, **c, **({"reverts": reverts} if reverts else {})}
             for k, c in enumerate(_diff(old or {}, doc), 1)]
    if lines:
        log = d / "draft.changes.jsonl"
        torn = log.is_file() and log.stat().st_size and _last_byte(log) != b"\n"
        with open(log, "a", encoding="utf-8") as f:
            f.write("\n" if torn else "")  # a crash-truncated last line stays its own (skipped) line
            f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in lines)
            f.flush()
            os.fsync(f.fileno())
    return {"rev": rev, "resume": doc, "draft": _hash(doc) != _hash(latest)}


def _flat(doc: dict[str, Any]) -> dict[tuple[str, str], tuple[Any, dict[str, Any] | None]]:
    """(kind, target_id) -> (value, where): a bullet, an entry without its bullets, or any other top-level field.
    Order-only moves are not changes."""
    out: dict[tuple[str, str], tuple[Any, dict[str, Any] | None]] = {}
    for k, v in doc.items():
        if k not in ENTRY_SECTIONS or not isinstance(v, list):
            out[("field", k)] = (v, None)
    for sec in ENTRY_SECTIONS:
        entries = doc.get(sec)
        for i, e in enumerate(entries if isinstance(entries, list) else []):
            if not isinstance(e, dict):
                continue
            out[("entry", str(e["id"]))] = ({k: v for k, v in e.items() if k != "bullets"}, {"section": sec, "index": i})
            for j, b in enumerate(e.get("bullets") or []):
                if isinstance(b, dict):
                    out[("bullet", str(b["id"]))] = (b, {"section": sec, "entry": str(e["id"]), "index": j})
    return out


def _diff(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    a, b = _flat(old), _flat(new)
    out = []
    for key in [*a, *(k for k in b if k not in a)]:
        before, after = a.get(key, (None, None)), b.get(key, (None, None))
        if before[0] != after[0]:
            op = "add" if key not in a else "delete" if key not in b else "edit"
            out.append({"kind": key[0], "target_id": key[1], "op": op, "before": before[0], "after": after[0],
                        "where": after[1] or before[1]})
    return out


def _put_node(doc: dict[str, Any], kind: str, tid: str, value: Any, where: dict[str, Any] | None) -> None:
    """Make target `tid` hold `value` (None = remove): in place if present, else inserted at `where`."""
    if kind == "field":
        doc.pop(tid, None) if value is None else doc.__setitem__(tid, value)
        return
    for sec in ENTRY_SECTIONS:
        entries = doc.get(sec)
        for e in entries if isinstance(entries, list) else []:
            if not isinstance(e, dict):
                continue
            if kind == "entry" and str(e.get("id")) == tid:
                if value is None:
                    entries.remove(e)
                else:
                    kept = e.get("bullets")
                    e.clear()
                    e.update(value, **({"bullets": kept} if kept is not None else {}))
                return
            bl = e.get("bullets") if kind == "bullet" else None
            for i, b in enumerate(bl or []):
                if isinstance(b, dict) and str(b.get("id")) == tid:
                    bl.pop(i) if value is None else bl.__setitem__(i, value)
                    return
    if value is None:
        return
    entries = doc.setdefault(where["section"], [])
    if kind == "entry":
        entries.insert(where["index"], {**value, "bullets": []})
        return
    e = next((e for e in entries if isinstance(e, dict) and str(e.get("id")) == where["entry"]), None)
    if e is None:
        raise Refused(f"entry {where['entry']!r} no longer exists; revert its removal first")
    e.setdefault("bullets", []).insert(where["index"], value)


class Conflict(Refused):
    """Revert refused: the target no longer holds the change's `after` (DEC-015) -> 409 with both texts."""

    def __init__(self, msg: str, expected: Any, current: Any) -> None:
        super().__init__(msg)
        self.expected, self.current = expected, current


def _text(v: Any) -> Any:
    return v.get("text", v) if isinstance(v, dict) else v


def _last_byte(p: Path) -> bytes:
    with open(p, "rb") as f:
        f.seek(-1, 2)
        return f.read(1)


def _read_log(p: Path) -> list[dict[str, Any]]:
    """Parsed log lines; an unparsable (e.g. crash-truncated) line is skipped, which only loses provenance (fails closed)."""
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines() if p.is_file() else []:
        try:
            c = json.loads(line)
        except ValueError:
            continue
        if isinstance(c, dict):
            out.append(c)
    return out


def changes(root: Path, rid: str) -> list[dict[str, Any]]:
    """The draft's change log, oldest first (History, DEC-015)."""
    return _read_log(_dir(root, rid) / "draft.changes.jsonl")


def revert_change(root: Path, rid: str, cid: str) -> dict[str, Any]:
    """History Revert (DEC-015): a new user change putting `before` back, only while the target still holds the
    change's `after`; else Conflict. Returns get_draft's shape."""
    with _locked(root):
        d, prev, latest = _draft_state(root, rid)
        c = next((c for c in reversed(_read_log(d / "draft.changes.jsonl")) if c.get("id") == cid), None)
        if c is None:
            raise LookupError(f"no change {cid!r}")
        doc = migrate(prev["resume"])
        now = _flat(doc).get((c["kind"], c["target_id"]), (None, None))[0]
        if now != c["after"]:
            raise Conflict(f"{c['target_id']!r} changed since: expected {_text(c['after'])!r}, now {_text(now)!r}",
                           _text(c["after"]), _text(now))
        _put_node(doc, c["kind"], c["target_id"], copy.deepcopy(c["before"]), c.get("where"))
        return _commit(d, prev, migrate(doc), latest, "user", reverts=cid)


def user_texts(root: Path, rid: str) -> set[str]:
    """DEC-020: bullet texts a user wrote, replaying the logs (published versions' changes.jsonl, then the draft's).
    Per bullet, the current text's author is the last line that changed the text (an add, or before.text !=
    after.text); a line leaving the text as is keeps the previous author; a revert line inherits whoever wrote the
    text it restores, not its actor. Only user-authored texts make `origin: "user"` count."""
    try:
        d = _dir(root, rid)
    except LookupError:
        return set()
    logs = sorted(d.glob("v*/changes.jsonl"), key=lambda p: int(p.parent.name[1:]) if p.parent.name[1:].isdigit() else 0)
    cur: dict[str, tuple[Any, str | None]] = {}  # bullet id -> (text, its author)
    for p in [*logs, d / "draft.changes.jsonl"]:
        prior: dict[str, str | None] = {}  # line id -> author of the text it replaced (newest line per id wins)
        for c in _read_log(p):
            if c.get("kind") != "bullet":
                continue
            bid = str(c.get("target_id"))
            was = cur.get(bid, (None, None))
            prior[str(c.get("id"))] = was[1]
            text = _text(c.get("after"))
            if c.get("reverts") is not None:
                who = prior.get(str(c["reverts"]))
            elif c.get("op") == "add" or _text(c.get("before")) != text:
                who = c.get("author")
            else:
                who = was[1]
            cur[bid] = (text, who)
    return {t for t, who in cur.values() if who == "user" and isinstance(t, str)}


MARK = ".publish.json"  # in .v<n>.tmp: the draft log's byte length at publish + the key (crash recovery)


def _move_log(d: Path, v: Path, offset: int) -> None:
    """Move the draft log's first `offset` bytes (the published changes) to v/changes.jsonl; later lines (edits
    made after a crash) stay in the draft log."""
    log = d / "draft.changes.jsonl"
    if offset and log.exists():
        data = log.read_bytes()
        tmp = v / "changes.jsonl.tmp"
        tmp.write_bytes(data[:offset])
        tmp.replace(v / "changes.jsonl")
        if data[offset:]:
            rest = d / f"draft.changes.jsonl.{os.getpid()}.tmp"
            rest.write_bytes(data[offset:])
            rest.replace(log)
        else:
            log.unlink()


def _recover(d: Path, meta: dict[str, Any]) -> None:
    """Under `_locked`, before any new version: v<n+1> exists but meta.json (the commit point) doesn't list it.
    A publish (resume.json, renamed in whole) is rolled forward (DEC-017): its log moved, it gets listed with its
    key. Anything else is an upload that never committed: discarded."""
    (d / f"v{meta['versions'][-1]['n']}" / MARK).unlink(missing_ok=True)  # crash after the commit
    n = meta["versions"][-1]["n"] + 1
    v = d / f"v{n}"
    if not v.is_dir():
        return
    if not (v / "resume.json").is_file():
        shutil.rmtree(v)
        return
    mark = json.loads((v / MARK).read_text(encoding="utf-8")) if (v / MARK).is_file() else {"offset": 0}
    if not (v / "changes.jsonl").exists():
        _move_log(d, v, mark["offset"])
    entry = {"n": n, "author": "user", "source": "publish", "at": _now(), **({"key": mark["key"]} if "key" in mark else {})}
    meta["versions"].append({**entry, "label": label(entry)})
    _write(d, meta)
    (v / MARK).unlink(missing_ok=True)


def publish(root: Path, rid: str, *, key: str, master: bool = False, source: str = "publish",
            rev: int | None = None) -> dict[str, Any]:
    """Next/Done (DEC-017, DEC-020): the draft becomes v<n+1> = resume.json + changes.jsonl only. Steps: write
    `.v<n+1>.tmp/resume.json`, rename to v<n+1>, move draft.changes.jsonl in, write meta.json (the commit point),
    restart the draft from it (rev kept monotonic so change ids stay unique). Unchanged hash or an already-seen
    `key` = no new version. A crash after the rename is rolled forward on the next call. `master` sets the
    résumé master (onboarding); `source` = import for the import guard (DEC-019); `rev` refuses a draft that moved
    past that rev. Returns meta + {published, n}."""
    from careeros.runs.atomic import write_json

    if not key.strip():
        raise ValueError("publish needs an idempotency key")
    with _locked(root):
        d, meta = _dir(root, rid), get(root, rid)
        _recover(d, meta)
        seen = next((v for v in meta["versions"] if v.get("key") == key), None)
        published = seen is not None  # a retry with the same key gets the same answer (NIT: idempotent)
        if seen is None:
            _, prev, latest = _draft_state(root, rid)
            if rev is not None and prev["rev"] != rev:
                raise Refused(f"the draft changed after rev {rev}; not published")
            doc = migrate(prev["resume"])
            if _hash(doc) != _hash(latest):
                n = meta["versions"][-1]["n"] + 1
                tmp = d / f".v{n}.tmp"
                shutil.rmtree(tmp, ignore_errors=True)  # left by a crash before the rename
                tmp.mkdir()
                write_json(tmp / "resume.json", doc, ensure_ascii=False)
                log = d / "draft.changes.jsonl"
                write_json(tmp / MARK, {"offset": log.stat().st_size if log.exists() else 0, "key": key})
                tmp.rename(d / f"v{n}")
                _move_log(d, d / f"v{n}", json.loads((d / f"v{n}" / MARK).read_text(encoding="utf-8"))["offset"])
                entry = {"n": n, "author": "user", "source": source, "at": _now(), "key": key}
                meta["versions"].append({**entry, "label": label(entry)})
                _write(d, meta)
                (d / f"v{n}" / MARK).unlink()
                write_json(d / "draft.json", {"rev": prev["rev"] + 1, "resume": doc}, ensure_ascii=False)
                published = True
        if master and meta["type"] != "master":
            meta = _update(root, rid, type="master")
        return {**get(root, rid), "published": published, "n": seen["n"] if seen else meta["versions"][-1]["n"]}


def _renderer() -> Any:
    """templates/resume/render.py as a module (one renderer, DEC-018)."""
    import importlib.util
    import sys

    mod = sys.modules.get("careeros_resume_render")
    if mod is None:
        path = Path(__file__).resolve().parents[2] / "templates" / "resume" / "render.py"
        spec = importlib.util.spec_from_file_location("careeros_resume_render", path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        sys.modules["careeros_resume_render"] = mod
    return mod


def renderer_version() -> str:
    """Hash of render.py + its templates: part of the PDF cache key (DEC-020)."""
    here = Path(_renderer().__file__).parent
    h = hashlib.sha256()
    for p in sorted([here / "render.py", *here.glob("*.tex")]):
        h.update(p.name.encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:12]


def _render_into(src: Path, out: Path, *, pdf: bool = False) -> Path:
    """Copy a version's resume.json into `out` and render resume.txt + resume.tex (+ PDF) there."""
    import io
    from contextlib import redirect_stdout

    shutil.copyfile(src, out / "resume.json")
    mod = _renderer()
    with redirect_stdout(io.StringIO()):
        mod.render_txt(out / "resume.json")
        mod.render(out / "resume.json", pdf=pdf)
    return out


def _published_json(root: Path, rid: str, n: int) -> Path:
    p = _dir(root, rid) / f"v{n}" / "resume.json"
    if not p.is_file():
        raise LookupError(f"résumé {rid!r} v{n} has no resume.json")
    return p


def rendered(root: Path, rid: str, n: int, kind: str) -> str:
    """The one store helper for derived outputs of a JSON-only version (DEC-020): `txt` or `tex`, rendered on
    demand into a temp dir; same resume.json -> identical output."""
    import tempfile

    if kind not in ("txt", "tex"):
        raise ValueError("kind must be txt or tex")
    src = _published_json(root, rid, n)
    with tempfile.TemporaryDirectory() as t:
        return (_render_into(src, Path(t)) / f"resume.{kind}").read_text(encoding="utf-8")


def render_pdf(root: Path, rid: str, n: int) -> bytes | None:
    """Latest version's PDF bytes, cached as cache/<hash(resume.json)>-<renderer_version>.pdf (DEC-020; older
    entries removed, disposable). Bytes, not a path: a concurrent eviction can't pull a file from under a caller.
    None = no LaTeX engine. Older versions have no PDF: LookupError."""
    import tempfile

    if n != get(root, rid)["versions"][-1]["n"]:
        raise LookupError(f"only the latest version of {rid!r} has a PDF")
    src = _published_json(root, rid, n)
    cache = _dir(root, rid) / "cache"
    want = cache / f"{_hash(read_resume_json(src))}-{renderer_version()}.pdf"
    try:
        return want.read_bytes()
    except FileNotFoundError:
        pass
    with tempfile.TemporaryDirectory() as t:
        pdf = _render_into(src, Path(t), pdf=True) / "resume.pdf"
        if not pdf.is_file():
            return None
        data = pdf.read_bytes()
    cache.mkdir(exist_ok=True)
    for old in cache.glob("*.pdf"):
        old.unlink(missing_ok=True)
    tmp = cache / f"{want.name}.{os.getpid()}.tmp"
    tmp.write_bytes(data)
    tmp.replace(want)
    return data


def cleanup_tmp(root: Path, max_age: float = 600) -> int:
    """Remove temp files (`*.tmp`; never dirs or symlinks) a crashed write left in résumé dirs; run on UI startup. Younger than
    `max_age` seconds = maybe a write in flight from another process (CLI, runner): kept. Returns the count."""
    old = time.time() - max_age
    stale = [p for p in _base(root).glob("*/*.tmp")
             if not p.is_symlink() and p.is_file() and p.lstat().st_mtime < old]
    for p in stale:
        p.unlink(missing_ok=True)
    return len(stale)
