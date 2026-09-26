"""`careeros storage|advise|advise apply` and the prune snapshot, end to end on a temp root (no network)."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from conftest import PY, subprocess_env

pytestmark = pytest.mark.integration

MB = 1024 * 1024


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def cli(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=subprocess_env(root, home), timeout=120, cwd=root)


def seed_snapshots(root: Path, n_days: int = 21, start_mb: int = 100, end_mb: int = 900) -> None:
    runs = root / "data" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    lines = []
    for i, day in enumerate((n_days, n_days // 2, 0)):
        total = int((start_mb + (end_mb - start_mb) * i / 2) * MB)
        cats = {"postings": int(total * 0.8), "resumes_pdfs": 0, "screenshots": 0, "run_logs": 0, "tracker": 0,
                "other": total - int(total * 0.8)}
        lines.append(json.dumps({"at": (now - timedelta(days=day)).isoformat(), "trigger": "prune",
                                 "pruned_bytes": 0, "bytes": cats, "total": total,
                                 "disk": {"total": 10**12, "free": 5 * 10**11, "free_pct": 50.0}}))
    (runs / "storage.jsonl").write_text("\n".join(lines) + "\n")


def test_storage_breakdown_and_snapshot(temp_root, home):
    (temp_root / "data" / "jobs" / "j1").mkdir(parents=True)
    (temp_root / "data" / "jobs" / "j1" / "posting.json").write_text("x" * 500)
    r = cli(temp_root, home, "storage", "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["bytes"]["postings"] == 500 and data["disk"]["free"] > 0
    assert not (temp_root / "data" / "runs" / "storage.jsonl").exists()
    assert cli(temp_root, home, "storage", "--snapshot").returncode == 0
    assert len((temp_root / "data" / "runs" / "storage.jsonl").read_text().splitlines()) == 1


def test_prune_yes_appends_a_snapshot_dry_run_does_not(temp_root, home):
    assert cli(temp_root, home, "prune").returncode == 0
    assert not (temp_root / "data" / "runs" / "storage.jsonl").exists()
    assert cli(temp_root, home, "prune", "--yes").returncode == 0
    (line,) = (temp_root / "data" / "runs" / "storage.jsonl").read_text().splitlines()
    assert json.loads(line)["trigger"] == "prune"


def test_advise_waits_for_enough_history(temp_root, home):
    seed_snapshots(temp_root, n_days=5)
    out = json.loads(cli(temp_root, home, "advise", "--json").stdout)
    assert out["storage"]["ready"] is False and out["recommendations"] == []
    assert "collecting" in cli(temp_root, home, "advise").stdout


def test_advise_then_apply_changes_only_that_key_and_keeps_comments(temp_root, home):
    cfg = temp_root / "config" / "pipeline.yaml"
    from conftest import EXAMPLE_REPO
    cfg.write_text((EXAMPLE_REPO / "config" / "pipeline.yaml").read_text())  # the commented example
    seed_snapshots(temp_root)
    before = cfg.read_text()
    out = json.loads(cli(temp_root, home, "advise", "--json").stdout)
    ids = [r["id"] for r in out["recommendations"]]
    assert "tighten-unprepared_posting_days" in ids
    assert cfg.read_text() == before  # advising never writes

    r = cli(temp_root, home, "advise", "apply", "tighten-unprepared_posting_days")
    assert r.returncode == 0, r.stderr
    after = cfg.read_text()
    assert yaml.safe_load(after)["retention"]["unprepared_posting_days"] == 60
    diff = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    assert len(diff) == 1 and "unprepared_posting_days" in diff[0][1]
    assert "(Recommended)" in after and len(before.splitlines()) == len(after.splitlines())
    again = cli(temp_root, home, "advise", "apply", "tighten-unprepared_posting_days")  # recomputed from 60
    assert again.returncode == 0 and yaml.safe_load(cfg.read_text())["retention"]["unprepared_posting_days"] == 40


def test_advise_apply_unknown_or_advice_only(temp_root, home):
    seed_snapshots(temp_root)
    assert cli(temp_root, home, "advise", "apply", "no-such-id").returncode == 1
