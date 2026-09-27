"""Advisory lock files with owner, pid, host and expiry. Never blocks: a held lock raises `LockBusy`.

One file per lock (`data/runs/runner.lock`, `data/runs/locks/<job_id>.lock`), created atomically with its full
JSON body (write a temp file, then hard-link it into place: the link fails if the lock exists). A lock is stale,
and is taken over, when it has expired, when its pid is dead on this host, or when the file is unreadable. The
check-and-takeover runs under a short `flock` on `<lock>.guard`, so two processes never both take a stale lock.

A lock taken from the CLI (`careeros job lock`) has no pid (the CLI exits at once), so only its expiry frees it.
The runner's locks carry its pid. The same token re-acquires a lock without changing it (`reentrant`): a skill
run by the runner sees the runner's job lock through `CAREEROS_LOCK_TOKEN`.

`data/runs/runner.lock` is the one pipeline lock: batches and headless skill runs (owner `run:<id>`), scout and
prune from the CLI (`cli:<kind>`), the scheduler (`schedule:<kind>`, `catch_up:<kind>`) and UI steps
(`step:<id>`) all take it, so a prune never deletes a job folder a batch is preparing and a scout never writes
while a batch reads. `pipeline_lock` is the helper for everything that is not a batch: it waits up to
`runs.lock_wait_s` while a batch holds the lock (`runs.scout_waits_for_batch`, Recommended) or refuses at once,
and raises `PipelineBusy`. A batch that finds the lock held raises `RunBusy` (the UI answers 409).
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from careeros.runs.atomic import write_json

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]


class LockBusy(RuntimeError):
    def __init__(self, path: Path, holder: dict[str, Any]):
        self.path, self.holder = path, holder
        super().__init__(f"{path.name} held by {holder.get('owner')} (pid {holder.get('pid')}, "
                         f"until {holder.get('expires_at')})")


@dataclass
class Lock:
    path: Path
    token: str
    owner: str
    info: dict[str, Any] = field(default_factory=dict)
    reentrant: bool = False
    stale_taken: bool = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _parse(ts: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read(path: Path) -> dict[str, Any] | None:
    """The lock's JSON body; {} when the file exists but is unreadable; None when there is no lock."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def is_stale(info: dict[str, Any], now: datetime, alive: Callable[[int], bool] = pid_alive,
             host: str | None = None) -> bool:
    if not info or not info.get("token"):
        return True
    exp = _parse(info.get("expires_at"))
    if exp is None or now >= exp:
        return True
    pid = info.get("pid")
    if isinstance(pid, int) and info.get("host") == (host or socket.gethostname()) and not alive(pid):
        return True
    return False


def status(path: Path, now: datetime | None = None, alive: Callable[[int], bool] = pid_alive) -> dict[str, Any]:
    """{state: free | held | stale, **lock body}."""
    info = read(path)
    if info is None:
        return {"state": "free"}
    return {**info, "state": "stale" if is_stale(info, now or _now(), alive) else "held"}


@contextmanager
def _guard(path: Path) -> Iterator[None]:
    if fcntl is None:  # pragma: no cover
        yield
        return
    g = path.with_name(path.name + ".guard")
    with g.open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _write_new(path: Path, body: dict[str, Any]) -> bool:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(body, indent=1), encoding="utf-8")
    try:
        os.link(tmp, path)
        return True
    except FileExistsError:
        return False
    finally:
        tmp.unlink(missing_ok=True)


def _replace(path: Path, body: dict[str, Any]) -> None:
    write_json(path, body, indent=1)


