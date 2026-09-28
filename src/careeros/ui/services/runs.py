"""Run control for the UI: start, watch, cancel, pause and catch up runs through the same code as the CLI.

Batches (score, prepare) start as a detached `careeros run <kind> --json` process (its own session, output under
data/runs/ui/), so ranking, budgets, locks, retries, the daily cap and every stop reason stay the CLI's, and a run
outlives a UI restart. Steps (scout, tracker sync, prune, inbox sync) start as `python -m careeros.ui.services.step`
and record a run the same way. The UI reads progress from data/runs/ like any other file; it never writes run
records itself.

Cancel sends SIGTERM only to a process whose command line is a careeros run or step (the CLI turns SIGTERM into
stop reason `cancelled` at the next safe point). A batch started by the scheduler (`careeros tick`) is not
signalled: Pause all stops it before its next job.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from careeros.config import Settings
from careeros.runs import locks
from careeros.runs.atomic import write_text
from careeros.runs.status import run_state
from careeros.runs.store import RunStore
from careeros.ui.services.stream import parse_event

BATCH_KINDS = ("score", "prepare")
JOB_KINDS = ("score", "prepare", "apply")  # `--job <id>` runs: one explicit job, apply only this way
STEP_KINDS = ("scout", "tracker", "prune", "inbox_sync")
KEEP_OUTPUTS = 50  # launch output files kept under data/runs/ui/


class Busy(RuntimeError):
    def __init__(self, holder: dict[str, Any], what: str = "another run is already running"):
        self.holder = holder
        super().__init__(f"{what} ({holder.get('note') or holder.get('owner')}, pid {holder.get('pid')})")


class Paused(RuntimeError):
    pass


class NotSetUp(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ps_cmdline(pid: int) -> list[str] | str:
    """The process's exact argv from /proc/<pid>/cmdline (Linux), else its command line from `ps -ww` (macOS; a
    joined string, see classify_cmdline). Without -ww, procps cuts the line at 80 columns when not on a terminal."""
    proc = Path(f"/proc/{pid}/cmdline")
    try:
        if proc.exists():
            return [a.decode("utf-8", "replace") for a in proc.read_bytes().split(b"\0") if a]
        return subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def ps_started(pid: int) -> datetime | None:
    """When the process started (`ps -o lstart=`, local time, whole seconds); None when unknown."""
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=5, env={**os.environ, "LC_ALL": "C"}).stdout
        return datetime.strptime(" ".join(out.split()), "%a %b %d %H:%M:%S %Y").astimezone()
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


CANCELLABLE_RUNS = ("score", "prepare", "apply", "catch-up")
# `ps lstart` is whole seconds and, on Linux, derived from boot time plus jiffies, which drifts by seconds on VMs.
# A pid reused within a minute of the lock being taken AND running a careeros run or step is not a real case.
START_SLACK_S = 60


def _cli_kind(rest: list[str]) -> str | None:
    while rest[:1] == ["--root"]:
        rest = rest[2:]
    if rest[:1] == ["tick"]:
        return "tick"
    if len(rest) >= 2 and rest[0] == "run" and rest[1] in CANCELLABLE_RUNS:
        return "run"
    return None


def classify_argv(argv: list[str]) -> str | None:
    """What a process is, from its exact argv: "run" (`careeros run score|prepare|catch-up`, as `-m careeros.cli`
    or the `careeros` entry point), "step" (`-m careeros.ui.services.step <kind>`), "tick", or None (anything
    else, including other careeros commands). Whole tokens, never a substring, so a reused pid is not mistaken."""
    for i, t in enumerate(argv):
        if t == "-m" and i + 1 < len(argv):
            mod, rest = argv[i + 1], argv[i + 2:]
            if mod == "careeros.cli":
                return _cli_kind(rest)
            if mod == "careeros.ui.services.step":
                while rest[:1] == ["--root"]:
                    rest = rest[2:]
                return "step" if len(rest) == 1 and rest[0] in STEP_KINDS else None
            return None
        if os.path.basename(t) == "careeros" and i <= 1:  # the entry point (possibly after its interpreter)
            return _cli_kind(argv[i + 1:])
    return None


def classify_cmdline(cmd: str | list[str], root: Any = None) -> str | None:
    """`classify_argv` for an exact argv (Linux /proc) or a joined command line (macOS `ps`, which loses argument
    boundaries). For a joined line, `--root <root>` (the known repo root, which may contain spaces) is removed
    first, and only the part after `-m <module>` or the `careeros` executable is split on spaces: the UI starts its
    children with the root in CAREEROS_ROOT, so their arguments never contain a path."""
    if isinstance(cmd, list):
        return classify_argv(cmd)
    if root:
        cmd = cmd.replace(f" --root {root}", "")
    m = re.search(r"(?:^|\s)-m (careeros\.cli|careeros\.ui\.services\.step)(?=\s|$)(.*)$", cmd)
    if m:
        return classify_argv(["python", "-m", m.group(1), *m.group(2).split()])
    m = re.search(r"(?:^|/)careeros(?=\s|$)(.*)$", cmd)  # the entry point: .../bin/careeros <args>
    if m:
        before = cmd[:m.start()]  # "" or its directory, maybe after the interpreter (shebang scripts on macOS)
        if before == "" or (before[:1] in "/.~" and " -" not in before):
            return classify_argv(["careeros", *m.group(1).split()])
    return None


def _parse_dt(v: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


class RunControl:
    def __init__(self, settings: Settings, *, popen: Callable[..., Any] = subprocess.Popen,
                 python: str = sys.executable, env: dict[str, str] | None = None,
                 pid_alive: Callable[[int], bool] = locks.pid_alive,
                 cmdline: Callable[[int], list[str] | str] = ps_cmdline,
                 kill: Callable[[int, int], None] = os.kill, now: Callable[[], datetime] = _utcnow,
                 sleep: Callable[[float], None] = time.sleep, launchctl: Callable[..., Any] | None = None,
                 started: Callable[[int], datetime | None] = ps_started, agents_dir: Path | None = None,
                 which: Callable[[str], str | None] | None = None):
        self.settings = settings
        self.rs = RunStore(settings)
        self.popen, self.python, self.env = popen, python, env
        self.pid_alive, self.cmdline, self.kill, self.now, self.sleep = pid_alive, cmdline, kill, now, sleep
        self.launchctl, self.started, self.agents_dir = launchctl, started, agents_dir
        if which is None:
            import shutil

            which = shutil.which
        self.which = which

    # --- starting ------------------------------------------------------------------------------------------

    def _held(self, path: Path) -> dict[str, Any] | None:
        st = locks.status(path, now=self.now(), alive=self.pid_alive)
        return st if st.get("state") == "held" else None

    @staticmethod
    def _holder_line(held: dict[str, Any] | None) -> str | None:
        return f"{held.get('pid')} {held.get('acquired_at', '')}" if held else None

    @staticmethod
    def _marker_line(marker: Path) -> str | None:
        try:
            return marker.read_text().split("\n", 1)[0]
        except FileNotFoundError:  # removed by a concurrent start: no marker
            return None

    def _check_can_start(self) -> None:
        held = self._held(self.rs.runner_lock_path)
        if held:
            raise Busy(held)
        if self.rs.pause_state(self.now()):
            raise Paused("runs are paused; resume them first")

    def _spawn(self, name: str, argv: list[str]) -> dict[str, Any]:
        out_dir = self.rs.dir / "ui"
        out_dir.mkdir(parents=True, exist_ok=True)
        old = sorted(out_dir.glob("*.out"))
        for f in old[:max(0, len(old) - (KEEP_OUTPUTS - 1))]:
            f.unlink(missing_ok=True)
        for m in out_dir.glob("cancel-*"):  # cancel markers of runs that have stopped
            rid = m.name.removeprefix("cancel-")
            if rid == "catch-up":  # no run record: keep the marker while the holder it names still holds tick.lock
                if self._marker_line(m) == self._holder_line(self._held(self.rs.dir / "tick.lock")):
                    continue
            else:
                run = self.rs.load_run(rid)
                if run and self._state(run) == "running":
                    continue
            m.unlink(missing_ok=True)
        out = out_dir / f"{self.now().astimezone().strftime('%Y%m%d-%H%M%S')}-{name}.out"
        root = str(self.settings.root)
        # the root travels in CAREEROS_ROOT, not argv: macOS `ps` joins argv with spaces, and a root such as
        # "~/My Jobs/career-os" would make the child's command line impossible to classify for Cancel
        env = {**(self.env if self.env is not None else os.environ), "CAREEROS_ROOT": root}
        with out.open("ab") as fh:
            proc = self.popen([self.python, "-m", *argv], cwd=root, env=env,
                              stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
        return {"started": True, "pid": proc.pid, "output": str(out)}

    def start(self, kind: str, preset: str | None = None, max_jobs: int | None = None,
              max_minutes: float | None = None, dry_run: bool = False, *, job_id: str | None = None,
              force: bool = False) -> dict[str, Any]:
        """Start a score or prepare batch (same as `careeros run <kind> ...`), or with `job_id` one job's
        score / prepare / apply run (`careeros run <kind> --job <id> [--force]`, run id chosen here and returned
        as `run_id`). A dry run ranks and returns the selection in-process: it never calls Claude and takes no
        lock, so there is nothing to detach. JobNotRunnable (the runner's own reasons) before anything is
        spawned when the job is not a candidate; Tier A is never submitted (the run stages it for review)."""
        from careeros.runs.config import budget_for, load_runs_config

        kinds = JOB_KINDS if job_id else BATCH_KINDS
        if kind not in kinds:
            raise ValueError(f"unknown run kind {kind!r}; use {' or '.join(kinds)}")
        cfg = load_runs_config(self.settings)
        if job_id:
            max_jobs = 1
        budget_for(cfg, kind, preset=preset, max_jobs=max_jobs, max_minutes=max_minutes)  # ValueError on bad input
        if dry_run:
            from careeros.runs.service import run_batch

            return run_batch(self.settings, kind, budget_for(cfg, kind, preset=preset, max_jobs=max_jobs,
                                                             max_minutes=max_minutes), cfg=cfg, dry_run=True,
                             job_ids=[job_id] if job_id else None, force=force)
        run_id = None
        if job_id:
            from careeros.runs.runner import JobNotRunnable, new_run_id, select_candidates

            from careeros.runs.failures import Failures
            from careeros.runs.policy import load_retry_config

            # the runner leaves a job out of retries to its Action Item: refuse it here, not in the detached child
            skip = Failures(self.rs).exhausted(kind, load_retry_config(cfg.raw)["max_attempts"])
            ranked, excluded = select_candidates(self.settings, kind, cfg, self.now(), job_ids=[job_id], force=force,
                                                 skip_ids=skip)
            if not ranked:
                raise JobNotRunnable(kind, {e["job_id"]: e["reason"] for e in excluded})
            run_id = new_run_id(kind, self.now())
        self._check_can_start()
        argv = ["careeros.cli", "run", kind]
        if preset:
            argv += ["--preset", preset]
        if max_jobs is not None and not job_id:
            argv += ["--max-jobs", str(max_jobs)]
        if max_minutes is not None:
            argv += ["--max-minutes", f"{max_minutes:g}"]
        if job_id:
            argv += ["--job", job_id, *(["--force"] if force else []), "--run-id", run_id]
        out = {"kind": kind, **self._spawn(run_id or kind, [*argv, "--json"])}
        return {**out, "run_id": run_id} if job_id else out

    def start_error(self, run_id: str) -> str | None:
        """The refusal a job run started here printed before writing any run record (`careeros run --json` prints
        {"error": ...} to its .out file), else None."""
        if not re.fullmatch(r"\w[\w.-]*", run_id or ""):  # a run id, never a path or a glob
            return None
        for f in sorted((self.rs.dir / "ui").glob(f"*-{run_id}.out"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("error"):
                return str(data["error"])
        return None

    def active_run_for(self, job_id: str) -> str | None:
        """The id of the running batch whose job in flight (its job lock) is this job, else None. A job that is
        only queued in the batch is `queued_in_run`: cancelling for it would kill the whole batch."""
        run = self.current()
        if run and run.get("state") == "running" and run.get("current_job") == job_id:
            return run["id"]
        return None

    def queued_in_run(self, job_id: str) -> str | None:
        """The id of the running batch whose queue names this job while another job is in flight, else None."""
        run = self.current()
        if not run or run.get("state") != "running" or run.get("current_job") == job_id:
            return None
        if any(q.get("job_id") == job_id for q in run.get("queue") or []):
            return run["id"]
        return None

    def start_step(self, kind: str) -> dict[str, Any]:
        """Start scout | tracker | prune (--yes) | inbox_sync as a recorded step run."""
        from careeros.ui.services.step import step_lock_path

        if kind not in STEP_KINDS:
            raise ValueError(f"unknown step {kind!r}; use one of {', '.join(STEP_KINDS)}")
        if kind == "inbox_sync":
            from careeros.runs.schedule import load_schedule

            if not load_schedule(self.settings).jobs["inbox_sync"].enabled:
                raise NotSetUp("Inbox sync is not set up yet: turn on schedule.jobs.inbox_sync once the inbox-sync "
                               "skill is finished and Gmail is logged in")
            self._check_can_start()  # a headless skill call: the runner lock and pause apply
        else:
            from careeros.ui.services.step import PIPELINE_STEPS

            held = self._held(step_lock_path(self.rs, kind))
            if held:
                raise Busy(held, f"a {kind} step is already running")
            if kind in PIPELINE_STEPS and (held := self._held(self.rs.runner_lock_path)):
                raise Busy(held)  # scout / prune never run beside a batch (the shared pipeline lock)
        return {"kind": kind, **self._spawn(kind, ["careeros.ui.services.step", kind])}

    def prune_plan(self) -> dict[str, Any]:
        """What Prune would remove right now (`careeros prune --json` without --yes). Reads only."""
        from careeros import retention

        items = retention.plan(self.settings, self.now())
        return {"dry_run": True, "items": [i.to_dict() for i in items], "summary": retention.summarize(items)}

    # --- cancel, pause, catch-up ---------------------------------------------------------------------------

    def _holder_of(self, run_id: str | None) -> tuple[str | None, dict[str, Any] | None]:
        held = self._held(self.rs.runner_lock_path)
        if held and (run_id is None or held.get("owner") == f"run:{run_id}"):
            return str(held.get("owner", "")).partition(":")[2] or None, held
        if run_id is None:  # a catch-up between batches (scout, prune) holds only tick.lock
            tick = self._held(self.rs.dir / "tick.lock")
            if tick and tick.get("owner") == "catch-up":
                return "catch-up", tick
        if run_id:
            run = self.rs.load_run(run_id) or {}
            from careeros.ui.services.step import step_lock_path

            held = self._held(step_lock_path(self.rs, str(run.get("kind"))))
            if held and held.get("owner") == f"step:{run_id}":
                return run_id, held
        return None, None

    def cancel(self, run_id: str | None = None) -> dict[str, Any]:
        """SIGTERM the careeros process running `run_id` (default: the running batch). Never signals anything else."""
        rid, held = self._holder_of(run_id)
        if not held:
            return {"status": "idle", "detail": "nothing is running"}
        pid = held.get("pid")
        if not isinstance(pid, int) or not self.pid_alive(pid):
            return {"status": "idle", "detail": "the run's process has already stopped"}
        marker = self.rs.dir / "ui" / f"cancel-{rid}"
        # the marker names the holder it cancelled (pid + lock time): a later holder of the same run id, such as
        # the next catch-up, finds a stale marker and can still be cancelled
        holder = self._holder_line(held)
        if self._marker_line(marker) == holder:
            return {"status": "already_stopping", "run_id": rid, "pid": pid}
        what = classify_cmdline(self.cmdline(pid), root=self.settings.root)
        if what == "tick":
            return {"status": "refused", "run_id": rid,
                    "detail": "started by the scheduler; use Pause all to stop it before its next job"}
        if what not in ("run", "step"):
            return {"status": "refused", "run_id": rid, "detail": f"pid {pid} is not a careeros run or step"}
        began, acquired = self.started(pid), _parse_dt(held.get("acquired_at"))
        if began and acquired and began > acquired + timedelta(seconds=START_SLACK_S):
            return {"status": "refused", "run_id": rid,
                    "detail": f"pid {pid} started after the lock was taken (a reused pid)"}
        try:
            self.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return {"status": "idle", "detail": "the run's process has already stopped"}
        except PermissionError:
            return {"status": "refused", "run_id": rid, "detail": f"not allowed to signal pid {pid}"}
        marker.parent.mkdir(parents=True, exist_ok=True)
        # Write then rename, so _spawn never reads a half-written marker and prunes it.
        write_text(marker, f"{holder}\n{self.now().isoformat()}\n")
        return {"status": "cancelling", "run_id": rid, "pid": pid}

    def pause(self, until: datetime | None = None, reason: str = "") -> dict[str, Any]:
        return self.rs.set_pause(until, reason, self.now())

    def resume(self) -> bool:
        return self.rs.clear_pause()

    def catch_up(self, dismiss: bool = False) -> dict[str, Any]:
        """Dismiss in-process; otherwise start `careeros run catch-up` detached (it runs batches)."""
        from careeros.runs.tick import load_catch_up, run_catch_up

        if dismiss:
            return run_catch_up(self.settings, dismiss=True, now=self.now())
        rec = load_catch_up(self.rs)
        if rec is None:
            return {"started": False, "pending": False}
        if self.rs.pause_state(self.now()):
            raise Paused("runs are paused; resume them first")
        return {"pending": True, "kinds": list(rec["kinds"]),
                **self._spawn("catch-up", ["careeros.cli", "run", "catch-up", "--json"])}

    # --- reading -------------------------------------------------------------------------------------------

    def _state(self, run: dict[str, Any]) -> str:
        return run_state(self.rs, run, alive=self.pid_alive)

    def _with_state(self, run: dict[str, Any]) -> dict[str, Any]:
        st = self._state(run)
        if run.get("status") == "running" and st not in ("running", "interrupted"):
            run = self.rs.load_run(run["id"]) or run  # it finished between our read and the lock check
        out = {**run, "state": st}
        if st == "interrupted" and not run.get("stop_reason"):
            out["stop_reason"] = "interrupted"
        return out

    def current(self) -> dict[str, Any] | None:
        """The running batch: budget used, the job in flight (from its job lock) and the finished attempts. Also a
        running step (scout, tracker, prune: its run record) or an unrecorded pipeline-lock holder (`careeros
        scout|prune`, the scheduler's scout/prune): kind, started_at and the holder's pid, nothing else."""
        rid, held = self._holder_of(None)
        run = self.rs.load_run(rid) if rid else None
        if not run and held is None:
            run, held = self._running_step()
        if not run and held is not None and str(held.get("owner", "")).partition(":")[0] != "run":
            return self._holder_only(held)
        if not run:
            return None
        rid = run["id"]
        b = run.get("budget") or {}
        started = _parse_dt(run.get("started_at"))
        minutes = round((self.now() - started).total_seconds() / 60, 1) if started else None
        job = None
        ldir = self.rs.dir / "locks"
        if ldir.is_dir():
            for f in sorted(ldir.glob("*.lock")):
                info = locks.read(f) or {}
                if info.get("owner") == f"run:{rid}":
                    job = f.stem
                    break
        return {**self._with_state(run), "holder": held, "current_job": job,
                "used": {"jobs": (run.get("counters") or {}).get("attempted", 0), "max_jobs": b.get("max_jobs"),
                         "minutes": minutes, "max_minutes": b.get("max_minutes")},
                "attempts": self.rs.load_attempts(rid)}

    def _running_step(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        from careeros.ui.services.step import step_lock_path

        for kind in ("scout", "tracker", "prune"):
            held = self._held(step_lock_path(self.rs, kind))
            owner, _, rid = str((held or {}).get("owner", "")).partition(":")
            if held and owner == "step" and (run := self.rs.load_run(rid)):
                return run, held
        return None, None

    def _holder_only(self, held: dict[str, Any]) -> dict[str, Any]:
        owner = str(held.get("owner", ""))
        kind = str(held.get("note") or owner.partition(":")[2] or owner).split(" ")[0]
        started = _parse_dt(held.get("acquired_at"))
        minutes = round((self.now() - started).total_seconds() / 60, 1) if started else None
        return {"id": owner, "kind": kind, "trigger": owner.partition(":")[0], "status": "running",
                "state": "running", "step": True, "stop_reason": None, "detail": "", "budget": {}, "counters": {},
                "started_at": held.get("acquired_at"), "ended_at": None, "duration_s": None, "pid": held.get("pid"),
                "holder": held, "current_job": None,
                "used": {"jobs": 0, "max_jobs": None, "minutes": minutes, "max_minutes": None}, "attempts": []}

    def history(self, kind: str | None = None, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        """Past and running runs, newest first. `cursor` = the last id of the previous page."""
        out: list[dict[str, Any]] = []
        more = False
        for rid in self.rs.run_ids():
            if cursor and rid >= cursor:
                continue
            run = self.rs.load_run(rid)
            if not run or (kind and run.get("kind") != kind):
                continue
            if len(out) == limit:
                more = True
                break
            out.append(self._with_state(run))
        return {"runs": out, "next_cursor": out[-1]["id"] if more and out else None}

    def detail(self, run_id: str) -> dict[str, Any] | None:
        run = self.rs.load_run(run_id)
        if run is None:
            return None
        return {**self._with_state(run), "attempts": self.rs.load_attempts(run_id), "log": self.rs.read_log(run_id)}

    def queue(self, kind: str, limit: int = 25) -> dict[str, Any]:
        """The live ranking for the next run of `kind` (what `careeros run status` computes), with the reasons."""
        from careeros.runs.config import load_runs_config
        from careeros.runs.runner import select_candidates

        if kind not in BATCH_KINDS:
            raise ValueError(f"unknown run kind {kind!r}")
        ranked, excluded = select_candidates(self.settings, kind, load_runs_config(self.settings), self.now())
        return {"kind": kind, "items": ranked[:limit], "total": len(ranked), "excluded": excluded}

    def tail(self, run_id: str, *, follow: bool = True, poll_s: float = 0.5) -> Iterator[dict[str, Any]]:
        """Plain events from the run's attempt streams and run.log; with `follow`, keep polling (by file size)
        until the run is no longer running, then yield {type: end}."""
        rdir = self.rs.run_dir(run_id)
        offsets: dict[Path, int] = {}

        def read_new() -> Iterator[dict[str, Any]]:
            files = sorted((rdir / "attempts").glob("[0-9][0-9][0-9].stream.jsonl")) if (rdir / "attempts").is_dir() \
                else []
            for f in [*files, rdir / "run.log"]:
                if not f.exists():
                    continue
                size = f.stat().st_size
                pos = offsets.get(f, 0)
                if size <= pos:
                    continue
                with f.open("rb") as fh:
                    fh.seek(pos)
                    chunk = fh.read(size - pos)
                done = chunk.rfind(b"\n") + 1  # a half-written line waits for the next poll
                offsets[f] = pos + done
                for line in chunk[:done].decode("utf-8", "replace").splitlines():
                    if f.name == "run.log":
                        if line.strip():
                            yield {"type": "log", "text": line}
                        continue
                    ev = parse_event(line)
                    if ev:
                        yield {**ev, "attempt": int(f.name[:3])}

        yield from read_new()
        if not follow:
            return
        while True:
            run = self.rs.load_run(run_id) or {}
            state = self._state(run) if run else "missing"
            if state != "running":
                run = self.rs.load_run(run_id) or run  # the final stop reason
                yield from read_new()
                yield {"type": "end", "state": state, "stop_reason": run.get("stop_reason"), "counters": run.get("counters")}
                return
            self.sleep(poll_s)
            yield from read_new()

    # --- schedule, storage, advice -------------------------------------------------------------------------

    def schedule_status(self) -> dict[str, Any]:
        from careeros.runs import launchd
        from careeros.runs.schedule import load_schedule
        from careeros.runs.tick import schedule_overview

        label = load_schedule(self.settings).launchd_label
        return {**launchd.status(label, **self._launchd_kw()), **schedule_overview(self.settings, self.now())}

    def _launchd_kw(self) -> dict[str, Any]:
        kw: dict[str, Any] = {"agents_dir": self.agents_dir}
        if self.launchctl:
            kw["launchctl"] = self.launchctl
        return kw

    def schedule_install(self) -> dict[str, Any]:
        from careeros.runs import launchd
        from careeros.runs.schedule import load_schedule

        sc = load_schedule(self.settings)
        claude = self.which("claude")
        dirs = [os.path.dirname(p) for p in (claude, self.python) if p]
        plist = launchd.build_plist(label=sc.launchd_label, python=self.python, root=self.settings.root,
                                    runs_dir=self.rs.dir, tick_minutes=sc.tick_minutes, path_dirs=dirs)
        out = launchd.install(plist, **self._launchd_kw())
        return {**out, "warning": None if claude else
                "`claude` is not on PATH; scheduled score and prepare runs will stop with doctor_failed"}

    def schedule_uninstall(self) -> dict[str, Any]:
        from careeros.runs import launchd
        from careeros.runs.schedule import load_schedule

        return launchd.uninstall(load_schedule(self.settings).launchd_label, **self._launchd_kw())

    def storage(self) -> dict[str, Any]:
        from careeros.runs.storage import load_snapshots, measure

        return {**measure(self.settings), "snapshots": load_snapshots(self.rs)}

    def advise(self) -> dict[str, Any]:
        from careeros.runs.advisor import advise

        return advise(self.settings, self.now())

    def advise_apply(self, rec_id: str) -> dict[str, Any]:
        """Same code as `careeros advise apply <id>`. LookupError / ValueError / ConfigError on refusal."""
        from careeros.runs.advisor import apply_recommendation

        return apply_recommendation(self.settings, rec_id, self.now())
