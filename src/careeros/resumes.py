"""Résumé store (REQ-093, REQ-099, REQ-100; DEC-006, DEC-008).

profile/resumes/<rid>/meta.json  {rid, name, type, category, versions: [{n, author, source, at}]}
profile/resumes/<rid>/v<n>/      original.<ext>, text.txt, ats.json (careeros.extract)
                                  [+ resume.json, resume.pdf: snapshot of a tailored version's job files]
Exactly one résumé is `master` (the first upload; marking another demotes the old one to `variant`).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
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


class BadType(ValueError):
    """Not a PDF/DOCX (extension and magic bytes must agree) -> 415."""


class TooLarge(ValueError):
    """Over MAX_BYTES -> 413."""


class Refused(Exception):
    """A rule forbids it (deleting the master, the latest version, un-mastering) -> 409."""


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


def get(root: Path, rid: str) -> dict[str, Any]:
    return json.loads((_dir(root, rid) / "meta.json").read_text(encoding="utf-8"))


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
        meta["versions"].append({"n": n, "author": author, "source": source, "at": _now()})
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
