"""Scam gate end to end: posting on disk -> `careeros safety check` CLI -> safety.json + Action Item +
status + registry -> scout drops the flagged company next run."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import PY, subprocess_env

import careeros.scout as scout_mod
from careeros.config import Settings
from careeros.models import Posting
from careeros.scout import run_scout
from careeros.store import Store

pytestmark = pytest.mark.integration


def _cli(root: Path, home: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          input=stdin, env=subprocess_env(root, home), timeout=120)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def _save(root: Path, **kw) -> str:
    s = Settings.load(root)
    p = Posting(**{"company": "Acme", "title": "Software Engineer", "ats": "greenhouse",
                   "url": "https://boards.greenhouse.io/acme/jobs/1",
                   "apply_url": "https://boards.greenhouse.io/acme/jobs/1", **kw})
    Store(s).save_posting(p)
    return p.job_id


def test_clean_posting_passes(temp_root: Path, home: Path):
    jid = _save(temp_root, description_text="Build APIs. Questions: jobs@acme.com")
    r = _cli(temp_root, home, "safety", "check", jid)
    assert r.returncode == 0, r.stderr
    out = json.loads((temp_root / "data" / "jobs" / jid / "safety.json").read_text())
    assert out["pass"] is True and out["flags"] == [] and out["auto_submit_allowed"] is True
    assert not (temp_root / "data" / "flagged_registry.yaml").exists()


def test_scam_posting_opens_action_item_sets_review_and_registers(temp_root: Path, home: Path):
    jid = _save(temp_root, company="Quick Hire Co", ats="custom", url="https://quick-hire-now.xyz/job",
                apply_url="https://quick-hire-now.xyz/job",
                description_text="Interview on Telegram. Email quickhire.jobs@gmail.com")
    assert _cli(temp_root, home, "tracker", "init").returncode == 0
    r = _cli(temp_root, home, "safety", "check", jid)
    assert r.returncode == 3, r.stdout + r.stderr   # 3 = hard flag found
    codes = {f["code"] for f in json.loads((temp_root / "data" / "jobs" / jid / "safety.json").read_text())["flags"]}
    assert {"apply_domain", "free_email_contact", "scam_phrase"} <= codes
    assert json.loads((temp_root / "data" / "jobs" / jid / "status.json").read_text())["status"] == "needs_review"
    items = _cli(temp_root, home, "action", "list").stdout
    assert "scam_suspected" in items and "Quick Hire Co" in items
    reg = yaml.safe_load((temp_root / "data" / "flagged_registry.yaml").read_text())["entries"]
    assert reg[0]["company"] == "Quick Hire Co" and reg[0]["domain"] == "quick-hire-now.xyz"
    # rerun: no duplicate Action Item, registry count bumps
    _cli(temp_root, home, "safety", "check", jid)
    assert _cli(temp_root, home, "action", "list").stdout.count("scam_suspected") == 1


def test_fields_command(temp_root: Path, home: Path):
    jid = _save(temp_root)
    ok = _cli(temp_root, home, "safety", "fields", jid, "--labels-json", "-", stdin=json.dumps(["First name", "Email"]))
    assert ok.returncode == 0, ok.stderr
    bad = _cli(temp_root, home, "safety", "fields", jid, "--labels-json", "-",
               stdin=json.dumps(["First name", "Social Security Number"]))
    assert bad.returncode == 3 and "Social Security Number" in bad.stdout
    assert json.loads((temp_root / "data" / "jobs" / jid / "status.json").read_text())["status"] == "needs_review"


def test_manual_flag_then_scout_drops_company(temp_root: Path, home: Path, monkeypatch):
    r = _cli(temp_root, home, "safety", "flag", "Acme", "--reason", "fake recruiter reported")
    assert r.returncode == 0, r.stderr

    class Fake:
        def fetch(self, board):
            return [Posting(company=board["company"], title="Software Engineer", ats="greenhouse",
                            ats_job_id="1", url="https://boards.greenhouse.io/acme/jobs/1")]

    monkeypatch.setattr(scout_mod, "ADAPTERS", {"greenhouse": Fake})
    s = Settings.load(temp_root)
    s.companies["boards"] = [{"company": "Acme", "ats": "greenhouse", "slug": "acme"}]
    summary = run_scout(s, Store(s), log=lambda *_: None)
    assert summary.totals["stored"] == 0 and summary.totals["filtered_flagged"] == 1


def test_verify_command_clears_unverified_flag(temp_root: Path, home: Path):
    jid = _save(temp_root, company="Nimbus Quantum", url="https://boards.greenhouse.io/nimbusq/jobs/1",
                apply_url="https://boards.greenhouse.io/nimbusq/jobs/1")
    assert _cli(temp_root, home, "safety", "check", jid).returncode == 0
    first = json.loads((temp_root / "data" / "jobs" / jid / "safety.json").read_text())
    assert first["auto_submit_allowed"] is False and first["flags"][0]["code"] == "company_unverified"
    r = _cli(temp_root, home, "safety", "verify", "Nimbus Quantum", "--domain", "nimbusq.com",
             "--evidence", "careers page lists role; LinkedIn page 120 employees")
    assert r.returncode == 0, r.stderr
    _cli(temp_root, home, "safety", "check", jid)
    again = json.loads((temp_root / "data" / "jobs" / jid / "safety.json").read_text())
    assert again["flags"] == [] and again["auto_submit_allowed"] is True
