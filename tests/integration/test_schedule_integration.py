"""`careeros schedule install|status|uninstall`, `careeros tick`, `run pause|resume|catch-up` end to end.
Temp root + temp HOME; a fake `launchctl` and a fake `claude` first on PATH (never the real ones)."""
from __future__ import annotations

import json
import os
import plistlib
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from conftest import FIXTURES, PY, personalize, subprocess_env

from careeros.config import Settings
from careeros.models import Posting
from careeros.store import Store

pytestmark = pytest.mark.integration

FAKE_LAUNCHCTL = f"""#!{PY}
import json, os, sys
with open(os.environ["FAKE_LAUNCHCTL_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
sys.exit(113 if sys.argv[1] == "print" and not os.path.exists(os.environ["FAKE_LAUNCHCTL_LOG"] + ".loaded") else 0)
"""


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def fake_bin(tmp_path: Path) -> Path:
    b = tmp_path / "bin"
    b.mkdir()
    for name, body in (("claude", f"#!{PY}\n" + (FIXTURES / "fake_claude.py").read_text()),
                       ("launchctl", FAKE_LAUNCHCTL)):
        exe = b / name
        exe.write_text(body)
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return b


@pytest.fixture
def root(temp_root: Path) -> Path:
    r = personalize(temp_root)
    p = r / "config" / "pipeline.yaml"
    data = yaml.safe_load(p.read_text())
    data["schedule"]["jobs"]["scout"]["enabled"] = False  # scout does HTTP; no network in tests
    data["schedule"]["quiet_hours"] = None
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return r


@pytest.fixture
def env(root, home, fake_bin, tmp_path) -> dict[str, str]:
    e = subprocess_env(root, home)
    e["PATH"] = f"{fake_bin}{os.pathsep}{e['PATH']}"
    e["FAKE_LAUNCHCTL_LOG"] = str(tmp_path / "launchctl.jsonl")
    e.pop("CLAUDECODE", None)
    return e


def cli(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=env, timeout=120, cwd=root)


def add_job(root: Path) -> str:
    store = Store(Settings.load(root))
    p = Posting(company="Co", title="Backend Software Engineer", ats="greenhouse", ats_job_id="r1",
                url="https://boards.greenhouse.io/co/jobs/1", description_text="python " * 50,
                posted_at=datetime.now(timezone.utc).isoformat())
    store.save_posting(p)
    return p.job_id


def test_schedule_install_status_uninstall(root, env, home, tmp_path):
    r = cli(root, env, "schedule", "install")
    assert r.returncode == 0, r.stderr
    plist = home / "Library" / "LaunchAgents" / "com.careeros.tick.plist"
    data = plistlib.loads(plist.read_bytes())
    assert data["ProgramArguments"][-1] == "tick" and data["WorkingDirectory"] == str(root)
    assert data["StartInterval"] == 15 * 60
    assert str(tmp_path / "bin") in data["EnvironmentVariables"]["PATH"]  # the claude it found
    calls = [json.loads(line) for line in Path(env["FAKE_LAUNCHCTL_LOG"]).read_text().splitlines()]
    assert calls[-1][0] == "bootstrap" and calls[-1][-1] == str(plist)

    st = json.loads(cli(root, env, "schedule", "status", "--json").stdout)
    assert st["installed"] is True and set(st["next"]) >= {"score", "prepare", "prune"}
    un = cli(root, env, "schedule", "uninstall")
    assert un.returncode == 0 and not plist.exists()


def test_tick_runs_due_jobs_then_is_idempotent(root, env):
    jid = add_job(root)
    r = cli(root, env, "tick", "--json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    acts = {d["kind"]: d["action"] for d in out["decisions"]}
    assert acts == {"scout": "disabled", "score": "run", "prepare": "run", "prune": "run"}
    assert json.loads((root / "data" / "jobs" / jid / "status.json").read_text())["status"] == "queued"
    runs = json.loads(cli(root, env, "run", "list", "--json").stdout)
    assert {r["trigger"] for r in runs} == {"schedule"}
    again = json.loads(cli(root, env, "tick", "--json").stdout)
    assert {d["action"] for d in again["decisions"]} <= {"not_due", "disabled"}


def test_pause_resume_and_catch_up(root, env):
    add_job(root)
    assert cli(root, env, "run", "pause", "--until", "+2h", "--reason", "travel").returncode == 0
    st = json.loads(cli(root, env, "run", "status", "--json").stdout)
    assert st["paused"]["reason"] == "travel"
    paused = json.loads(cli(root, env, "tick", "--json").stdout)
    assert {d["action"] for d in paused["decisions"]} <= {"skip_paused", "disabled"}
    assert cli(root, env, "run", "resume").returncode == 0

    state = root / "data" / "runs" / "schedule.json"
    s = json.loads(state.read_text())
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    s["last_tick"] = old
    for k in s["jobs"]:
        s["jobs"][k]["last_run"] = old
    state.write_text(json.dumps(s))
    missed = json.loads(cli(root, env, "tick", "--json").stdout)
    assert "missed" in {d["action"] for d in missed["decisions"]}
    st = json.loads(cli(root, env, "run", "status", "--json").stdout)
    assert st["catch_up"] and "score" in st["catch_up"]["kinds"]

    r = cli(root, env, "run", "catch-up", "--json")
    assert r.returncode == 0, r.stderr
    assert "score" in json.loads(r.stdout)["ran"]
    assert json.loads(cli(root, env, "run", "status", "--json").stdout)["catch_up"] is None
