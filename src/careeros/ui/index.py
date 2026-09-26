"""The UI's read index: data/careeros.db (SQLite, WAL), built from the canonical files and safe to delete.

    ix = Index(settings)
    ix.sync()                  # incremental: jobs/runs whose files changed, removed jobs, the tracker
    ix.rebuild()               # drop everything and index from scratch (`careeros ui --reindex`)
    ix.update_jobs([job_id])   # the watcher's path: one job (removed from the index when its folder is gone)

Sources: data/jobs/<id>/*.json (posting, status, score, safety, qa, contacts), data/runs/<id>/ (run.json +
attempts), and the tracker's Action Items tab (the only home of action items until they move to
data/action_items.json). Every table is derived; the index never writes back. A job or run whose file signature
(count, newest mtime, total size) is unchanged is skipped. Unreadable JSON is indexed as missing, never fatal.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from careeros.store import _is_finder_copy

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY, company TEXT, title TEXT, location TEXT, ats TEXT, url TEXT, apply_url TEXT,
    category TEXT, fit INTEGER, tier TEXT, status TEXT, safety TEXT, qa_passed INTEGER, qa_score REAL,
    found_at TEXT, applied_at TEXT, updated_at TEXT, closes_at TEXT, pruned INTEGER, sig TEXT);
CREATE INDEX jobs_status ON jobs(status);
CREATE TABLE status_history (job_id TEXT, seq INTEGER, status TEXT, at TEXT, note TEXT);
CREATE INDEX status_history_job ON status_history(job_id);
CREATE TABLE action_items (
    id TEXT PRIMARY KEY, created TEXT, job_id TEXT, company TEXT, role TEXT, type TEXT, what TEXT, link TEXT,
    priority TEXT, needs TEXT, done INTEGER, done_date TEXT);
CREATE TABLE contacts (
    job_id TEXT, seq INTEGER, name TEXT, title TEXT, company TEXT, linkedin TEXT, email TEXT,
    email_confidence TEXT, linkedin_degree INTEGER, mutuals INTEGER, sent INTEGER, replied TEXT);
CREATE INDEX contacts_job ON contacts(job_id);
CREATE TABLE runs (
    id TEXT PRIMARY KEY, kind TEXT, trigger TEXT, status TEXT, stop_reason TEXT, detail TEXT, started_at TEXT,
    ended_at TEXT, duration_s REAL, pid INTEGER, attempted INTEGER, ok INTEGER, failed INTEGER, budget TEXT,
    sig TEXT);
CREATE TABLE attempts (
    run_id TEXT, n INTEGER, job_id TEXT, company TEXT, title TEXT, outcome TEXT, detail TEXT, session_id TEXT,
    started_at TEXT, ended_at TEXT, duration_s REAL);
CREATE INDEX attempts_run ON attempts(run_id);
"""
_TABLES = ("meta", "jobs", "status_history", "action_items", "contacts", "runs", "attempts")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _obj(path: Path) -> dict[str, Any]:
    got = _read_json(path)
    return got if isinstance(got, dict) else {}


def _sig(paths: Iterable[Path]) -> str:
    n = newest = size = 0
    for p in paths:
        try:
            st = p.stat()
        except OSError:
            continue
        n, newest, size = n + 1, max(newest, st.st_mtime_ns), size + st.st_size
    return f"{n}:{newest}:{size}"


def _dir_sig(d: Path) -> str:
    try:
        return _sig(f for f in d.iterdir() if f.is_file() and not _is_finder_copy(f.name))
    except OSError:
        return ""


def default_path(settings: Any) -> Path:
    from careeros.ui.config import load_ui_config

    cfg = load_ui_config(settings)
    if cfg.index_path:
        p = Path(cfg.index_path).expanduser()
        return p if p.is_absolute() else (Path(settings.root) / p).resolve()
    return Path(settings.paths["jobs_dir"]).parent / "careeros.db"


