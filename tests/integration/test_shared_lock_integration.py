"""`careeros prune --yes` / `careeros scout` as real subprocesses while a batch holds data/runs/runner.lock."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from conftest import PY, subprocess_env

from careeros.config import Settings
from careeros.runs import locks
from careeros.runs.store import RunStore

pytestmark = pytest.mark.integration


def _cli(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=subprocess_env(root, home), timeout=120)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def _set_runs(root: Path, **kv) -> None:
    p = root / "config" / "pipeline.yaml"
    data = yaml.safe_load(p.read_text())
    data.setdefault("runs", {}).update(kv)
    p.write_text(yaml.safe_dump(data))


def _hold_batch(root: Path) -> None:
    # this test process is alive, so the lock is held (not stale) for the child
    locks.acquire(RunStore(Settings.load(root)).runner_lock_path, owner="run:batch1", ttl_seconds=600,
                  pid=os.getpid(), note="prepare (manual)")


def test_prune_yes_waits_for_the_batch_then_refuses(temp_root, home):
    _set_runs(temp_root, lock_wait_s=1)
    _hold_batch(temp_root)
    t0 = time.monotonic()
    r = _cli(temp_root, home, "prune", "--yes")
    assert r.returncode == 6, r.stderr
    assert time.monotonic() - t0 >= 1
    assert "run:batch1" in r.stderr and "waited" in r.stderr


def test_prune_dry_run_never_waits(temp_root, home):
    _set_runs(temp_root, lock_wait_s=30)
    _hold_batch(temp_root)
    r = _cli(temp_root, home, "prune")
    assert r.returncode == 0, r.stderr


def test_scout_refuses_at_once_when_the_switch_is_off(temp_root, home):
    _set_runs(temp_root, scout_waits_for_batch=False, lock_wait_s=30)
    _hold_batch(temp_root)
    t0 = time.monotonic()
    r = _cli(temp_root, home, "scout")
    assert r.returncode == 6, r.stderr
    assert time.monotonic() - t0 < 20 and "run:batch1" in r.stderr
