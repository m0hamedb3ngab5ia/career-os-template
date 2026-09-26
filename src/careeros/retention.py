"""Retention: trim old, bulky job files so data/ stays small. Driven by `pipeline.yaml: retention`.

Two rules, each measured from the job's last status change (status.json history, else updated_at):

- Closed jobs (rejected / withdrawn / ghosted) older than `screenshots_after_closed_days` lose the apply
  step screenshots in `screenshots/`. The confirmation shot (`NN_confirmation.png`) stays when
  `keep_confirmation_screenshot` is on.
- Postings never prepared (found / scored / skipped) older than `unprepared_posting_days` become a stub:
  every field stays except the description, which is cut to a short preview (the HTML copy is dropped).
  Dedupe, repost and tracker code only need the ids, company, title, url and dates. A stubbed found / scored
  job is also moved to `skipped` (status.json and tracker) so it leaves the prepare queue: scoring or a safety
  check on a 500-char preview would be meaningless. `careeros safety check` refuses a pruned posting.

Never touched: jobs in any other status, `submitted/` snapshots, anything outside `screenshots/`, `status.json` and
`posting.json`, the shared state in data/ (seen.json, posting_history.json, flagged_registry.yaml,
verified_companies.yaml), and Finder duplicates. 0 or null days turns a rule off.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from careeros.config import ConfigError, Settings
from careeros.store import POSTING, STATUS, Store, _is_finder_copy

DEFAULTS: dict[str, Any] = {
    "screenshots_after_closed_days": 30,
    "keep_confirmation_screenshot": True,
    "unprepared_posting_days": 90,
}
CLOSED = ("rejected", "withdrawn", "ghosted")
UNPREPARED = ("found", "scored", "skipped")
QUEUE = ("found", "scored")  # still waiting for score/prepare: a stub must leave this queue
SCREENSHOT_DIR = "screenshots"
STUB_TEXT_CHARS = 500
_CONFIRMATION_RE = re.compile(r"^\d+_confirmation\b", re.I)


@dataclass
class PruneItem:
    job_id: str
    action: str  # delete_screenshots | stub_posting
    paths: list[str] = field(default_factory=list)
    bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def retention_config(settings: Settings) -> dict[str, Any]:
    raw = settings.pipeline.get("retention")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("pipeline.yaml: retention must be a mapping (see examples/config/pipeline.yaml)")
    cfg = dict(DEFAULTS)
    for key in ("screenshots_after_closed_days", "unprepared_posting_days"):
        if key not in raw:
            continue
        val = raw[key]
        if val is None:
            cfg[key] = 0
            continue
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            raise ConfigError(f"pipeline.yaml: retention.{key} must be a whole number of days >= 0 (0 = off), got {val!r}")
        cfg[key] = val
    keep = raw.get("keep_confirmation_screenshot")
    if keep is not None:
        if not isinstance(keep, bool):
            raise ConfigError("pipeline.yaml: retention.keep_confirmation_screenshot must be true/false, "
                              f"got {keep!r}")
        cfg["keep_confirmation_screenshot"] = keep
    return cfg


def _parse(ts: Any) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def last_change(status: dict[str, Any]) -> datetime | None:
    """When the job last changed status: newest parseable history `at`, else `updated_at`."""
    stamps = [_parse(h.get("at")) for h in status.get("history") or [] if isinstance(h, dict)]
    stamps = [s for s in stamps if s]
    if stamps:
        return max(stamps)
    return _parse(status.get("updated_at"))


def _age_days(status: dict[str, Any], now: datetime) -> float | None:
    at = last_change(status)
    return None if at is None else (now - at).total_seconds() / 86400


def _read_json(path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def stub_posting(posting: dict[str, Any], now: datetime) -> dict[str, Any]:
    """posting.json without the bulky description; everything dedupe and the tracker read is kept."""
    out = dict(posting)
    text = str(out.get("description_text") or "")
    out["description_text"] = text if len(text) <= STUB_TEXT_CHARS else text[:STUB_TEXT_CHARS].rstrip() + "…"
    out["description_html"] = ""
    out["pruned"] = True
    out["pruned_at"] = now.replace(microsecond=0).isoformat()
    return out


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _screenshot_targets(job_dir, keep_confirmation: bool) -> list:
    d = job_dir / SCREENSHOT_DIR
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or _is_finder_copy(f.name):
            continue
        if keep_confirmation and _CONFIRMATION_RE.match(f.stem):
            continue
        out.append(f)
    return out


def plan(settings: Settings, now: datetime | None = None) -> list[PruneItem]:
    """What `prune` would do right now. Reads only; changes nothing."""
    now = now or datetime.now(timezone.utc)
    cfg = retention_config(settings)
    shot_days, post_days = cfg["screenshots_after_closed_days"], cfg["unprepared_posting_days"]
    store = Store(settings)
    items: list[PruneItem] = []
    for jid in store.iter_job_ids():
        jdir = store.job_dir(jid)
        status = _read_json(jdir / STATUS) or {}
        st = status.get("status") or "found"
        age = _age_days(status, now)
        if age is None:
            continue
        if st in CLOSED and shot_days and age > shot_days:
            files = _screenshot_targets(jdir, cfg["keep_confirmation_screenshot"])
            if files:
                items.append(PruneItem(jid, "delete_screenshots", [str(f) for f in files],
                                       sum(f.stat().st_size for f in files)))
        elif st in UNPREPARED and post_days and age > post_days:
            path = jdir / POSTING
            posting = _read_json(path)
            if not posting or posting.get("pruned"):
                continue
            saved = path.stat().st_size - len(_dump(stub_posting(posting, now)).encode("utf-8"))
            if saved > 0:
                items.append(PruneItem(jid, "stub_posting", [str(path)], saved))
    return items


def execute(settings: Settings, items: list[PruneItem], now: datetime | None = None) -> int:
    """Apply a plan. Returns bytes freed. Each touched job gets a `[prune]` line in its log.md."""
    from careeros.tracker import set_status_both

    now = now or datetime.now(timezone.utc)
    store = Store(settings)
    days = retention_config(settings)["unprepared_posting_days"]
    freed = 0
    for item in items:
        jdir = store.job_dir(item.job_id)
        if item.action == "delete_screenshots":
            gone = 0
            for p in item.paths:
                f = jdir / SCREENSHOT_DIR / os.path.basename(p)  # only ever inside this job's screenshots/
                if f.is_file():
                    size = f.stat().st_size
                    f.unlink()
                    freed += size
                    gone += 1
            if gone:
                store.append_log(item.job_id, f"removed {gone} apply screenshot(s) (retention)", component="prune")
        elif item.action == "stub_posting":
            path = jdir / POSTING
            posting = _read_json(path)
            if not posting or posting.get("pruned"):
                continue
            before = path.stat().st_size
            tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
            tmp.write_text(_dump(stub_posting(posting, now)), encoding="utf-8")
            tmp.replace(path)
            freed += max(0, before - path.stat().st_size)
            store.append_log(item.job_id, "posting.json trimmed to a stub (retention)", component="prune")
            if store.get_status(item.job_id) in QUEUE:
                set_status_both(settings, item.job_id, "skipped",
                                f"retention stub (posting older than {days} days)")
    return freed


def summarize(items: list[PruneItem]) -> dict[str, int]:
    return {"jobs": len({i.job_id for i in items}), "files": sum(len(i.paths) for i in items),
            "bytes": sum(i.bytes for i in items)}


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"

