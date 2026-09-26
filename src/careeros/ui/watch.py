"""Live updates: watch the data and config folders, re-index what changed, tell the browser once per batch.

watchfiles groups changes into one batch until the files have been quiet for `ui.watch_debounce_ms`; plan_changes() turns the
batch into job ids, run ids and flags; handle() re-indexes those (skipping files whose signature is unchanged)
and publishes one `changed` SSE event, or nothing when the batch changed nothing the UI shows. A scout run that
writes hundreds of files therefore costs a few events, not hundreds.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from careeros.store import _is_finder_copy

log = logging.getLogger("careeros.ui")


@dataclass(frozen=True)
class Roots:
    jobs: Path
    runs: Path
    config: Path
    tracker: Path
    index: Path


@dataclass
class Plan:
    jobs: set[str] = field(default_factory=set)
    runs: set[str] = field(default_factory=set)
    tracker: bool = False
    config: bool = False
    status: bool = False        # pause, catch-up, queue, schedule state, locks: the Today/Runs panels

    @property
    def any(self) -> bool:
        return bool(self.jobs or self.runs or self.tracker or self.config or self.status)


def _real(p: Path | str) -> Path:
    return Path(os.path.realpath(p))


def _under(p: Path, root: Path) -> tuple[str, ...] | None:
    try:
        return p.relative_to(root).parts
    except ValueError:
        return None


def plan_changes(paths: Iterable[Path | str], roots: Roots) -> Plan:
    plan = Plan()
    index_names = {roots.index.name + s for s in ("", "-wal", "-shm", "-journal")}
    tracker_names = {roots.tracker.name, roots.tracker.name + ".pending.json"}
    for raw in paths:
        p = Path(raw)
        name = p.name
        if name.startswith(".") or name.endswith(".tmp") or _is_finder_copy(name):
            continue
        if p.parent == roots.index.parent and name in index_names:
            continue
        if p.parent == roots.tracker.parent and name in tracker_names:
            plan.tracker = True
            continue
        if (parts := _under(p, roots.jobs)) is not None:
            if parts and not parts[0].startswith(("_", ".")) and not _is_finder_copy(parts[0]) \
                    and not any(_is_finder_copy(x) for x in parts):
                plan.jobs.add(parts[0])
            continue
        if (parts := _under(p, roots.runs)) is not None:
            if len(parts) == 1 or parts[0] == "locks":
                plan.status = True                   # queue-*.json, pause.json, catch_up.json, runner.lock, ...
            elif not _is_finder_copy(parts[0]):
                plan.runs.add(parts[0])
            continue
        if _under(p, roots.config) is not None:
            plan.config = True
            continue
        if _under(p, roots.jobs.parent) is not None:
            plan.status = True                       # data/seen.json, flagged registries, ...
    return plan


class Watcher:
    def __init__(self, settings: Any, index: Any, broker: Any, *, debounce_ms: int = 300,
                 on_config: Callable[[], None] | None = None):
        from careeros.runs.store import runs_dir_for

        self.index, self.broker, self.debounce_ms, self.on_config = index, broker, debounce_ms, on_config
        self.roots = Roots(jobs=_real(settings.paths["jobs_dir"]), runs=_real(runs_dir_for(settings)),
                           config=_real(Path(settings.root) / "config"), tracker=_real(settings.paths["tracker_xlsx"]),
                           index=_real(index.path))
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def watch_dirs(self) -> list[Path]:
        """Folders watched recursively; one inside another is dropped. The tracker's folder is watched on its own,
        not recursively (it may be a busy folder such as ~/Desktop)."""
        dirs = sorted({self.roots.jobs, self.roots.runs, self.roots.config}, key=lambda p: len(p.parts))
        out: list[Path] = []
        for d in dirs:
            if not any(_under(d, o) is not None for o in out):
                out.append(d)
        return out

    def handle(self, paths: Iterable[Path | str]) -> dict[str, Any] | None:
        plan = plan_changes([_real(p) for p in paths], self.roots)
        if not plan.any:
            return None
        jobs = self.index.update_jobs(sorted(plan.jobs)) if plan.jobs else []
        runs = self.index.update_runs(sorted(plan.runs)) if plan.runs else []
        actions = self.index.update_tracker() if plan.tracker else False
        if plan.config and self.on_config:
            self.on_config()
        if not (jobs or runs or actions or plan.config or plan.status):
            return None
        payload = {"jobs": jobs, "runs": runs, "actions": actions, "config": plan.config, "status": plan.status}
        self.broker.publish("changed", payload)
        return payload

    # --- thread --------------------------------------------------------------------------------------------

    def _loop(self, dirs: list[Path], recursive: bool) -> None:
        from watchfiles import watch

        try:
            # step = the quiet window (a batch ends once nothing changed for this long); debounce = the longest a
            # batch may grow while files keep changing
            for changes in watch(*dirs, step=self.debounce_ms, debounce=max(1600, 5 * self.debounce_ms),
                                 stop_event=self._stop, recursive=recursive, raise_interrupt=False):
                try:
                    self.handle(p for _, p in changes)
                except Exception:  # noqa: BLE001 - one bad batch must not stop live updates
                    log.exception("careeros ui: re-index after a file change failed")
        except Exception:  # noqa: BLE001
            log.exception("careeros ui: file watcher stopped; restart `careeros ui` for live updates")

    def start(self) -> None:
        dirs = self.watch_dirs()
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        groups = [(dirs, True)]
        if not any(_under(self.roots.tracker.parent, d) is not None for d in dirs):
            groups.append(([self.roots.tracker.parent], False))
        for ds, rec in groups:
            t = threading.Thread(target=self._loop, args=(ds, rec), name="careeros-ui-watch", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
