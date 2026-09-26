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


def _safety(root: Path, jid: str) -> dict:
    return json.loads((root / "data" / "jobs" / jid / "safety.json").read_text())


def test_clean_posting_passes(temp_root: Path, home: Path):
    jid = _save(temp_root, description_text="Build APIs. Questions: jobs@acme.com")
    r = _cli(temp_root, home, "safety", "check", jid)
    assert r.returncode == 0, r.stderr
    out = _safety(temp_root, jid)
    assert out["verdict"] == "pass" and out["flags"] == [] and out["auto_submit_allowed"] is True
    assert len(out["runs"]) == 1 and out["runs"][0]["verdict"] == "pass"
    assert not (temp_root / "data" / "flagged_registry.yaml").exists()


def test_block_opens_action_item_sets_review_and_registers_with_evidence(temp_root: Path, home: Path):
    jid = _save(temp_root, company="Quick Hire Co", ats="custom", url="https://quick-hire-now.xyz/job",
                apply_url="https://quick-hire-now.xyz/job",
                description_text="A $40 training fee is required. Email quickhire.jobs@gmail.com")
    assert _cli(temp_root, home, "tracker", "init").returncode == 0
    r = _cli(temp_root, home, "safety", "check", jid)
    assert r.returncode == 3, r.stdout + r.stderr   # 3 = block
    out = _safety(temp_root, jid)
    codes = {f["code"] for f in out["flags"]}
    assert out["verdict"] == "block"
    assert {"SCAM_PAYMENT_REQUEST", "SCAM_FREE_EMAIL_RECRUITER", "SCAM_APPLY_DOMAIN_UNRECOGNIZED"} <= codes
    assert all(f["at"] for f in out["flags"])
    assert json.loads((temp_root / "data" / "jobs" / jid / "status.json").read_text())["status"] == "needs_review"
    items = _cli(temp_root, home, "action", "list").stdout
    assert "scam_suspected" in items and "SCAM_PAYMENT_REQUEST" in items
    reg = yaml.safe_load((temp_root / "data" / "flagged_registry.yaml").read_text())["entries"]
    assert reg[0]["company"] == "Quick Hire Co" and reg[0]["domain"] == "quick-hire-now.xyz"
    assert reg[0]["confidence"] == "high" and reg[0]["state"] == "active" and reg[0]["expires_at"]
    assert "https://quick-hire-now.xyz/job" in reg[0]["evidence"]
    # rerun: no duplicate Action Item, decision trail grows
    _cli(temp_root, home, "safety", "check", jid)
    assert _cli(temp_root, home, "action", "list").stdout.count("scam_suspected") == 1
    assert len(_safety(temp_root, jid)["runs"]) == 2


def test_review_turns_auto_submit_off_without_registry(temp_root: Path, home: Path):
    jid = _save(temp_root, description_text="Questions? Email acme.founder@gmail.com")
    r = _cli(temp_root, home, "safety", "check", jid)
    assert r.returncode == 0, r.stdout + r.stderr
    out = _safety(temp_root, jid)
    assert out["verdict"] == "review" and out["auto_submit_allowed"] is False
    assert "SCAM_FREE_EMAIL_RECRUITER" in out["auto_submit_reason"]
    assert not (temp_root / "data" / "flagged_registry.yaml").exists()
    assert json.loads((temp_root / "data" / "jobs" / jid / "status.json").read_text())["status"] == "found"


def test_fields_command(temp_root: Path, home: Path):
    jid = _save(temp_root)
    ok = _cli(temp_root, home, "safety", "fields", jid, "--labels-json", "-",
              stdin=json.dumps(["First name", "Are you authorized to work in the US?"]))
    assert ok.returncode == 0, ok.stderr
    bad = _cli(temp_root, home, "safety", "fields", jid, "--labels-json", "-", "--page-url", "https://x.xyz/f",
               stdin=json.dumps(["First name", "Social Security Number"]))
    assert bad.returncode == 3 and "FIELD_SENSITIVE_PRE_OFFER" in bad.stdout
    assert json.loads((temp_root / "data" / "jobs" / jid / "status.json").read_text())["status"] == "needs_review"


def _scout_acme(temp_root: Path, monkeypatch):
    class Fake:
        def fetch(self, board):
            return [Posting(company=board["company"], title="Software Engineer", ats="greenhouse",
                            ats_job_id="1", url="https://boards.greenhouse.io/acme/jobs/1")]

    monkeypatch.setattr(scout_mod, "ADAPTERS", {"greenhouse": Fake})
    (temp_root / "data" / "seen.json").unlink(missing_ok=True)
    s = Settings.load(temp_root)
    s.companies["boards"] = [{"company": "Acme", "ats": "greenhouse", "slug": "acme"}]
    return run_scout(s, Store(s), log=lambda *_: None).totals


def test_registry_confidence_expiry_and_clear_drive_scout(temp_root: Path, home: Path, monkeypatch):
    assert _cli(temp_root, home, "safety", "flag", "Acme", "--reason", "fake recruiter",
                "--confidence", "medium").returncode == 0
    assert _scout_acme(temp_root, monkeypatch)["filtered_flagged"] == 0     # medium: review later, not dropped
    assert _cli(temp_root, home, "safety", "flag", "Acme", "--reason", "asked for gift cards",
                "--confidence", "high", "--evidence", "https://reddit.example/post").returncode == 0
    assert _scout_acme(temp_root, monkeypatch)["filtered_flagged"] == 1
    r = _cli(temp_root, home, "safety", "clear", "Acme", "--note", "real company, recruiter confirmed")
    assert r.returncode == 0, r.stderr
    assert _scout_acme(temp_root, monkeypatch)["filtered_flagged"] == 0


def test_verify_sets_company_risk(temp_root: Path, home: Path):
    jid = _save(temp_root, company="Nimbus Quantum", url="https://boards.greenhouse.io/nimbusq/jobs/1",
                apply_url="https://boards.greenhouse.io/nimbusq/jobs/1")
    assert _cli(temp_root, home, "safety", "check", jid).returncode == 0
    first = _safety(temp_root, jid)
    assert first["verdict"] == "review" and first["flags"][0]["code"] == "COMPANY_NOT_YET_CHECKED"
    one = _cli(temp_root, home, "safety", "verify", "Nimbus Quantum", "--risk", "low", "--signal", "website")
    assert one.returncode == 2 and "two" in one.stderr.lower()
    r = _cli(temp_root, home, "safety", "verify", "Nimbus Quantum", "--risk", "low", "--domain", "nimbusq.com",
             "--signal", "official site describes product", "--signal", "careers page lists role",
             "--evidence", "https://nimbusq.com/careers")
    assert r.returncode == 0, r.stderr
    _cli(temp_root, home, "safety", "check", jid)
    again = _safety(temp_root, jid)
    assert again["verdict"] == "pass" and again["auto_submit_allowed"] is True