def acquire(path: Path, owner: str, ttl_seconds: float, *, token: str | None = None, pid: int | None = None,
            host: str | None = None, now: datetime | None = None, pid_alive: Callable[[int], bool] = pid_alive,
            note: str = "") -> Lock:
    """Take the lock or raise LockBusy. `token` equal to the holder's = reentrant (nothing changes)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = now or _now()
    me = host or socket.gethostname()
    body = {"owner": owner, "token": token or uuid.uuid4().hex, "pid": pid, "host": me,
            "acquired_at": now.isoformat(), "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            "note": note}
    if _write_new(path, body):
        return Lock(path, body["token"], owner, body)
    with _guard(path):
        cur = read(path)
        if cur is None:
            if _write_new(path, body):
                return Lock(path, body["token"], owner, body)
            cur = read(path) or {}
        if token and cur.get("token") == token:
            return Lock(path, token, str(cur.get("owner")), cur, reentrant=True)
        if not is_stale(cur, now, pid_alive, me):
            raise LockBusy(path, cur)
        _replace(path, body)
        return Lock(path, body["token"], owner, body, stale_taken=True)


def release(path: Path, token: str | None, force: bool = False) -> bool:
    """Remove the lock when `token` matches (or `force`). False when it is not ours or already gone."""
    path = Path(path)
    with _guard(path) if path.parent.exists() else _nullctx():
        cur = read(path)
        if cur is None:
            return False
        if not force and cur.get("token") != token:
            return False
        path.unlink(missing_ok=True)
        return True


def refresh(path: Path, token: str, ttl_seconds: float, now: datetime | None = None) -> bool:
    """Push the expiry of a lock we hold `ttl_seconds` past `now` (the runner's heartbeat)."""
    path = Path(path)
    with _guard(path):
        cur = read(path)
        if not cur or cur.get("token") != token:
            return False
        cur["expires_at"] = ((now or _now()) + timedelta(seconds=ttl_seconds)).isoformat()
        _replace(path, cur)
        return True


@contextmanager
def _nullctx() -> Iterator[None]:
    yield


class PipelineBusy(LockBusy):
    """The pipeline lock stayed held (by a batch, a scout, a prune...) for the whole wait."""

    def __init__(self, path: Path, holder: dict[str, Any], waited_s: float = 0.0):
        super().__init__(path, holder)
        self.waited_s = waited_s
        waited = f"; waited {waited_s:.0f}s" if waited_s else ""
        RuntimeError.__init__(self, f"the pipeline is busy: {holder.get('owner')} ({holder.get('note') or '-'}, "
                                    f"pid {holder.get('pid')}, since {holder.get('acquired_at')}){waited}; "
                                    "try again when it finishes")


PIPELINE_TTL_S = 6 * 3600  # scout/prune/steps are short; a dead pid frees the lock sooner
_HELD = threading.local()  # .tokens: pipeline lock path -> token held by THIS thread (nested use re-enters;
# another thread of the same process is a separate holder and waits/refuses like another process)


def _held() -> dict[str, str]:
    tokens = getattr(_HELD, "tokens", None)
    if tokens is None:
        tokens = _HELD.tokens = {}
    return tokens


def acquire_waiting(path: Path, owner: str, ttl_seconds: float, *, wait_s: float = 0.0, poll_s: float = 1.0,
                    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                    on_wait: Callable[[dict[str, Any], float], None] | None = None, **kw: Any) -> Lock:
    """`acquire`, retried every `poll_s` for up to `wait_s` seconds; PipelineBusy when still held.
    `on_wait(holder, wait_s)` is called once, before the first wait (the CLI says what it is waiting for)."""
    start = clock()
    announced = False
    while True:
        try:
            return acquire(path, owner, ttl_seconds, **kw)
        except LockBusy as e:
            waited = clock() - start
            if waited >= wait_s:
                raise PipelineBusy(e.path, e.holder, waited) from None
            if on_wait is not None and not announced:
                announced = True
                on_wait(e.holder, wait_s)
            sleep(min(poll_s, wait_s - waited))


def pipeline_wait_s(settings: Any) -> float:
    """runs.lock_wait_s when runs.scout_waits_for_batch (Recommended), else 0 (refuse at once)."""
    from careeros.runs.config import load_runs_config

    cfg = load_runs_config(settings)
    return float(cfg.lock_wait_s) if cfg.scout_waits_for_batch else 0.0


@contextmanager
def pipeline_lock(settings: Any, owner: str, *, note: str = "", wait_s: float | None = None, poll_s: float = 1.0,
                  ttl_seconds: float = PIPELINE_TTL_S, sleep: Callable[[float], None] = time.sleep,
                  clock: Callable[[], float] = time.monotonic,
                  pid_alive: Callable[[int], bool] = pid_alive,
                  on_wait: Callable[[dict[str, Any], float], None] | None = None) -> Iterator[Lock]:
    """Hold data/runs/runner.lock for scout / prune / a UI step. `wait_s` None = from config (pipeline_wait_s).
    Nested use in one thread (a UI step calling the scheduler's scout) re-enters the outer lock; another thread
    is another holder. `on_wait(holder, wait_s)` is called once before waiting."""
    from careeros.runs.store import RunStore

    path = RunStore(settings).runner_lock_path
    key = str(path)
    wait = pipeline_wait_s(settings) if wait_s is None else wait_s
    held = _held()
    lk = acquire_waiting(path, owner, ttl_seconds, wait_s=wait, poll_s=poll_s, sleep=sleep, clock=clock,
                         on_wait=on_wait, token=held.get(key), pid=os.getpid(), note=note, pid_alive=pid_alive)
    if lk.reentrant:
        yield lk
        return
    held[key] = lk.token
    try:
        yield lk
    finally:
        held.pop(key, None)
        release(path, lk.token)
