"""`careeros company slots|gate|active|requeue` and `jobs list --order urgent` end to end: real job dirs
(posting.json, score.json, status.json), the real workbook (DateApplied), the CLI as a subprocess."""
from __future__ import annotations

import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from conftest import PY, subprocess_env

from careeros.company_policy import load_records
from careeros.config import Settings
from careeros.models import Posting
from careeros.store import Store
from careeros.tracker import Tracker

pytestmark = pytest.mark.integration


def _days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def _cli(root: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "careeros.cli", "--root", str(root), *args], capture_output=True, text=True,
                          env=subprocess_env(root, home), timeout=120)


def _job(store: Store, pid: str, title: str, company: str = "Acme", fit: int = 80, category: str = "swe_backend",
         status: str | None = None, text: str = "", decision: str = "prepare", skip_reason: str | None = None) -> str:
    p = Posting(company=company, title=title, ats="greenhouse", ats_job_id=pid, description_text=text,
                first_published=_days(-5), posted_at=_days(-5))
    store.save_posting(p)
    store._write(p.job_id, "score.json", {"job_id": p.job_id, "category": category, "fit": fit, "tier": "C",
                                          "decision": decision, "skip_reason": skip_reason})
    if status:
        store.set_status(p.job_id, status, "test")
    return p.job_id


def _applied(root: Path, store: Store, jid: str, days_ago: int, status: str = "applied") -> None:
    store.set_status(jid, "applied", "test")
    if status != "applied":
        store.set_status(jid, status, "test")
    p = store.load_posting(jid)
    Tracker(settings=Settings.load(root)).upsert_job(
        {"job_id": jid, "company": p.company, "role": p.title, "status": status, "date_applied": _days(-days_ago)})


