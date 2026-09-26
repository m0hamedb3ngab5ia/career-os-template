"""How much space career-os uses, by category, and a history of it (`data/runs/storage.jsonl`, one JSON line per
snapshot). A snapshot is appended after every prune (`careeros prune --yes`, the weekly scheduled prune) and on
demand (`careeros storage --snapshot`); the advisor reads the history.

Categories: postings (posting.json), resumes_pdfs (résumés, cover letters, any PDF / .tex, incl. submitted/
copies), screenshots (apply screenshots), run_logs (run.log, raw stream-json, launchd logs), tracker (the
workbook and its pending queue, wherever paths.tracker_xlsx points), other (everything else under data/).
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from careeros.runs.store import RunStore, iso

CATEGORIES = ("postings", "resumes_pdfs", "screenshots", "run_logs", "tracker", "other")
SNAPSHOTS = "storage.jsonl"
_DOC_PREFIXES = ("resume.", "cover_letter.")
_DOC_SUFFIXES = (".pdf", ".tex")


def _category(path: Path, jobs_dir: Path, runs_dir: Path) -> str:
    name = path.name
    try:
        rel = path.relative_to(jobs_dir)
    except ValueError:
        rel = None
    if rel is not None:
        if "screenshots" in rel.parts[:-1]:
            return "screenshots"
        if name == "posting.json":
            return "postings"
        if name.startswith(_DOC_PREFIXES) or name.endswith(_DOC_SUFFIXES):
            return "resumes_pdfs"
        return "other"
    try:
        path.relative_to(runs_dir)
        if name == "run.log" or name.endswith(".stream.jsonl") or (name.startswith("launchd.") and name.endswith(".log")):
            return "run_logs"
    except ValueError:
        pass
    return "other"


def _disk(path: Path) -> tuple[int, int]:
    u = shutil.disk_usage(path)
    return u.total, u.free


def measure(settings: Any, disk: Callable[[Path], tuple[int, int]] = _disk) -> dict[str, Any]:
    jobs_dir = Path(settings.paths["jobs_dir"])
    data_dir = jobs_dir.parent
    runs_dir = RunStore(settings).dir
    tracker = Path(settings.paths["tracker_xlsx"])
    tracker_files = {tracker, tracker.with_name(tracker.name + ".pending.json")}
    out = {c: 0 for c in CATEGORIES}
    for f in tracker_files:
        if f.is_file():
            out["tracker"] += f.stat().st_size
    roots = [data_dir] + ([runs_dir] if not str(runs_dir).startswith(str(data_dir) + os.sep) else [])
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, _, files in os.walk(root):
            for name in files:
                f = Path(dirpath) / name
                if f in tracker_files or f.is_symlink():
                    continue
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                out[_category(f, jobs_dir, runs_dir)] += size
    probe = data_dir if data_dir.exists() else Path(settings.root)
    total, free = disk(probe)
    return {"bytes": out, "total": sum(out.values()),
            "disk": {"total": total, "free": free, "free_pct": round(free / total * 100, 1) if total else 0.0}}


def append_snapshot(rs: RunStore, m: dict[str, Any], trigger: str, now: datetime | None = None,
                    pruned_bytes: int | None = None) -> dict[str, Any]:
    line = {"at": iso(now or datetime.now(timezone.utc)), "trigger": trigger, "pruned_bytes": pruned_bytes, **m}
    rs.dir.mkdir(parents=True, exist_ok=True)
    with (rs.dir / SNAPSHOTS).open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
    return line


def load_snapshots(rs: RunStore) -> list[dict[str, Any]]:
    p = rs.dir / SNAPSHOTS
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and "total" in d:
            out.append(d)
    return sorted(out, key=lambda d: d.get("at") or "")


def snapshot_after_prune(settings: Any, freed: int) -> dict[str, Any]:
    return append_snapshot(RunStore(settings), measure(settings), trigger="prune", pruned_bytes=freed)
