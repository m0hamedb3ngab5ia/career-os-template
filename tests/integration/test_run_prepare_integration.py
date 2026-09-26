"""PR B end to end: `careeros run prepare|cap`, `careeros job lock|unlock|check`, mutating job commands honouring
the per-job lock, retry-once -> Action Item across two real runs. Fake `claude` on PATH; no model, no network."""
from __future__ import annotations

import json
import os
import stat
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from conftest import FIXTURES, PY, personalize, subprocess_env

from careeros.config import Settings
from careeros.models import Posting
from careeros.store import Store

pytestmark = pytest.mark.integration


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def fake_bin(tmp_path: Path) -> Path:
    b = tmp_path / "bin"
    b.mkdir()
    exe = b / "claude"
    exe.write_text(f"#!{PY}\n" + (FIXTURES / "fake_claude.py").read_text())
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return b


@pytest.fixture
def root(temp_root: Path) -> Path:
    return personalize(temp_root)


@pytest.fixture
def env(root, home, fake_bin) -> dict[str, str]:
    e = subprocess_env(root, home)
    e["PATH"] = f"{fake_bin}{os.pathsep}{e['PATH']}"
    for k in ("CLAUDECODE", "CAREEROS_LOCK_TOKEN", "CAREEROS_RUN_ID"):
        e.pop(k, None)
    return e


def cli(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=env, timeout=120, cwd=root)


def add_job(root: Path, n: int, status: str = "scored", fit: int = 80, decision: str | None = "prepare") -> str:
    store = Store(Settings.load(root))
    p = Posting(company=f"Co{n}", title="Backend Software Engineer", ats="greenhouse", ats_job_id=f"r{n}",
                url=f"https://boards.greenhouse.io/co/jobs/{n}", description_text="python apis " * 40,
                posted_at=(datetime.now(timezone.utc) - timedelta(hours=60 + n)).isoformat())
    store.save_posting(p)
    if decision:
        (store.job_dir(p.job_id) / "score.json").write_text(json.dumps(
            {"job_id": p.job_id, "decision": decision, "fit": fit, "category": "swe_backend", "tier": "C"}))
    if status != "found":
        store.set_status(p.job_id, status, "test")
    return p.job_id


def status_of(root: Path, jid: str) -> str:
    return json.loads((root / "data" / "jobs" / jid / "status.json").read_text())["status"]


def test_run_prepare_prepares_by_fit_and_status_shows_the_cap(root, env):
    a, b = add_job(root, 1, fit=70), add_job(root, 2, fit=95)
    r = cli(root, env, "run", "prepare", "--max-jobs", "1")
    assert r.returncode == 0, r.stdout + r.stderr
    assert status_of(root, b) == "queued" and status_of(root, a) == "scored"
    st = json.loads(cli(root, env, "run", "status", "--json").stdout)
    assert st["cap"]["cap"] >= 1 and st["cap"]["applied"] == 0
    assert st["next"]["prepare"][0]["job_id"] == a
    assert st["auto_submit"]["enabled"] is False


def test_run_cap_check_exits_3_at_the_cap(root, env):
    p = root / "config" / "targets.yaml"
    t = yaml.safe_load(p.read_text())
    t["volume"]["max_applications_per_day"] = 1
    t["volume"]["season_multiplier"] = {}
    p.write_text(yaml.safe_dump(t, sort_keys=False))
    ok = cli(root, env, "run", "cap", "--check")
    assert ok.returncode == 0 and "0/1" in ok.stdout
    jid = add_job(root, 1, status="queued")
    assert cli(root, env, "job", "status", jid, "applied").returncode == 0
    full = cli(root, env, "run", "cap", "--check", "--json")
    assert full.returncode == 3
    data = json.loads(full.stdout)
    assert data["applied"] == 1 and data["reached"] and data["date"] == date.today().isoformat()


def test_job_lock_check_unlock_and_mutations_honour_it(root, env):
    jid = add_job(root, 1)
    lk = cli(root, env, "job", "lock", jid, "--owner", "prepare-job", "--json")
    assert lk.returncode == 0, lk.stderr
    token = json.loads(lk.stdout)["token"]
    assert cli(root, env, "job", "check", jid).returncode == 6
    again = cli(root, env, "job", "lock", jid, "--owner", "someone-else")
    assert again.returncode == 6 and "prepare-job" in again.stderr

    denied = cli(root, env, "job", "status", jid, "queued")
    assert denied.returncode == 6 and "locked" in denied.stderr and status_of(root, jid) == "scored"
    assert cli(root, env, "job", "show", jid).returncode == 0          # read-only always works
    assert cli(root, env, "jobs", "list").returncode == 0
    ok = cli(root, env, "job", "status", jid, "queued", "--lock-token", token)
    assert ok.returncode == 0 and status_of(root, jid) == "queued"
    via_env = cli(root, {**env, "CAREEROS_LOCK_TOKEN": token}, "job", "status", jid, "needs_review")
    assert via_env.returncode == 0
    assert cli(root, env, "tracker", "upsert", jid, "--field", "Status=queued").returncode == 6

    assert cli(root, env, "job", "unlock", jid, "--token", "wrong").returncode == 1
    assert cli(root, env, "job", "unlock", jid, "--token", token).returncode == 0
    assert cli(root, env, "job", "check", jid).returncode == 0
    assert cli(root, env, "job", "status", jid, "queued").returncode == 0


def test_force_overrides_a_lock(root, env):
    jid = add_job(root, 1)
    cli(root, env, "job", "lock", jid, "--owner", "x")
    assert cli(root, env, "job", "status", jid, "queued", "--force").returncode == 0
    assert cli(root, env, "job", "unlock", jid, "--force").returncode == 0


def test_expired_manual_lock_frees_itself(root, env):
    jid = add_job(root, 1)
    assert cli(root, env, "job", "lock", jid, "--ttl-minutes", "0.0001").returncode == 0
    import time
    time.sleep(0.05)
    assert cli(root, env, "job", "check", jid).returncode == 0


def test_skill_under_the_runner_reenters_the_runner_lock(root, env):
    jid = add_job(root, 1)
    lk = json.loads(cli(root, env, "job", "lock", jid, "--owner", "run:r1", "--json").stdout)
    inner = cli(root, {**env, "CAREEROS_LOCK_TOKEN": lk["token"]}, "job", "lock", jid, "--owner", "prepare-job",
                "--json")
    assert inner.returncode == 0 and json.loads(inner.stdout)["reentrant"] is True


def test_retry_once_then_action_item_across_runs(root, env):
    jid = add_job(root, 1, status="found", decision=None)
    (root / "data" / "jobs" / jid / ".fake_mode").write_text("garbage")
    first = cli(root, env, "run", "score", "--json")
    assert json.loads(first.stdout)["counters"]["failed"] == 1
    second = cli(root, env, "run", "score", "--json")
    assert json.loads(second.stdout)["counters"]["attempted"] == 1
    items = cli(root, env, "action", "list")
    assert jid[:6] in items.stdout or "failed twice" in items.stdout
    third = json.loads(cli(root, env, "run", "score", "--json").stdout)
    assert third["counters"]["attempted"] == 0
    assert status_of(root, jid) == "found"