def test_slots_and_gate_follow_the_cap(temp_root: Path, home: Path):
    store = Store(Settings.load(temp_root))
    a1 = _job(store, "1", "Backend Engineer")
    _applied(temp_root, store, a1, days_ago=10)
    hi = _job(store, "2", "Platform Engineer", fit=92, category="swe_platform")
    lo = _job(store, "3", "Data Engineer", fit=75, category="data_engineering")
    pm = _job(store, "4", "Product Manager", fit=99, category="product_manager")

    r = _cli(temp_root, home, "company", "slots", "Acme", "--json")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert (got["submitted"], got["reserved"], got["used"], got["allowed"], got["remaining"]) == (1, 0, 1, 2, 1)
    by = {c["job_id"]: c for c in got["candidates"]}
    assert by[hi]["allowed"] and by[lo]["reason"] == "company_cap" and by[pm]["reason"] == "not_similar"

    r = _cli(temp_root, home, "company", "gate", hi, "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["allowed"] is True
    r = _cli(temp_root, home, "company", "gate", lo, "--json")
    assert r.returncode == 3, r.stdout + r.stderr
    g = json.loads(r.stdout)
    assert g["allowed"] is False and g["reason"] == "company_cap" and g["slots"]["remaining"] == 1

    r = _cli(temp_root, home, "company", "gate", lo)
    assert r.returncode == 3 and "company_cap" in r.stdout

    r = _cli(temp_root, home, "company", "slots", "Acme")
    assert r.returncode == 0 and "1/2" in r.stdout


def test_gate_unknown_job_and_missing_score(temp_root: Path, home: Path):
    store = Store(Settings.load(temp_root))
    r = _cli(temp_root, home, "company", "gate", "nope00000000", "--json")
    assert r.returncode == 1 and "not found" in r.stderr
    p = Posting(company="Acme", title="SWE", ats="greenhouse", ats_job_id="9")
    store.save_posting(p)
    r = _cli(temp_root, home, "company", "gate", p.job_id, "--json")
    assert r.returncode == 3 and json.loads(r.stdout)["reason"] == "unscored"


def test_cooldown_and_deadline_exception_from_posting_text(temp_root: Path, home: Path):
    store = Store(Settings.load(temp_root))
    old = _job(store, "1", "Backend Engineer")
    _applied(temp_root, store, old, days_ago=120, status="rejected")  # rejected today, applied long ago
    waits = _job(store, "2", "Platform Engineer", fit=90, category="swe_platform")
    due = _job(store, "3", "Data Engineer", fit=70, category="data_engineering",
               text=f"Application deadline: {(date.today() + timedelta(days=5)).strftime('%B %d, %Y')}")

    r = _cli(temp_root, home, "company", "gate", waits, "--json")
    assert r.returncode == 3
    g = json.loads(r.stdout)
    assert g["reason"] == "cooldown" and g["until"] == _days(30)

    r = _cli(temp_root, home, "company", "gate", due, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    g = json.loads(r.stdout)
    assert g["urgent"] is True and g["closes_at"] == _days(5) and _days(5) in g["action_note"]


def test_company_caps_override_from_config(temp_root: Path, home: Path):
    path = temp_root / "config" / "companies.yaml"
    data = yaml.safe_load(path.read_text())
    data["company_caps"] = {"Acme": {"max": 3, "window_days": 30}}
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    r = _cli(temp_root, home, "company", "slots", "Acme", "--json")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert (got["allowed"], got["window_days"]) == (3, 30)

    data["company_caps"] = {"Acme": {"max": "lots"}}
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    r = _cli(temp_root, home, "company", "slots", "Acme")
    assert r.returncode == 1 and "company_caps.Acme.max" in r.stderr


def test_active_note_for_recruiter(temp_root: Path, home: Path):
    store = Store(Settings.load(temp_root))
    i1 = _job(store, "1", "Backend Engineer")
    _applied(temp_root, store, i1, days_ago=20, status="interview")
    a2 = _job(store, "2", "Data Engineer")
    _applied(temp_root, store, a2, days_ago=15)
    _job(store, "3", "Platform Engineer", status="queued")
    _job(store, "4", "Other Co role", company="Other Co", status="queued")

    r = _cli(temp_root, home, "company", "active", "Acme", "--exclude", i1, "--json")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert [(a["title"], a["status"]) for a in got["active"]] == [("Data Engineer", "applied"),
                                                                  ("Platform Engineer", "queued")]
    assert got["note"] == ("Also active at Acme: Data Engineer (applied), Platform Engineer (queued) "
                           "— mention these to the recruiter.")


def test_requeue_releases_deferred_jobs_when_a_slot_opens(temp_root: Path, home: Path):
    store = Store(Settings.load(temp_root))
    q1 = _job(store, "1", "Backend Engineer", status="queued")
    q2 = _job(store, "2", "Platform Engineer", status="queued")
    deferred = _job(store, "3", "Data Engineer", status="skipped", decision="skip", skip_reason="company_cap")
    other = _job(store, "4", "Low fit", status="skipped", decision="skip", skip_reason="below_min_fit")

    r = _cli(temp_root, home, "company", "requeue", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["requeued"] == []  # both slots still reserved

    store.set_status(q2, "withdrawn", "changed my mind")
    r = _cli(temp_root, home, "company", "requeue", "--dry-run", "--json")
    assert [j["job_id"] for j in json.loads(r.stdout)["requeued"]] == [deferred]
    assert store.get_status(deferred) == "skipped"

    r = _cli(temp_root, home, "company", "requeue", "--json")
    assert [j["job_id"] for j in json.loads(r.stdout)["requeued"]] == [deferred]
    assert store.get_status(deferred) == "scored" and store.get_status(other) == "skipped"
    assert Tracker(settings=Settings.load(temp_root)).get_job(deferred)["Status"] == "scored"
    assert store.get_status(q1) == "queued"


def test_jobs_list_order_urgent(temp_root: Path, home: Path):
    store = Store(Settings.load(temp_root))
    plain = _job(store, "1", "Backend Engineer", company="Acme", fit=95, status="queued")
    soon = _job(store, "2", "Data Engineer", company="Beta", fit=60, status="queued",
                text=f"Apply by {(date.today() + timedelta(days=4)).strftime('%B %d, %Y')}.")
    soon2 = _job(store, "3", "Platform Engineer", company="Beta", fit=65, status="queued",
                 text=f"Apply by {(date.today() + timedelta(days=6)).strftime('%B %d, %Y')}.")
    r = _cli(temp_root, home, "jobs", "list", "--status", "queued", "--order", "urgent", "--json")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert [j["job_id"] for j in got] == [soon, soon2, plain]
    assert got[0]["urgent"] is True and got[0]["closes_at"] == _days(4) and got[2]["urgent"] is False
    r = _cli(temp_root, home, "jobs", "list", "--order", "urgent")
    assert r.returncode == 0 and "URGENT" in r.stdout


def test_scout_stores_closes_at_in_posting_json(temp_root: Path):
    s = Settings.load(temp_root)
    store = Store(s)
    p = Posting(company="Acme", title="SWE", ats="greenhouse", ats_job_id="7", closes_at="2026-10-16")
    store.save_posting(p)
    assert json.loads((store.job_dir(p.job_id) / "posting.json").read_text())["closes_at"] == "2026-10-16"


def test_load_records_reads_store_and_tracker(temp_root: Path):
    s = Settings.load(temp_root)
    store = Store(s)
    jid = _job(store, "1", "Backend Engineer")
    _applied(temp_root, store, jid, days_ago=12, status="rejected")
    Tracker(settings=s).upsert_job({"job_id": "legacy0001", "company": "Acme", "role": "Old", "status": "applied",
                                    "date_applied": _days(-3)})
    recs = {r.job_id: r for r in load_records(s)}
    assert recs[jid].date_applied == date.today() - timedelta(days=12)
    assert recs[jid].rejected_at == date.today() and recs[jid].category == "swe_backend"
    assert recs["legacy0001"].status == "applied" and recs["legacy0001"].company == "Acme"


def test_gate_deferral_recorded_only_in_status_note_still_competes(temp_root: Path, home: Path):
    # prepare-job Step 1b skips via `careeros job status <id> skipped --note "<reason>: <detail>"` and leaves
    # score.json at decision prepare / skip_reason null; a ghost skip leaves the same score.json.
    s = Settings.load(temp_root)
    store = Store(s)
    deferred = _job(store, "1", "Backend Engineer", fit=95)
    ghost = _job(store, "2", "Platform Engineer", fit=96)
    r = _cli(temp_root, home, "job", "status", deferred, "skipped", "--note", "company_cap: 2/2 slots used at Acme")
    assert r.returncode == 0, r.stderr
    r = _cli(temp_root, home, "job", "status", ghost, "skipped", "--note", "ghost job: GHOST_STALE_NO_ACTIVITY")
    assert r.returncode == 0, r.stderr
    recs = {r.job_id: r for r in load_records(s)}
    assert recs[deferred].skip_reason == "company_cap"
    assert recs[ghost].skip_reason is None

    r = _cli(temp_root, home, "company", "requeue", "--dry-run", "--json")
    assert [j["job_id"] for j in json.loads(r.stdout)["requeued"]] == [deferred]


def test_batch_scores_all_then_gates_so_higher_fit_wins(temp_root: Path, home: Path):
    # One slot left at Acme. Phase 1 (score-job on every found job) meets the lower-fit job first: its gate
    # passes because the other job has no score yet. Phase 2 (gate + prepare in --order urgent order) must
    # still give the slot to the higher-fit job.
    store = Store(Settings.load(temp_root))
    a1 = _job(store, "1", "Backend Engineer")
    _applied(temp_root, store, a1, days_ago=10)
    lo = _job(store, "2", "Data Engineer", fit=72, category="data_engineering")
    hi_p = Posting(company="Acme", title="Platform Engineer", ats="greenhouse", ats_job_id="3",
                   first_published=_days(-5), posted_at=_days(-5))
    store.save_posting(hi_p)  # found, not scored yet
    hi = hi_p.job_id

    r = _cli(temp_root, home, "company", "gate", lo, "--json")  # phase 1, lower-fit job scored first
    assert r.returncode == 0, r.stdout
    store._write(hi, "score.json", {"job_id": hi, "category": "swe_platform", "fit": 93, "tier": "C",
                                    "decision": "prepare", "skip_reason": None})
    requeued = _job(store, "4", "Backend Engineer II", fit=60, status="scored")  # found + scored both listed

    r = _cli(temp_root, home, "jobs", "list", "--status", "found", "--status", "scored", "--order", "urgent",
             "--json")
    assert r.returncode == 0, r.stderr
    order = [j["job_id"] for j in json.loads(r.stdout)]
    assert order == [hi, lo, requeued]

    outcome = {}
    for jid in order:  # phase 2: re-run the gate right before each prepare
        r = _cli(temp_root, home, "company", "gate", jid, "--json")
        g = json.loads(r.stdout)
        outcome[jid] = g["reason"]
        if r.returncode == 0:
            store.set_status(jid, "queued", "prepared")  # prepare-job reserves the slot
    assert outcome == {hi: "ok", lo: "company_cap", requeued: "company_cap"}


def test_retention_stubbed_deferred_job_is_not_requeued(temp_root: Path, home: Path):
    """`careeros prune --yes` stubs a gate-deferred posting untouched for > 90 days; it then neither holds a
    slot nor comes back through `company requeue` (prepare-job would refuse the pruned posting)."""
    s = Settings.load(temp_root)
    store = Store(s)
    _applied(temp_root, store, _job(store, "1", "Backend Engineer"), days_ago=10)
    old = _job(store, "2", "Platform Engineer", fit=95, status="skipped", text="Build things. " * 100,
               decision="skip", skip_reason="company_cap")
    st = store._read(old, "status.json")
    for h in st["history"]:
        h["at"] = _days(-120) + "T12:00:00+00:00"
    st["updated_at"] = st["history"][-1]["at"]
    store._write(old, "status.json", st)
    fresh = _job(store, "3", "Data Engineer", fit=85, status="scored")

    r = _cli(temp_root, home, "prune", "--yes", "--json")
    assert r.returncode == 0, r.stderr
    assert [i["job_id"] for i in json.loads(r.stdout)["items"]] == [old]
    assert store._read(old, "posting.json")["pruned"] is True
    assert {r.job_id: r for r in load_records(s)}[old].pruned is True

    r = _cli(temp_root, home, "company", "requeue", "--json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["requeued"] == [] and out["still_deferred"] == []
    assert store.get_status(old) == "skipped"
    r = _cli(temp_root, home, "company", "gate", fresh, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
