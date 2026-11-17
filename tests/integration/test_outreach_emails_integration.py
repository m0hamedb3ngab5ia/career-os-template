"""`careeros outreach targets|emails` as subprocesses on a temp root, no provider keys (no network): targets JSON,
contacts.json written with pattern guesses + manual links, credits line in log.md. Provider HTTP is unit-tested with
fakes in tests/test_email_guess.py."""
from __future__ import annotations

import json
import subprocess

import pytest
from conftest import PY, subprocess_env

from careeros.config import Settings
from careeros.models import Posting
from careeros.store import Store

pytestmark = pytest.mark.integration


def test_outreach_targets_and_emails(temp_root, tmp_path):
    store = Store(Settings.load(temp_root))
    p = Posting(company="Nimbus", title="Software Engineer", ats="greenhouse", ats_job_id="1",
                location="Austin, TX", description_text="x", url="https://careers.nimbus.com/1")
    store.save_posting(p)
    store.set_status(p.job_id, "applied")
    d = store.job_dir(p.job_id)
    (d / "score.json").write_text(json.dumps({"job_id": p.job_id, "category": "swe", "fit": 90, "tier": "B",
                                              "decision": "prepare"}))
    (d / "contacts.json").write_text(json.dumps({"job_id": p.job_id, "company": "Nimbus",
                                                 "contacts": [{"name": "Sam Lee", "role": "recruiter"}]}))
    home = tmp_path / "home"
    home.mkdir()

    def cli(*a):
        return subprocess.run([PY, "-m", "careeros.cli", "--root", str(temp_root), "outreach", *a],
                              capture_output=True, text=True, env=subprocess_env(temp_root, home), timeout=120)

    r = cli("targets", "--json")
    assert r.returncode == 0, r.stderr
    assert [j["job_id"] for j in json.loads(r.stdout)] == [p.job_id]
    r = cli("emails", p.job_id)
    assert r.returncode == 0, r.stderr
    out = json.loads((d / "contacts.json").read_text())
    assert out["domain"] == "nimbus.com" and out["contacts"][0]["email_candidates"][0] == "sam.lee@nimbus.com"
    assert out["search_urls"]["apollo_recruiter"].startswith("https://app.apollo.io/")
    assert "outreach emails: no provider keys, 0 credits" in (d / "log.md").read_text()


def test_emails_keeps_researched_domain_over_a_name_guess(temp_root, tmp_path):
    """An ATS posting URL gives no domain; the domain find-contacts researched (shophammock.com) beats the
    `<name>.com` guess (hammock.com, a different company)."""
    store = Store(Settings.load(temp_root))
    p = Posting(company="Hammock", title="Software Engineer", ats="ashby", ats_job_id="2",
                location="Austin, TX", description_text="x", url="https://jobs.ashbyhq.com/hammock/2")
    store.save_posting(p)
    d = store.job_dir(p.job_id)
    (d / "contacts.json").write_text(json.dumps({"job_id": p.job_id, "company": "Hammock", "domain": "shophammock.com",
                                                 "domain_confidence": "medium",
                                                 "contacts": [{"name": "Sam Lee", "role": "recruiter"}]}))
    home = tmp_path / "home"
    home.mkdir()
    r = subprocess.run([PY, "-m", "careeros.cli", "--root", str(temp_root), "outreach", "emails", p.job_id],
                       capture_output=True, text=True, env=subprocess_env(temp_root, home), timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads((d / "contacts.json").read_text())
    assert out["domain"] == "shophammock.com" and out["domain_confidence"] == "medium"
    assert out["contacts"][0]["email_candidates"][0] == "sam.lee@shophammock.com"
