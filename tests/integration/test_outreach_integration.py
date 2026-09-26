"""Outreach gate end to end: contacts.json on disk -> `careeros outreach mark` records what the candidate saw on
LinkedIn -> `careeros outreach check` reports which contacts must be tailored by hand."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
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


@pytest.fixture
def job(temp_root: Path) -> str:
    s = Settings.load(temp_root)
    p = Posting(company="Acme", title="Software Engineer", ats="greenhouse",
                url="https://boards.greenhouse.io/acme/jobs/1")
    store = Store(s)
    store.save_posting(p)
    (store.job_dir(p.job_id) / "contacts.json").write_text(json.dumps({
        "job_id": p.job_id, "company": "Acme",
        "contacts": [{"name": "Jane Doe", "role": "recruiter"}, {"name": "Sam Lee", "role": "team_lead"}],
    }))
    return p.job_id


def test_check_before_and_after_mark(temp_root: Path, home: Path, job: str):
    r = _cli(temp_root, home, "outreach", "check", job)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["manual"] == 0 and [c["manual"] for c in out["contacts"]] == [False, False]

    assert _cli(temp_root, home, "outreach", "mark", job, "Jane Doe", "--degree", "1").returncode == 0
    r = _cli(temp_root, home, "outreach", "mark", job, "Sam Lee", "--degree", "2", "--mutuals", "3")
    assert r.returncode == 0, r.stderr

    out = json.loads(_cli(temp_root, home, "outreach", "check", job).stdout)
    assert out["manual"] == 2
    assert [c["reason"] for c in out["contacts"]] == ["LINKEDIN_CONNECTED", "LINKEDIN_MUTUALS"]
    saved = json.loads((temp_root / "data" / "jobs" / job / "contacts.json").read_text())
    assert saved["contacts"][1]["mutuals"] == 3


def test_config_switch_off(temp_root: Path, home: Path, job: str):
    cfg = temp_root / "config" / "pipeline.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["outreach"] = {"manual_if_connected": True, "manual_if_mutuals": False}
    cfg.write_text(yaml.safe_dump(data, sort_keys=False))
    _cli(temp_root, home, "outreach", "mark", job, "Sam Lee", "--mutuals", "5")
    out = json.loads(_cli(temp_root, home, "outreach", "check", job).stdout)
    assert out["manual"] == 0


def test_errors(temp_root: Path, home: Path, job: str):
    r = _cli(temp_root, home, "outreach", "mark", job, "Nobody", "--degree", "1")
    assert r.returncode == 1 and "Nobody" in r.stderr
    r = _cli(temp_root, home, "outreach", "check", "000000000000")
    assert r.returncode == 1 and "contacts.json" in r.stderr
    r = _cli(temp_root, home, "outreach", "mark", job, "Jane Doe")
    assert r.returncode == 2
