from __future__ import annotations

import json
import os
import re
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from careeros.config import Settings, get_settings
from careeros.models import Posting, QAResult, Score, now_iso

POSTING = "posting.json"
SCORE = "score.json"
QA = "qa.json"
ANSWERS = "answers.json"
STATUS = "status.json"
FLAGS = "flags.json"
LOG = "log.md"


# Finder duplicates: "posting 2.json", "log 3.md", "377debe1ff52 2" — never real job data.
_FINDER_COPY_RE = re.compile(r" \d+(\.[^.]+)?$")


def _is_finder_copy(name: str) -> bool:
    return bool(_FINDER_COPY_RE.search(name))


class Store:
    def __init__(self, settings: Settings | None = None, jobs_dir: Path | None = None, seen_file: Path | None = None):
        s = settings or get_settings()
        self.settings = s
        self.jobs_dir = (jobs_dir or s.paths["jobs_dir"]).resolve()
        self.seen_file = (seen_file or s.paths["seen_file"]).resolve()
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.seen_file.parent.mkdir(parents=True, exist_ok=True)
        self._warned_strays = False

    # --- paths ---------------------------------------------------------------

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def exists(self, job_id: str) -> bool:
        return (self.job_dir(job_id) / POSTING).exists()

    # --- generic json ------------------------------------------------------

    def _read(self, job_id: str, name: str) -> dict[str, Any] | None:
        p = self.job_dir(job_id) / name
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def _write(self, job_id: str, name: str, data: dict[str, Any]) -> Path:
        d = self.job_dir(job_id)
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(p)
        return p

    # --- posting -----------------------------------------------------------

    def save_posting(self, posting: Posting) -> Path:
        new = not self.exists(posting.job_id)
        path = self._write(posting.job_id, POSTING, posting.model_dump())
        if new:
            self.set_status(posting.job_id, "found", "posting stored by scout")
            self.set_selected([posting.job_id], False)  # REQ-104: the user ticks jobs for the pipeline
        self._scan_injection(posting)
        return path

    def _scan_injection(self, posting: Posting) -> None:
        """REQ-109: flag a posting whose text looks like a prompt-injection attempt (flags.json + Action Item).
        A clear (`clear_injection`) holds while the reasons stay the same; new reasons flag the job again."""
        from careeros import untrusted

        extra = (self.settings.pipeline.get("injection") or {}).get("extra_patterns") or []
        reasons = untrusted.scan(posting.description_text, posting.description_html, extra)
        with self._flags_lock(posting.job_id):
            flags = self.load_flags(posting.job_id)
            if not reasons and not flags.get("injection_suspected"):
                return
            if reasons == flags.get("injection_reasons"):
                return
            flags.update(injection_suspected=bool(reasons), injection_reasons=reasons, injection_cleared_at=None)
            self._write(posting.job_id, FLAGS, flags)
        if reasons:
            from careeros.tracker import add_action

            add_action(self.settings, f"Possible prompt injection in posting: {'; '.join(reasons)}"[:300]
                       + ". Read it, then `careeros job clear-injection <id>` if it is safe",
                       "injection_suspected", job_id=posting.job_id, link=posting.url, priority="H",
                       needs="laptop", dedupe=True)

    def _flags_lock(self, job_id: str):
        """Serialise flags.json read-modify-writes (scout scan, select, clear) so no writer drops another's keys."""
        from careeros.runs import locks

        d = self.jobs_dir.parent / "locks" / "flags"
        d.mkdir(parents=True, exist_ok=True)
        return locks._guard(d / job_id)  # flock on data/locks/flags/<job_id>.guard

    def load_flags(self, job_id: str) -> dict[str, Any]:
        return self._read(job_id, FLAGS) or {}

    def is_selected(self, job_id: str) -> bool:
        """REQ-104: ticked for prepare/apply. A job from before the flag (no `selected` key) counts as ticked."""
        return bool(self.load_flags(job_id).get("selected", True))

    def set_selected(self, job_ids: Iterable[str], selected: bool) -> None:
        for jid in job_ids:
            with self._flags_lock(jid):
                flags = self.load_flags(jid)
                flags["selected"] = selected
                self._write(jid, FLAGS, flags)

    def set_flag(self, job_id: str, key: str, value: Any) -> None:
        with self._flags_lock(job_id):
            flags = self.load_flags(job_id)
            flags[key] = value
            self._write(job_id, FLAGS, flags)

    def clear_injection(self, job_id: str) -> dict[str, Any]:
        """The user checked a flagged posting ("I checked it"): prepare/apply are allowed again."""
        with self._flags_lock(job_id):
            flags = self.load_flags(job_id)
            flags["injection_cleared_at"] = now_iso()
            self._write(job_id, FLAGS, flags)
        from careeros.tracker import Tracker

        tr = Tracker(settings=self.settings)
        for it in tr.list_action_items(open_only=True):
            if str(it.get("JobID") or "") == job_id and it.get("Type") == "injection_suspected":
                tr.mark_action_done(str(it["ID"]))
        return flags

    def load_posting(self, job_id: str) -> Posting | None:
        d = self._read(job_id, POSTING)
        return Posting.model_validate(d) if d else None

    # --- score / qa / answers ---------------------------------------------

    def save_score(self, score: Score) -> Path:
        return self._write(score.job_id, SCORE, score.model_dump())

    def load_score(self, job_id: str) -> Score | None:
        d = self._read(job_id, SCORE)
        return Score.model_validate(d) if d else None

    def save_qa(self, job_id: str, results: list[QAResult] | QAResult) -> Path:
        items = results if isinstance(results, list) else [results]
        return self._write(job_id, QA, {"results": [r.model_dump() for r in items]})

    def load_qa(self, job_id: str) -> list[QAResult]:
        d = self._read(job_id, QA)
        return [QAResult.model_validate(r) for r in (d or {}).get("results", [])]

    def save_answers(self, job_id: str, answers: dict[str, Any]) -> Path:
        return self._write(job_id, ANSWERS, answers)

    def load_answers(self, job_id: str) -> dict[str, Any]:
        return self._read(job_id, ANSWERS) or {}

    # --- status ------------------------------------------------------------

    def set_status(self, job_id: str, status: str, note: str | None = None) -> None:
        cur = self._read(job_id, STATUS) or {"history": []}
        cur["status"] = status
        cur["updated_at"] = now_iso()
        cur.setdefault("history", []).append({"status": status, "at": cur["updated_at"], "note": note})
        self._write(job_id, STATUS, cur)
        self.append_log(job_id, f"status -> {status}" + (f": {note}" if note else ""), component="store")
        if status == "applied":
            self._freeze_if_missing(job_id)

    def _freeze_if_missing(self, job_id: str) -> None:
        """Every applied job keeps an as-submitted snapshot; make one if nothing froze it yet."""
        from careeros.apply import snapshot

        jd = self.job_dir(job_id)
        try:
            if snapshot.latest(jd):
                return
            out = snapshot.freeze(jd)
        except (OSError, ValueError) as e:  # never block a status change (ValueError covers bad JSON)
            self.append_log(job_id, f"snapshot failed: {e}", component="snapshot")
            return
        self.append_log(job_id, f"frozen as-submitted copy -> {out.relative_to(jd)}", component="snapshot")

    def submitted_at(self, job_id: str) -> str | None:
        from careeros.apply import snapshot

        m = snapshot.latest(self.job_dir(job_id))
        return m["frozen_at"] if m else None

    def get_status(self, job_id: str) -> str | None:
        d = self._read(job_id, STATUS)
        return d.get("status") if d else None

    # --- log ---------------------------------------------------------------

    def append_log(self, job_id: str, msg: str, component: str = "system") -> None:
        d = self.job_dir(job_id)
        d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with (d / LOG).open("a", encoding="utf-8") as f:
            f.write(f"- {ts} [{component}] {msg}\n")

    def read_log(self, job_id: str) -> str:
        p = self.job_dir(job_id) / LOG
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # --- seen --------------------------------------------------------------

    def load_seen(self) -> set[str]:
        if not self.seen_file.exists():
            return set()
        try:
            return set(json.loads(self.seen_file.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            return set()

    def save_seen(self, seen: set[str]) -> None:
        tmp = self.seen_file.with_name(f"{self.seen_file.name}.{os.getpid()}.tmp")  # per-writer temp
        tmp.write_text(json.dumps(sorted(seen)), encoding="utf-8")
        tmp.replace(self.seen_file)

    def mark_seen(self, job_ids: list[str] | set[str]) -> set[str]:
        seen = self.load_seen()
        seen.update(job_ids)
        self.save_seen(seen)
        return seen

    # --- posting history (ghost jobs) ------------------------------------------

    @property
    def history_file(self) -> Path:
        return self.seen_file.parent / "posting_history.json"

    def load_history(self) -> dict[str, dict[str, Any]]:
        if not self.history_file.exists():
            return {}
        try:
            return json.loads(self.history_file.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def update_history(self, postings: list[Posting], today: str | None = None) -> dict[str, dict[str, Any]]:
        """Record every fetched posting (seen or not) under its role key. A new requisition id for the same
        role is a repost (`times_reposted`); a changed `last_updated` on a known id is an edit
        (`times_edited`). Returns the touched entries by key."""
        from careeros.safety.ghost import history_key

        hist = self.load_history()
        now = today or now_iso()
        touched: dict[str, dict[str, Any]] = {}
        for p in postings:
            key = history_key(p.company, p.title, p.location)
            e = hist.setdefault(key, {"first_seen": now, "last_seen": now, "first_published": None,
                                      "last_updated": None, "times_seen": 0, "times_reposted": 0,
                                      "times_edited": 0, "ats_job_ids": [], "job_ids": [], "sightings": [],
                                      "updated_by_id": {}})
            for k, v in (("times_seen", 0), ("times_reposted", 0), ("times_edited", 0), ("updated_by_id", {}),
                         ("first_published", e.pop("posted_at_min", None)), ("last_updated", None)):
                e.setdefault(k, v)
            if key not in touched:
                e["times_seen"] += 1
            e["last_seen"] = now
            pid = p.ats_job_id or p.url or p.job_id
            published = (p.first_published or p.posted_at or "")[:10] or None
            updated = (p.last_updated or "")[:10] or None
            if pid not in e["ats_job_ids"]:
                e["ats_job_ids"].append(pid)
                e["sightings"].append(published or now[:10])
            elif updated and e["updated_by_id"].get(pid) and e["updated_by_id"][pid] != updated:
                e["times_edited"] += 1
            if updated:
                e["updated_by_id"][pid] = updated
                if not e["last_updated"] or updated > e["last_updated"]:
                    e["last_updated"] = updated
            e["times_reposted"] = max(len(e["ats_job_ids"]) - 1, 0)
            if p.job_id not in e["job_ids"]:
                e["job_ids"].append(p.job_id)
            if published and (not e["first_published"] or published < e["first_published"]):
                e["first_published"] = published
            touched[key] = e
        tmp = self.history_file.with_name(f"{self.history_file.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(hist, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.history_file)
        return touched

    def history_for(self, p: Posting) -> dict[str, Any] | None:
        from careeros.safety.ghost import history_key

        return self.load_history().get(history_key(p.company, p.title, p.location))

    # --- listing -----------------------------------------------------------

    def iter_job_ids(self) -> Iterator[str]:
        if not self.jobs_dir.exists():
            return
        strays: list[str] = []
        for d in sorted(self.jobs_dir.iterdir()):
            if d.name.startswith("_"):  # fixtures such as data/jobs/_example: never a real job
                continue
            if _is_finder_copy(d.name):
                strays.append(d.name)
                continue
            if d.is_dir() and (d / POSTING).exists():
                stray_files = [f.name for f in d.iterdir() if _is_finder_copy(f.name)]
                strays.extend(f"{d.name}/{f}" for f in stray_files)
                yield d.name
        if strays and not self._warned_strays:
            self._warned_strays = True
            warnings.warn(
                f"ignoring {len(strays)} Finder duplicate(s) under {self.jobs_dir}: {', '.join(strays[:5])}"
                + (" ..." if len(strays) > 5 else "") + "; delete them by hand", stacklevel=2)

    def list_jobs(self, status: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for jid in self.iter_job_ids():
            st = self.get_status(jid) or "found"
            if status and st != status:
                continue
            p = self.load_posting(jid)
            if not p:
                continue
            sc = self.load_score(jid)
            out.append(
                {
                    "job_id": jid,
                    "company": p.company,
                    "title": p.title,
                    "location": p.location,
                    "ats": p.ats,
                    "url": p.url,
                    "fetched_at": p.fetched_at,
                    "status": st,
                    "category": sc.category if sc else None,
                    "fit": sc.fit if sc else None,
                    "tier": sc.tier if sc else None,
                    "submitted_at": self.submitted_at(jid),
                }
            )
        return out
