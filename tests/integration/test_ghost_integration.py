"""Ghost jobs end to end: scout runs -> posting_history.json -> stale postings filtered, reposts flagged
by `careeros safety check`, freeze signal recorded by `careeros safety signal`."""
from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from conftest import PY, subprocess_env

import careeros.scout as scout_mod
from careeros.config import Settings
from careeros.models import Posting
from careeros.scout import run_scout
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


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _scout(root: Path, monkeypatch, postings: list[dict]):
    class Fake:
        def fetch(self, board):
            return [Posting(company="Acme", ats="greenhouse", location="New York, NY", **p) for p in postings]

    monkeypatch.setattr(scout_mod, "ADAPTERS", {"greenhouse": Fake})
    s = Settings.load(root)
    s.companies["boards"] = [{"company": "Acme", "ats": "greenhouse", "slug": "acme"}]
    return run_scout(s, Store(s), log=lambda *_: None), Store(s)


def _old(title: str, pid: str, ago: int) -> dict:
    return {"title": title, "ats_job_id": pid, "posted_at": _days_ago(ago), "first_published": _days_ago(ago),
            "last_updated": _days_ago(ago)}


def test_old_posting_skipped_only_without_signs_of_hiring(temp_root: Path, monkeypatch):
    summary, _ = _scout(temp_root, monkeypatch, [_old("Software Engineer", "a", 60), _old("Backend Engineer", "b", 70)])
    assert summary.totals["stored"] == 0 and summary.totals["filtered_ghost"] == 2


def test_old_posting_kept_when_company_is_still_hiring(temp_root: Path, monkeypatch):
    summary, _ = _scout(temp_root, monkeypatch, [_old("Software Engineer", "a", 60), _old("Backend Engineer", "b", 3)])
    assert summary.totals["stored"] == 2 and summary.totals["filtered_ghost"] == 0


def test_repost_is_flagged_by_safety_check(temp_root: Path, home: Path, monkeypatch):
    for i, ago in enumerate((80, 50, 5)):
        summary, store = _scout(temp_root, monkeypatch, [
            {"title": "Software Engineer", "ats_job_id": f"r{i}", "posted_at": _days_ago(ago)}])
    jid = summary.boards[0].stored_ids[0] if summary.boards[0].stored_ids else None
    assert jid, "the fresh repost itself is stored (age comes from the posting, the repost is a soft flag)"
    hist = json.loads((temp_root / "data" / "posting_history.json").read_text())
    assert len(hist) == 1 and len(next(iter(hist.values()))["ats_job_ids"]) == 3
    r = _cli(temp_root, home, "safety", "check", jid)
    assert r.returncode == 0, r.stdout + r.stderr
    codes = {f["code"] for f in json.loads((temp_root / "data" / "jobs" / jid / "safety.json").read_text())["flags"]}
    assert "GHOST_REPOSTED" in codes


def test_freeze_covering_role_is_review_not_skip(temp_root: Path, home: Path):
    s = Settings.load(temp_root)
    p = Posting(company="Acme", title="Software Engineer", ats="greenhouse", ats_job_id="9",
                url="https://boards.greenhouse.io/acme/jobs/9", posted_at=_days_ago(2), departments=["Engineering"])
    Store(s).save_posting(p)
    r = _cli(temp_root, home, "safety", "signal", "Acme", "--kind", "freeze", "--date", _days_ago(20),
             "--scope", "engineering", "--source", "https://news.example/acme-freeze")
    assert r.returncode == 0, r.stderr
    r = _cli(temp_root, home, "safety", "check", p.job_id)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads((temp_root / "data" / "jobs" / p.job_id / "safety.json").read_text())
    freeze = [f for f in out["flags"] if f["code"] == "GHOST_HIRING_FREEZE"]
    assert out["verdict"] == "review" and freeze[0]["evidence"] == ["https://news.example/acme-freeze"]
    assert json.loads((temp_root / "data" / "jobs" / p.job_id / "status.json").read_text())["status"] == "found"
