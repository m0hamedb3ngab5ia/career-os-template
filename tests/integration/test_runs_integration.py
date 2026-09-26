"""`careeros run score|list|show|status` end to end: a temp repo root, a fake `claude` first on PATH
(tests/fixtures/fake_claude.py: prints stream-json, never calls a model), real subprocesses."""
from __future__ import annotations

import json
import os
import shutil
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
    return personalize(temp_root)  # doctor must pass: runs refuse to start on the example candidate


def env_for(root: Path, home: Path, fake_bin: Path, **extra) -> dict[str, str]:
    env = subprocess_env(root, home)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env.pop("CLAUDECODE", None)
    env.update(extra)
    return env


def cli(root: Path, env: dict[str, str], *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=env, timeout=timeout, cwd=root)


def add_jobs(root: Path, n: int) -> list[str]:
    store = Store(Settings.load(root))
    now = datetime.now(timezone.utc)
    ids = []
    for i in range(n):
        p = Posting(company=f"Co{i}", title="Backend Software Engineer", ats="greenhouse", ats_job_id=f"r{i}",
                    url=f"https://boards.greenhouse.io/co/jobs/{i}", description_text="python apis " * 40,
                    posted_at=(now - timedelta(hours=50 + i * 10)).isoformat())
        store.save_posting(p)
        ids.append(p.job_id)
    return ids


def set_runs(root: Path, **runs) -> None:
    p = root / "config" / "pipeline.yaml"
    data = yaml.safe_load(p.read_text())
    data.setdefault("runs", {}).update(runs)
    p.write_text(yaml.safe_dump(data, sort_keys=False))


def status_of(root: Path, jid: str) -> str:
    return json.loads((root / "data" / "jobs" / jid / "status.json").read_text())["status"]


def test_dry_run_prints_the_queue_with_reasons_and_runs_nothing(root, home, fake_bin, tmp_path):
    ids = add_jobs(root, 3)
    argv_log = tmp_path / "argv.jsonl"
    r = cli(root, env_for(root, home, fake_bin, FAKE_CLAUDE_ARGV=str(argv_log)), "run", "score", "--dry-run",
            "--max-jobs", "2")
    assert r.returncode == 0, r.stderr
    assert ids[0] in r.stdout and "posted" in r.stdout and "dry run" in r.stdout.lower()
    assert not argv_log.exists()
    assert not (root / "data" / "runs").exists() or not any((root / "data" / "runs").glob("2*"))
    assert all(status_of(root, j) == "found" for j in ids)


def test_run_score_scores_within_budget_and_records_the_run(root, home, fake_bin, tmp_path):
    ids = add_jobs(root, 3)
    argv_log = tmp_path / "argv.jsonl"
    env = env_for(root, home, fake_bin, FAKE_CLAUDE_ARGV=str(argv_log))
    r = cli(root, env, "run", "score", "--max-jobs", "2")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "budget_reached" in r.stdout
    assert [status_of(root, j) for j in ids] == ["scored", "scored", "found"]

    argv = [json.loads(line) for line in argv_log.read_text().splitlines()]
    assert len(argv) == 2
    first = argv[0]
    assert first[0] == "-p" and first[-1] == f"/score-job data/jobs/{ids[0]}"
    assert first[first.index("--output-format") + 1] == "stream-json" and "--verbose" in first
    assert first[first.index("--permission-mode") + 1] == "dontAsk" and "--allowedTools" in first

    lst = cli(root, env, "run", "list", "--json")
    runs = json.loads(lst.stdout)
    assert len(runs) == 1 and runs[0]["kind"] == "score" and runs[0]["stop_reason"] == "budget_reached"
    show = json.loads(cli(root, env, "run", "show", runs[0]["id"], "--json").stdout)
    assert [a["job_id"] for a in show["attempts"]] == ids[:2]
    assert all(a["outcome"] == "ok" and a["session_id"] for a in show["attempts"])
    txt = cli(root, env, "run", "show", runs[0]["id"], "--log")
    assert "attempt" in txt.stdout
    st = json.loads(cli(root, env, "run", "status", "--json").stdout)
    assert st["running"] is None and st["last"]["score"]["id"] == runs[0]["id"]
    assert st["next"]["score"][0]["job_id"] == ids[2]


def test_usage_limit_stops_the_run_and_exits_nonzero(root, home, fake_bin):
    ids = add_jobs(root, 2)
    (root / "data" / "jobs" / ids[0] / ".fake_mode").write_text("usage_limit")
    r = cli(root, env_for(root, home, fake_bin), "run", "score")
    assert r.returncode == 1 and "usage_limit" in r.stdout
    assert [status_of(root, j) for j in ids] == ["found", "found"]


def test_rate_limit_event_is_a_usage_limit(root, home, fake_bin):
    ids = add_jobs(root, 1)
    (root / "data" / "jobs" / ids[0] / ".fake_mode").write_text("rate_event")
    r = cli(root, env_for(root, home, fake_bin), "run", "score", "--json")
    assert r.returncode == 1
    assert json.loads(r.stdout)["stop_reason"] == "usage_limit"


def test_hung_claude_is_killed_at_the_job_timeout(root, home, fake_bin):
    ids = add_jobs(root, 2)
    (root / "data" / "jobs" / ids[0] / ".fake_mode").write_text("hang")
    set_runs(root, job_timeout_minutes={"score": 0.03, "prepare": 1})
    r = cli(root, env_for(root, home, fake_bin), "run", "score", "--json", timeout=60)
    out = json.loads(r.stdout)
    assert r.returncode == 1 and out["stop_reason"] == "timeout"
    assert out["counters"]["attempted"] == 1


def test_doctor_failure_blocks_the_run(temp_root, home, fake_bin):
    add_jobs(temp_root, 1)  # untouched example candidate: doctor FAILs
    r = cli(temp_root, env_for(temp_root, home, fake_bin), "run", "score", "--json")
    assert r.returncode == 1 and json.loads(r.stdout)["stop_reason"] == "doctor_failed"


def test_second_run_while_one_holds_the_lock_exits_busy(root, home, fake_bin):
    add_jobs(root, 1)
    from careeros.runs import locks
    from careeros.runs.store import RunStore

    locks.acquire(RunStore(Settings.load(root)).runner_lock_path, owner="run:other", ttl_seconds=600,
                  pid=os.getpid())
    r = cli(root, env_for(root, home, fake_bin), "run", "score")
    assert r.returncode == 5 and "already running" in r.stderr


def test_main_in_process_status_and_list(root, capsys):
    from careeros.cli import main

    assert main(["--root", str(root), "run", "list"]) == 0
    assert "no runs" in capsys.readouterr().out
    assert main(["--root", str(root), "run", "status"]) == 0
    out = capsys.readouterr().out
    assert "running: none" in out


def test_show_unknown_run(root, capsys):
    from careeros.cli import main

    assert main(["--root", str(root), "run", "show", "nope"]) == 1


def test_fake_claude_not_on_path_means_doctor_fails(root, home, tmp_path):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    add_jobs(root, 1)
    env = subprocess_env(root, home)
    env["PATH"] = f"{empty}{os.pathsep}{Path(PY).parent}{os.pathsep}/usr/bin:/bin"
    env.pop("CLAUDECODE", None)
    if shutil.which("claude", path=env["PATH"]):
        pytest.skip("a real claude is on the system PATH")
    r = cli(root, env, "run", "score", "--json")
    assert r.returncode == 1 and json.loads(r.stdout)["stop_reason"] == "doctor_failed"
