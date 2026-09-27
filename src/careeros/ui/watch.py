"""Live updates: watch the data and config folders, re-index what changed, tell the browser once per batch.

watchfiles groups changes into one batch until the files have been quiet for `ui.watch_debounce_ms`;
plan_changes() turns the batch into job ids, run ids and flags; handle() re-indexes those (skipping files whose
signature is unchanged) and publishes one `changed` SSE event, or nothing when the batch changed nothing the UI
shows. A scout run that writes hundreds of files therefore costs a few events, not hundreds.
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


_RUN_STATE = {"pause.json", "catch_up.json", "runner.lock", "locks"}


def _is_run_state(name: str) -> bool:
    """Files the runner keeps beside the run folders (not runs themselves)."""
    return name in _RUN_STATE or (name.startswith("queue-") and name.endswith(".json"))


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
            if len(parts) == 1 and not _is_run_state(parts[0]) and not _is_finder_copy(parts[0]):
                if not p.is_file():
                    plan.runs.add(parts[0])          # a run folder created, moved in or moved away
                if not p.is_dir():
                    plan.status = True               # schedule.json, storage.jsonl, launchd logs, or a deleted file
            elif len(parts) <= 1 or parts[0] == "locks":
                plan.status = True                   # runs/ itself, queue-*.json, pause.json, catch_up.json, runner.lock, ...
            elif not _is_finder_copy(parts[0]):
                plan.runs.add(parts[0])
            continue
        if _under(p, roots.config) is not None:
            plan.config = True
            continue
        if _under(p, roots.jobs.parent) is not None:
            plan.status = True                       # data/seen.json, flagged registries, ...
    return plan


def _tracker_watch_dir(folder: Path, root: Path) -> Path | None:
    """The folder to watch for tracker changes: the tracker's own folder, or while that is missing the nearest
    existing ancestor inside the repo root (never outside it). None when neither exists: the caller polls."""
    if folder.is_dir():
        return folder
    for a in folder.parents:
        if _under(a, root) is None:
            return None
        if a.is_dir():
            return a
    return None


class Watcher:
    tracker_poll_s = 2.0        # how often a missing tracker folder outside the repo root is checked for

    def __init__(self, settings: Any, index: Any, broker: Any, *, debounce_ms: int = 300,
                 on_config: Callable[[], None] | None = None):
        from careeros.runs.store import runs_dir_for

        self.index, self.broker, self.debounce_ms, self.on_config = index, broker, debounce_ms, on_config
        self.roots = Roots(jobs=_real(settings.paths["jobs_dir"]), runs=_real(runs_dir_for(settings)),
                           config=_real(Path(settings.root) / "config"), tracker=_real(settings.paths["tracker_xlsx"]),
                           index=_real(index.path))
        self.repo_root = _real(settings.root)
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
        config = plan.config and self.index.update_config()   # False when a UI write already took this change
        if config and self.on_config:
            self.on_config()
        if not (jobs or runs or actions or config or plan.status):
            return None
        payload = {"jobs": jobs, "runs": runs, "actions": actions, "config": config, "status": plan.status}
        self.broker.publish("changed", payload)
        return payload

    # --- thread --------------------------------------------------------------------------------------------

    def _watch(self, dirs: list[Path], recursive: bool):
        from watchfiles import watch

        # step = the quiet window (a batch ends once nothing changed for this long); debounce = the longest a
        # batch may grow while files keep changing
        return watch(*dirs, step=self.debounce_ms, debounce=max(1600, 5 * self.debounce_ms),
                     stop_event=self._stop, recursive=recursive, raise_interrupt=False)

    def _handle_batch(self, paths: Iterable[Path | str]) -> None:
        try:
            self.handle(paths)
        except Exception:  # noqa: BLE001 - one bad batch must not stop live updates
            log.exception("careeros ui: re-index after a file change failed")

    def _loop(self, dirs: list[Path], recursive: bool) -> None:
        try:
            for changes in self._watch(dirs, recursive):
                self._handle_batch(p for _, p in changes)
        except Exception:  # noqa: BLE001
            log.exception("careeros ui: file watcher stopped; restart `careeros ui` for live updates")

    def _tracker_loop(self) -> None:
        """Watch the tracker's folder (not recursively). While it is missing, watch its nearest existing ancestor
        inside the repo root (or poll, when there is none) and switch to the folder once it appears."""
        folder = self.roots.tracker.parent
        try:
            while not self._stop.is_set():
                target = _tracker_watch_dir(folder, self.repo_root)
                if target is None:
                    self._stop.wait(self.tracker_poll_s)
                    if folder.is_dir() and self.roots.tracker.exists():
                        self._handle_batch([self.roots.tracker])
                    continue
                waiting = target != folder
                try:
                    for changes in self._watch([target], False):
                        if waiting:
                            if _tracker_watch_dir(folder, self.repo_root) != target:
                                break                 # the folder (or a nearer ancestor) appeared: re-target
                        elif not folder.is_dir():
                            break                     # the folder went away: fall back to an ancestor
                        else:
                            self._handle_batch(p for _, p in changes)
                except FileNotFoundError:             # the target vanished between the check and the watch
                    self._stop.wait(self.tracker_poll_s)
                    continue
                if waiting and folder.is_dir() and self.roots.tracker.exists():
                    self._handle_batch([self.roots.tracker])   # written before the folder watch attached
        except Exception:  # noqa: BLE001
            log.exception("careeros ui: tracker watcher stopped; restart `careeros ui` for live updates")

    def start(self) -> None:
        dirs = self.watch_dirs()
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        self._spawn(self._loop, dirs, True)
        if not any(_under(self.roots.tracker.parent, d) is not None for d in dirs):
            self._spawn(self._tracker_loop)

    def _spawn(self, target: Callable[..., None], *args: Any) -> None:
        t = threading.Thread(target=target, args=args, name="careeros-ui-watch", daemon=True)
        t.start()
        self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
