"""Advisory lock files with owner, pid, host and expiry. Never blocks: a held lock raises `LockBusy`.

One file per lock (`data/runs/runner.lock`, `data/runs/locks/<job_id>.lock`), created atomically with its full
JSON body (write a temp file, then hard-link it into place: the link fails if the lock exists). A lock is stale,
and is taken over, when it has expired, when its pid is dead on this host, or when the file is unreadable. The
check-and-takeover runs under a short `flock` on `<lock>.guard`, so two processes never both take a stale lock.

A lock taken from the CLI (`careeros job lock`) has no pid (the CLI exits at once), so only its expiry frees it.
The runner's locks carry its pid. The same token re-acquires a lock without changing it (`reentrant`): a skill
run by the runner sees the runner's job lock through `CAREEROS_LOCK_TOKEN`.
"""
from __future__ import annotations

import json
import os
import socket
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

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
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(body, indent=1), encoding="utf-8")
    tmp.replace(path)


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
