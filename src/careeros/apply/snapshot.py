"""As-submitted snapshots: a frozen copy of exactly what went out for a job.

Regenerating a résumé, cover letter or answers overwrites the files in `data/jobs/<id>/`. A snapshot keeps
the versions that were submitted, plus the values typed into the form, so an interview weeks later can be
prepared from what the company actually read.

    from careeros.apply.snapshot import freeze, latest
    freeze(job_dir, session=s)          # apply-job, right after finish("submitted")
    freeze(job_dir, reason="manual")    # you submitted by hand
    latest(job_dir)                     # newest manifest (dict) or None

Layout: `data/jobs/<id>/submitted/<UTC stamp>/` holding copies of the documents that exist plus
`manifest.json` {job_id, frozen_at, reason, resume_version, confirmation_text, files[{name, sha256, bytes}],
answers_entered[{label, value, source}]}. Snapshots are never overwritten (a same-second freeze gets `-2`)
and their files are made read-only.

`Store.set_status(..., "applied")` freezes automatically when a job has no snapshot yet, so every applied
job has one however it was submitted.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from careeros.apply.session import SESSION_FILE, ApplySession

SNAPSHOT_DIR = "submitted"
MANIFEST = "manifest.json"
REASONS: tuple[str, ...] = ("submitted", "assisted_stop", "manual")

# What went out, and what explains it later. Missing files are skipped.
FROZEN_FILES: tuple[str, ...] = (
    "resume.pdf", "resume.txt", "resume.json", "resume.tex",
    "cover_letter.pdf", "cover_letter.txt", "cover_letter.md",
    "answers.json", "posting.json", "score.json", SESSION_FILE,
)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _is_finder_copy(name: str) -> bool:
    from careeros.store import _is_finder_copy as f

    return f(name)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_answers(answers: list[Mapping[str, Any]] | Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not answers:
        return []
    if isinstance(answers, Mapping):
        return [{"label": str(k), "value": v, "source": None} for k, v in answers.items()]
    out = []
    for a in answers:
        if not isinstance(a, Mapping) or "label" not in a:
            raise ValueError("each entered answer needs a 'label'")
        out.append({"label": str(a["label"]), "value": a.get("value"), "source": a.get("source")})
    return out


def _resume_version(jd: Path) -> str | None:
    p = jd / "resume.json"
    if not p.exists():
        return None
    try:
        return (json.loads(p.read_text(encoding="utf-8")).get("meta") or {}).get("resume_version")
    except (json.JSONDecodeError, AttributeError):
        return None


def _new_dir(root: Path) -> Path:
    base = _stamp()
    root.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        d = root / (base if n == 1 else f"{base}-{n}")
        try:
            d.mkdir()
            return d
        except FileExistsError:
            n += 1


def freeze(job_dir: str | Path, *, reason: str | None = None,
           answers_entered: list[Mapping[str, Any]] | Mapping[str, Any] | None = None,
           session: ApplySession | None = None) -> Path:
    """Copy the job's current documents into a new `submitted/<stamp>/` and return that directory.

    `session` (or the saved `apply_session.json`) supplies the entered form values, résumé version and,
    when `reason` is not given, the reason: `submitted` if the applier clicked submit, `assisted_stop` if
    it filled the form and stopped for you, else `manual`.
    """
    jd = Path(job_dir)
    if reason is not None and reason not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}, got {reason!r}")
    sess = session or ApplySession.load(jd)
    if reason is None:
        reason = "manual" if sess is None else ("submitted" if sess.submit_clicked else "assisted_stop")
    entered = _normalize_answers(answers_entered) if answers_entered is not None else (
        _normalize_answers(sess.entered) if sess else [])

    out = _new_dir(jd / SNAPSHOT_DIR)
    if session is not None:  # the in-memory session may be newer than the file on disk
        (out / SESSION_FILE).write_text(json.dumps(session.to_dict(), indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    files = []
    for name in FROZEN_FILES:
        src = jd / name
        dst = out / name
        if not dst.exists():
            if not src.is_file() or _is_finder_copy(name):
                continue
            shutil.copy2(src, dst)
        files.append({"name": name, "sha256": _sha256(dst), "bytes": dst.stat().st_size})

    posting = {}
    if (jd / "posting.json").exists():
        try:
            posting = json.loads((jd / "posting.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            posting = {}
    manifest = {
        "job_id": posting.get("job_id") or jd.name,
        "frozen_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "reason": reason,
        "resume_version": (sess.resume_version if sess and sess.resume_version else None) or _resume_version(jd),
        "confirmation_text": sess.confirmation_text if sess else None,
        "files": files,
        "answers_entered": entered,
    }
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    ro = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    for p in out.iterdir():
        try:
            os.chmod(p, ro)
        except OSError:  # best effort (e.g. filesystems without POSIX modes)
            pass
    return out


def snapshots(job_dir: str | Path) -> list[Path]:
    """Snapshot directories, oldest first (Finder duplicates ignored)."""
    root = Path(job_dir) / SNAPSHOT_DIR
    if not root.is_dir():
        return []
    dirs = [d for d in root.iterdir() if d.is_dir() and not _is_finder_copy(d.name) and (d / MANIFEST).exists()]
    return sorted(dirs, key=lambda d: (d.name.split("-")[0], int(d.name.split("-")[1]) if "-" in d.name else 1))


def latest(job_dir: str | Path) -> dict[str, Any] | None:
    """Newest snapshot's manifest plus `dir`, or None when the job has none."""
    snaps = snapshots(job_dir)
    if not snaps:
        return None
    m = json.loads((snaps[-1] / MANIFEST).read_text(encoding="utf-8"))
    m["dir"] = str(snaps[-1])
    return m
