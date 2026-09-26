"""`careeros prune` end to end on a temp repo: dry run by default, deletes only with --yes."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import PY, subprocess_env

from careeros.config import Settings
from careeros.models import Posting
from careeros.store import Store

pytestmark = pytest.mark.integration


def _cli(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=subprocess_env(root, home), timeout=120)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def _job(root: Path, status: str, days_ago: int, shots=()) -> Path:
    s = Settings.load(root)
    store = Store(s)
    p = Posting(company="Acme", title=f"Engineer {status}", ats="greenhouse", ats_job_id=f"{status}{days_ago}",
                url=f"https://boards.greenhouse.io/acme/jobs/{status}{days_ago}", description_text="word " * 2000)
    store.save_posting(p)
    d = store.job_dir(p.job_id)
    at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    (d / "status.json").write_text(json.dumps({"status": status, "updated_at": at,
                                               "history": [{"status": status, "at": at, "note": None}]}))
    for name in shots:
        (d / "screenshots").mkdir(exist_ok=True)
        (d / "screenshots" / name).write_bytes(b"x" * 500)
    return d


def test_prune_dry_run_changes_nothing_then_yes_deletes(temp_root, home):
    old = _job(temp_root, "rejected", 45, shots=["01_form.png", "05_confirmation.png"])
    stale = _job(temp_root, "found", 120)
    active = _job(temp_root, "interview", 400, shots=["01_form.png"])
    posting_before = (stale / "posting.json").read_text()

    r = _cli(temp_root, home, "prune")
    assert r.returncode == 0, r.stderr
    assert "dry run" in r.stdout.lower()
    assert "01_form.png" in r.stdout or "1 screenshot" in r.stdout
    assert (old / "screenshots" / "01_form.png").exists()
    assert (stale / "posting.json").read_text() == posting_before

    rj = _cli(temp_root, home, "prune", "--json")
    data = json.loads(rj.stdout)
    assert data["dry_run"] is True
    assert {i["action"] for i in data["items"]} == {"delete_screenshots", "stub_posting"}
    assert data["summary"]["jobs"] == 2

    r2 = _cli(temp_root, home, "prune", "--yes")
    assert r2.returncode == 0, r2.stderr
    assert not (old / "screenshots" / "01_form.png").exists()
    assert (old / "screenshots" / "05_confirmation.png").exists()
    assert json.loads((stale / "posting.json").read_text())["pruned"] is True
    assert (active / "screenshots" / "01_form.png").exists()

    r3 = _cli(temp_root, home, "prune", "--json")
    assert json.loads(r3.stdout)["items"] == []


def test_prune_dry_run_flag_wins_over_yes(temp_root, home):
    d = _job(temp_root, "withdrawn", 90, shots=["01_form.png"])
    r = _cli(temp_root, home, "prune", "--dry-run", "--yes")
    assert r.returncode == 0, r.stderr
    assert (d / "screenshots" / "01_form.png").exists()


def test_prune_bad_config_exits_1(temp_root, home):
    import yaml
    cfg = temp_root / "config" / "pipeline.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["retention"] = {"unprepared_posting_days": "soon"}
    cfg.write_text(yaml.safe_dump(data))
    r = _cli(temp_root, home, "prune")
    assert r.returncode == 1
    assert "retention" in r.stderr


def test_prune_bad_keep_confirmation_exits_1(temp_root, home):
    import yaml
    cfg = temp_root / "config" / "pipeline.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["retention"] = {"keep_confirmation_screenshot": "no"}
    cfg.write_text(yaml.safe_dump(data))
    r = _cli(temp_root, home, "prune")
    assert r.returncode == 1
    assert "keep_confirmation_screenshot must be true/false" in r.stderr


def test_pruned_found_posting_leaves_queue_and_safety_check_refuses(temp_root, home):
    stale = _job(temp_root, "found", 120)
    jid = stale.name
    r = _cli(temp_root, home, "prune", "--yes")
    assert r.returncode == 0, r.stderr
    assert json.loads((stale / "status.json").read_text())["status"] == "skipped"
    listed = _cli(temp_root, home, "jobs", "list", "--status", "found")
    assert listed.returncode == 0, listed.stderr
    assert jid not in listed.stdout

    chk = _cli(temp_root, home, "safety", "check", jid)
    assert chk.returncode != 0
    assert "pruned" in chk.stderr
    assert not (stale / "safety.json").exists()
