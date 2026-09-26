from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from careeros.runs import locks
from careeros.runs.locks import LockBusy

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def alive(pid):
    return True


def dead(pid):
    return False


def test_acquire_writes_metadata_and_blocks_a_second_owner(tmp_path):
    p = tmp_path / "runner.lock"
    lk = locks.acquire(p, owner="run:r1", ttl_seconds=600, pid=111, now=NOW, pid_alive=alive)
    info = json.loads(p.read_text())
    assert info["owner"] == "run:r1" and info["pid"] == 111 and info["token"] == lk.token
    assert info["expires_at"] == (NOW + timedelta(seconds=600)).isoformat()
    with pytest.raises(LockBusy) as e:
        locks.acquire(p, owner="run:r2", ttl_seconds=600, pid=222, now=NOW, pid_alive=alive)
    assert e.value.holder["owner"] == "run:r1"


def test_same_token_is_reentrant(tmp_path):
    p = tmp_path / "job.lock"
    lk = locks.acquire(p, owner="run:r1", ttl_seconds=600, now=NOW)
    again = locks.acquire(p, owner="prepare-job", ttl_seconds=600, token=lk.token, now=NOW)
    assert again.reentrant and again.token == lk.token
    assert json.loads(p.read_text())["owner"] == "run:r1"  # the first holder keeps it


def test_expired_lock_is_taken_over(tmp_path):
    p = tmp_path / "job.lock"
    locks.acquire(p, owner="prepare-job", ttl_seconds=60, now=NOW)
    later = NOW + timedelta(seconds=61)
    lk = locks.acquire(p, owner="run:r2", ttl_seconds=60, now=later)
    assert lk.stale_taken and json.loads(p.read_text())["owner"] == "run:r2"


def test_dead_pid_on_this_host_is_stale_but_live_pid_is_not(tmp_path):
    p = tmp_path / "runner.lock"
    locks.acquire(p, owner="run:r1", ttl_seconds=3600, pid=111, now=NOW)
    with pytest.raises(LockBusy):
        locks.acquire(p, owner="run:r2", ttl_seconds=3600, pid=222, now=NOW, pid_alive=alive)
    lk = locks.acquire(p, owner="run:r2", ttl_seconds=3600, pid=222, now=NOW, pid_alive=dead)
    assert lk.stale_taken


def test_other_host_pid_is_not_checked(tmp_path):
    p = tmp_path / "runner.lock"
    locks.acquire(p, owner="run:r1", ttl_seconds=3600, pid=111, host="other-mac", now=NOW)
    with pytest.raises(LockBusy):
        locks.acquire(p, owner="run:r2", ttl_seconds=3600, pid=222, now=NOW, pid_alive=dead)


def test_release_needs_the_token(tmp_path):
    p = tmp_path / "job.lock"
    lk = locks.acquire(p, owner="x", ttl_seconds=60, now=NOW)
    assert locks.release(p, "wrong") is False and p.exists()
    assert locks.release(p, lk.token) is True and not p.exists()
    assert locks.release(p, lk.token) is False  # idempotent


def test_force_release(tmp_path):
    p = tmp_path / "job.lock"
    locks.acquire(p, owner="x", ttl_seconds=60, now=NOW)
    assert locks.release(p, None, force=True) and not p.exists()


def test_corrupt_lock_file_counts_as_stale(tmp_path):
    p = tmp_path / "job.lock"
    p.write_text("{not json")
    lk = locks.acquire(p, owner="x", ttl_seconds=60, now=NOW)
    assert lk.stale_taken


def test_status_reports_free_held_stale(tmp_path):
    p = tmp_path / "job.lock"
    assert locks.status(p, now=NOW)["state"] == "free"
    locks.acquire(p, owner="x", ttl_seconds=60, now=NOW)
    assert locks.status(p, now=NOW)["state"] == "held"
    assert locks.status(p, now=NOW + timedelta(minutes=5))["state"] == "stale"


def test_refresh_extends_expiry(tmp_path):
    p = tmp_path / "runner.lock"
    lk = locks.acquire(p, owner="x", ttl_seconds=60, now=NOW)
    locks.refresh(p, lk.token, ttl_seconds=600, now=NOW + timedelta(seconds=30))
    assert json.loads(p.read_text())["expires_at"] == (NOW + timedelta(seconds=630)).isoformat()


def test_no_tmp_files_left_behind(tmp_path):
    p = tmp_path / "job.lock"
    lk = locks.acquire(p, owner="x", ttl_seconds=60, now=NOW)
    locks.release(p, lk.token)
    locks.acquire(p, owner="y", ttl_seconds=60, now=NOW)
    assert sorted(f.name for f in tmp_path.iterdir() if not f.name.endswith(".guard")) == ["job.lock"]