class Index:
    def __init__(self, settings: Any, path: Path | None = None):
        from careeros.runs.store import runs_dir_for

        self.settings = settings
        self.jobs_dir = Path(settings.paths["jobs_dir"])
        self.runs_dir = runs_dir_for(settings)
        self.tracker_path = Path(settings.paths["tracker_xlsx"])
        self.path = Path(path) if path else default_path(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            self._open()
        except sqlite3.DatabaseError:        # not a database (or damaged): it is derived, so start over
            self.con.close()
            self.remove_files(self.path)
            self._open()

    def _open(self) -> None:
        self.con = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    @staticmethod
    def remove_files(path: Path) -> None:
        """Delete the index and its WAL side files (`careeros ui --reindex`)."""
        for suffix in ("", "-wal", "-shm", "-journal"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)

    # --- schema --------------------------------------------------------------------------------------------

    def _ensure_schema(self) -> bool:
        """Create the tables; drop and recreate them when the schema version differs. True = (re)created."""
        with self._lock:
            try:
                row = self.con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            except sqlite3.OperationalError:
                row = None
            if row and row[0] == str(SCHEMA_VERSION):
                return False
            for t in _TABLES:
                self.con.execute(f"DROP TABLE IF EXISTS {t}")
            self.con.executescript(_SCHEMA)
            self.set_meta("schema_version", str(SCHEMA_VERSION))
            return True

    def close(self) -> None:
        with self._lock:
            self.con.close()

    # --- reads ---------------------------------------------------------------------------------------------

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self.con.execute(sql, tuple(params)).fetchall()]

    def get_meta(self, key: str) -> str | None:
        rows = self.query("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self.con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    # --- whole index ---------------------------------------------------------------------------------------

    def rebuild(self) -> dict[str, Any]:
        with self._lock:
            self.con.execute("UPDATE meta SET value = '0' WHERE key = 'schema_version'")
            self._ensure_schema()
            return self.sync()

    def sync(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_schema()
            on_disk = set(self._job_ids())
            known = {r["job_id"] for r in self.query("SELECT job_id FROM jobs")}
            removed = sorted(known - on_disk)
            for jid in removed:
                self._delete_job(jid)
            changed = self.update_jobs(sorted(on_disk))
            run_ids = set(self._run_ids())
            gone_runs = {r["id"] for r in self.query("SELECT id FROM runs")} - run_ids
            for rid in gone_runs:
                self._delete_run(rid)
            runs_changed = self.update_runs(sorted(run_ids))
            tracker = self.update_tracker()
            self.set_meta("indexed_at", _now())
            return {"jobs_changed": changed, "jobs_removed": removed, "runs_changed": runs_changed,
                    "runs_removed": sorted(gone_runs), "tracker": tracker}

    # --- jobs ----------------------------------------------------------------------------------------------

    def _job_ids(self) -> list[str]:
        if not self.jobs_dir.is_dir():
            return []
        return [d.name for d in self.jobs_dir.iterdir()
                if d.is_dir() and not d.name.startswith("_") and not _is_finder_copy(d.name)
                and (d / "posting.json").exists()]

    def _delete_job(self, jid: str) -> None:
        for t in ("jobs", "status_history", "contacts"):
            self.con.execute(f"DELETE FROM {t} WHERE job_id = ?", (jid,))

    def update_jobs(self, job_ids: Iterable[str]) -> list[str]:
        """Re-index these jobs when their files changed; a job whose folder (or posting.json) is gone is removed.
        Returns the ids whose rows changed."""
        changed = []
        with self._lock:
            for jid in job_ids:
                if not jid or _is_finder_copy(jid) or "/" in jid or jid.startswith((".", "_")):
                    continue
                d = self.jobs_dir / jid
                if not (d / "posting.json").exists():
                    if self.query("SELECT 1 FROM jobs WHERE job_id = ?", (jid,)):
                        self._delete_job(jid)
                        changed.append(jid)
                    continue
                sig = _dir_sig(d)
                row = self.query("SELECT sig FROM jobs WHERE job_id = ?", (jid,))
                if row and row[0]["sig"] == sig:
                    continue
                self._index_job(jid, d, sig)
                changed.append(jid)
            if changed:
                self.set_meta("indexed_at", _now())
        return changed

    def _index_job(self, jid: str, d: Path, sig: str) -> None:
        posting = _obj(d / "posting.json")
        status = _obj(d / "status.json")
        score = _obj(d / "score.json")
        safety = _obj(d / "safety.json")
        qa = _obj(d / "qa.json").get("results")
        hist = status.get("history") if isinstance(status.get("history"), list) else []
        hist = [h for h in hist if isinstance(h, dict)]
        qa_passed = qa_score = None
        if isinstance(qa, list) and qa:
            results = [r for r in qa if isinstance(r, dict)]
            qa_passed = int(all(r.get("passed") for r in results)) if results else None
            crit = [v for r in results for v in (r.get("critic_scores") or {}).values() if isinstance(v, (int, float))]
            qa_score = round(sum(crit) / len(crit), 2) if crit else None
        applied_at = next((h.get("at") for h in hist if h.get("status") == "applied"), None)
        found_at = posting.get("fetched_at") or next((h.get("at") for h in hist if h.get("status") == "found"), None)
        fit = score.get("fit")
        self._delete_job(jid)
        self.con.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (jid, posting.get("company"), posting.get("title"), posting.get("location"), posting.get("ats"),
             posting.get("url"), posting.get("apply_url"), score.get("category"),
             fit if isinstance(fit, int) and not isinstance(fit, bool) else None, score.get("tier"),
             status.get("status") or "found", safety.get("verdict"), qa_passed, qa_score, found_at, applied_at,
             status.get("updated_at"), posting.get("closes_at"), int(bool(posting.get("pruned"))), sig))
        self.con.executemany("INSERT INTO status_history VALUES (?,?,?,?,?)",
                             [(jid, i, h.get("status"), h.get("at"), h.get("note")) for i, h in enumerate(hist)])
        contacts = _obj(d / "contacts.json").get("contacts")
        if isinstance(contacts, list):
            rows = []
            for i, c in enumerate(x for x in contacts if isinstance(x, dict)):
                deg, mut = c.get("linkedin_degree"), c.get("mutuals")
                rows.append((jid, i, c.get("name"), c.get("title") or c.get("role"),
                             c.get("company") or posting.get("company"), c.get("linkedin"), c.get("email"),
                             c.get("email_confidence"), deg if isinstance(deg, int) else None,
                             mut if isinstance(mut, int) else None, int(bool(c.get("sent"))), c.get("replied")))
            self.con.executemany("INSERT INTO contacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    # --- runs ----------------------------------------------------------------------------------------------

    def _run_ids(self) -> list[str]:
        if not self.runs_dir.is_dir():
            return []
        return [d.name for d in self.runs_dir.iterdir()
                if d.is_dir() and not _is_finder_copy(d.name) and (d / "run.json").exists()]

    def _delete_run(self, rid: str) -> None:
        self.con.execute("DELETE FROM runs WHERE id = ?", (rid,))
        self.con.execute("DELETE FROM attempts WHERE run_id = ?", (rid,))

    def update_runs(self, run_ids: Iterable[str]) -> list[str]:
        changed = []
        with self._lock:
            for rid in run_ids:
                if not rid or _is_finder_copy(rid) or "/" in rid or rid.startswith("."):
                    continue
                d = self.runs_dir / rid
                if not (d / "run.json").exists():
                    if self.query("SELECT 1 FROM runs WHERE id = ?", (rid,)):
                        self._delete_run(rid)
                        changed.append(rid)
                    continue
                att_dir = d / "attempts"
                att_files = sorted(att_dir.glob("[0-9][0-9][0-9].json")) if att_dir.is_dir() else []
                sig = _sig([d / "run.json", *att_files])
                row = self.query("SELECT sig FROM runs WHERE id = ?", (rid,))
                if row and row[0]["sig"] == sig:
                    continue
                self._index_run(rid, _obj(d / "run.json"), att_files, sig)
                changed.append(rid)
        return changed

    def _index_run(self, rid: str, run: dict[str, Any], att_files: list[Path], sig: str) -> None:
        c = run.get("counters") if isinstance(run.get("counters"), dict) else {}
        self._delete_run(rid)
        self.con.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, run.get("kind"), run.get("trigger"), run.get("status"), run.get("stop_reason"), run.get("detail"),
             run.get("started_at"), run.get("ended_at"), run.get("duration_s"), run.get("pid"),
             c.get("attempted"), c.get("ok"), c.get("failed"), json.dumps(run.get("budget") or {}), sig))
        rows = []
        for f in att_files:
            a = _obj(f)
            if a:
                rows.append((rid, a.get("n"), a.get("job_id"), a.get("company"), a.get("title"), a.get("outcome"),
                             a.get("detail"), a.get("session_id"), a.get("started_at"), a.get("ended_at"),
                             a.get("duration_s")))
        self.con.executemany("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)

    # --- tracker (action items) ----------------------------------------------------------------------------

    def update_tracker(self) -> bool:
        """Re-read the Action Items tab when the workbook changed. A missing tracker indexes as no items and is
        never created here (Tracker() would create one on read)."""
        with self._lock:
            sig = _sig([self.tracker_path]) if self.tracker_path.exists() else "missing"
            if self.get_meta("tracker_sig") == sig:
                return False
            items: list[dict[str, Any]] = []
            if self.tracker_path.exists():
                from careeros.tracker import Tracker

                try:
                    items = Tracker(path=self.tracker_path, settings=self.settings).list_action_items(open_only=False)
                except Exception:  # noqa: BLE001 - a half-written or foreign workbook: keep the old rows
                    return False
            self.con.execute("DELETE FROM action_items")
            self.con.executemany(
                "INSERT OR REPLACE INTO action_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(str(it.get("ID")), _s(it.get("Created")), _s(it.get("JobID")), _s(it.get("Company")),
                  _s(it.get("Role")), _s(it.get("Type")), _s(it.get("What to do")), _s(it.get("Link")),
                  _s(it.get("Priority")), _s(it.get("Needs")), int(str(it.get("Done") or "N").upper() == "Y"),
                  _s(it.get("DoneDate"))) for it in items if it.get("ID")])
            self.set_meta("tracker_sig", sig)
            return True


def _s(v: Any) -> str | None:
    if v is None or v == "":
        return None
    return v.isoformat() if isinstance(v, datetime) else str(v)
