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


def test_run_prepare_with_job_runs_only_that_job_and_reports_json(root, home, fake_bin, tmp_path):
    ids = add_jobs(root, 3)
    env = env_for(root, home, fake_bin, FAKE_CLAUDE_ARGV=str(tmp_path / "argv.jsonl"))
    r = cli(root, env, "run", "score", "--job", ids[1], "--json")
    assert r.returncode == 0, r.stderr
    assert status_of(root, ids[1]) == "scored" and status_of(root, ids[0]) == "found"
    r = cli(root, env, "run", "prepare", "--job", ids[1], "--json")
    assert r.returncode == 0, r.stderr
    rec = json.loads(r.stdout)
    assert rec["kind"] == "prepare" and rec["counters"]["attempted"] == 1 and rec["counters"]["ok"] == 1
    assert [q["job_id"] for q in rec["queue"]] == [ids[1]]
    assert status_of(root, ids[1]) == "queued"
    argv = [json.loads(l) for l in (tmp_path / "argv.jsonl").read_text().splitlines()]
    assert argv[-1][-1] == f"/prepare-job data/jobs/{ids[1]}"
    # done already (status queued): refused with the reason unless --force
    r = cli(root, env, "run", "prepare", "--job", ids[1], "--json")
    assert r.returncode == 2 and json.loads(r.stdout)["reasons"] == {ids[1]: "status queued"}
    r = cli(root, env, "run", "prepare", "--job", ids[1])
    assert r.returncode == 2 and "status queued" in r.stderr and "--force" in r.stderr
    r = cli(root, env, "run", "prepare", "--job", ids[1], "--force", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["counters"]["attempted"] == 1
    r = cli(root, env, "run", "prepare", "--job", "nope", "--json")
    assert r.returncode == 2 and json.loads(r.stdout)["reasons"] == {"nope": "not found"}
    r = cli(root, env, "run", "prepare", "--job", "nope")
    assert r.returncode == 2 and "not found" in r.stderr


def test_run_apply_needs_job_and_uses_the_apply_skill(root, home, fake_bin, tmp_path):
    ids = add_jobs(root, 1)
    env = env_for(root, home, fake_bin, FAKE_CLAUDE_ARGV=str(tmp_path / "argv.jsonl"))
    r = cli(root, env, "run", "apply")
    assert r.returncode == 2 and "--job" in r.stderr
    assert not (tmp_path / "argv.jsonl").exists()
    r = cli(root, env, "run", "apply", "--job", ids[0], "--json")
    assert r.returncode == 2 and json.loads(r.stdout)["reasons"] == {ids[0]: "status found"}
    assert cli(root, env, "run", "score", "--job", ids[0]).returncode == 0
    assert cli(root, env, "run", "prepare", "--job", ids[0]).returncode == 0
    r = cli(root, env, "run", "apply", "--job", ids[0], "--json")
    assert r.returncode == 0, r.stderr
    rec = json.loads(r.stdout)
    # auto_submit is off by default, so the run hands CAREEROS_AUTO_SUBMIT=0 and apply-job stages the form
    assert rec["kind"] == "apply" and rec["counters"]["ok"] == 1 and status_of(root, ids[0]) == "needs_review"
    argv = [json.loads(l) for l in (tmp_path / "argv.jsonl").read_text().splitlines()]
    assert argv[-1][-1] == f"/apply-job data/jobs/{ids[0]}"
    assert "mcp__claude-in-chrome__*" in argv[-1][argv[-1].index("--allowedTools") + 1]
    assert "mcp__claude-in-chrome__*" not in argv[0][argv[0].index("--allowedTools") + 1]


def test_run_apply_stages_a_tier_a_job_parked_in_needs_review(root, home, fake_bin, tmp_path):
    """Tier A across the CLI -> headless process boundary: prepare-job leaves it in needs_review with QA passed;
    `run apply --job` picks it, hands the skill CAREEROS_AUTO_SUBMIT=0 and accepts the staged outcome."""
    jid = add_jobs(root, 1)[0]
    jdir = root / "data" / "jobs" / jid
    (jdir / "score.json").write_text(json.dumps({"job_id": jid, "decision": "prepare", "fit": 90,
                                                 "category": "swe_backend", "tier": "A"}))
    (jdir / "prepare.json").write_text(json.dumps({"job_id": jid, "status": "needs_review", "qa_pass": True}))
    Store(Settings.load(root)).set_status(jid, "needs_review", "test: prepare-job parked Tier A")
    env = env_for(root, home, fake_bin, FAKE_CLAUDE_ENV=str(tmp_path / "env.jsonl"))
    r = cli(root, env, "run", "apply", "--job", jid, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.loads(r.stdout)
    assert rec["kind"] == "apply" and rec["counters"]["ok"] == 1 and rec["counters"]["attempted"] == 1
    seen = [json.loads(l) for l in (tmp_path / "env.jsonl").read_text().splitlines()]
    assert len(seen) == 1 and seen[0]["CAREEROS_AUTO_SUBMIT"] == "0" and seen[0]["CAREEROS_AUTO_SUBMIT_REASON"]
    assert seen[0]["CAREEROS_RUN_ID"] == rec["id"]
    assert status_of(root, jid) == "needs_review"


def test_run_apply_auto_submits_when_an_allow_rule_matches(root, home, fake_bin, tmp_path):
    """auto_submit on + a matching allow rule (tier_c, safety pass): the run hands CAREEROS_AUTO_SUBMIT=1 across the
    process boundary and apply-job submits (outcome submitted, status applied)."""
    jid = add_jobs(root, 1)[0]
    jdir = root / "data" / "jobs" / jid
    (jdir / "score.json").write_text(json.dumps({"job_id": jid, "decision": "prepare", "fit": 70,
                                                 "category": "swe_backend", "tier": "C"}))
    (jdir / "prepare.json").write_text(json.dumps({"job_id": jid, "status": "prepared", "qa_pass": True}))
    (jdir / "safety.json").write_text(json.dumps({"job_id": jid, "verdict": "pass"}))
    Store(Settings.load(root)).set_status(jid, "prepared", "test: prepared Tier C")
    set_runs(root, auto_submit={"enabled": True, "allow": ["tier_c"], "manual": ["tier_a"]})
    env = env_for(root, home, fake_bin, FAKE_CLAUDE_ENV=str(tmp_path / "env.jsonl"))
    r = cli(root, env, "run", "apply", "--job", jid, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.loads(r.stdout)
    assert rec["kind"] == "apply" and rec["counters"]["ok"] == 1 and rec["counters"]["failed"] == 0
    seen = [json.loads(l) for l in (tmp_path / "env.jsonl").read_text().splitlines()]
    assert len(seen) == 1 and seen[0]["CAREEROS_AUTO_SUBMIT"] == "1"
    assert seen[0]["CAREEROS_AUTO_SUBMIT_REASON"] == "allowed: tier_c"
    assert status_of(root, jid) == "applied"


def test_run_force_without_job_exits_2_before_anything_runs(root, home, fake_bin, tmp_path):
    add_jobs(root, 1)
    env = env_for(root, home, fake_bin, FAKE_CLAUDE_ARGV=str(tmp_path / "argv.jsonl"))
    r = cli(root, env, "run", "score", "--force", "--json")
    assert r.returncode == 2, r.stderr
    assert "--force" in json.loads(r.stdout)["error"] and "--job" in json.loads(r.stdout)["error"]
    assert not (tmp_path / "argv.jsonl").exists()
    assert not list((root / "data" / "runs").glob("2*")) if (root / "data" / "runs").exists() else True
    r = cli(root, env, "run", "score", "--force")
    assert r.returncode == 2 and "--job" in r.stderr


def test_run_job_on_a_locked_job_exits_5_busy(root, home, fake_bin, tmp_path):
    from careeros.runs import locks
    from careeros.runs.store import RunStore

    ids = add_jobs(root, 1)
    env = env_for(root, home, fake_bin, FAKE_CLAUDE_ARGV=str(tmp_path / "argv.jsonl"))
    rs = RunStore(Settings.load(root))
    locks.acquire(rs.job_lock_path(ids[0]), owner="skill:test", pid=os.getpid(), ttl_seconds=600)
    r = cli(root, env, "run", "score", "--job", ids[0], "--json")
    assert r.returncode == 5, r.stdout + r.stderr
    assert "skill:test" in r.stderr and not (tmp_path / "argv.jsonl").exists()
    assert status_of(root, ids[0]) == "found"


def test_run_job_refused_by_the_company_gate_exits_2(root, home, fake_bin, tmp_path):
    ids = add_jobs(root, 1)
    env = env_for(root, home, fake_bin, FAKE_CLAUDE_ARGV=str(tmp_path / "argv.jsonl"))
    assert cli(root, env, "run", "score", "--job", ids[0]).returncode == 0
    p = root / "data" / "jobs" / ids[0] / "posting.json"
    p.write_text(json.dumps({**json.loads(p.read_text()), "closes_at": "2020-01-01"}))  # closed: a gate verdict
    r = cli(root, env, "run", "prepare", "--job", ids[0], "--json")
    assert r.returncode == 2, r.stdout + r.stderr
    body = json.loads(r.stdout)
    assert "closed" in body["reasons"][ids[0]] and "error" in body
    argv = [json.loads(l) for l in (tmp_path / "argv.jsonl").read_text().splitlines()]
    assert len(argv) == 1  # only the score call; prepare-job was never spawned
