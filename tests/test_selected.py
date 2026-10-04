"""REQ-104: the per-job `selected` flag (flags.json). New postings start unselected, legacy jobs count as
selected, and only selected jobs are prepared or applied (scoring runs on all)."""
from __future__ import annotations

import json

import pytest

from careeros.models import Posting
from careeros.runs.runner import eligibility
from careeros.store import Store

pytestmark = pytest.mark.unit


def _posting(n: int) -> Posting:
    return Posting(company="Acme", title=f"Engineer {n}", ats="greenhouse", ats_job_id=str(n),
                   description_text="python apis")


def test_new_posting_is_unselected_and_resave_keeps_choice(settings):
    store = Store(settings)
    p = _posting(1)
    store.save_posting(p)
    assert json.loads((store.job_dir(p.job_id) / "flags.json").read_text())["selected"] is False
    assert store.is_selected(p.job_id) is False
    store.set_selected([p.job_id], True)
    store.save_posting(p)  # a re-scout never unticks
    assert store.is_selected(p.job_id) is True


def test_legacy_job_without_flag_is_selected(settings):
    store = Store(settings)
    p = _posting(2)
    store.save_posting(p)
    (store.job_dir(p.job_id) / "flags.json").unlink()
    assert store.is_selected(p.job_id) is True
    (store.job_dir(p.job_id) / "flags.json").write_text(json.dumps({"injection_suspected": False}))
    assert store.is_selected(p.job_id) is True


def test_set_selected_keeps_other_flags(settings):
    store = Store(settings)
    p = _posting(3)
    store.save_posting(p)
    (store.job_dir(p.job_id) / "flags.json").write_text(json.dumps({"selected": False, "injection_reasons": ["x"]}))
    store.set_selected([p.job_id], True)
    assert store.load_flags(p.job_id) == {"selected": True, "injection_reasons": ["x"]}


@pytest.mark.parametrize("kind", ["prepare", "apply"])
def test_eligibility_requires_selected(kind):
    score = {"decision": "prepare", "tier": "C"}
    status = "scored" if kind == "prepare" else "queued"
    assert eligibility(kind, status, True, score, kind == "apply", selected=False) == "not selected"
    assert eligibility(kind, status, True, score, kind == "apply") is None
    assert eligibility("score", "found", False, {}, False, selected=False) is None


def test_job_unticked_mid_run_is_not_prepared(settings):
    """A multi-job run re-checks `selected` before each job: untick job 2 while job 1 runs -> job 2 is skipped."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from test_runs_prepare import Fake, add_job, batch

    store = Store(settings)
    first, second = add_job(store, 1, company="A", fit=95), add_job(store, 2, company="B", fit=70)

    class Untick(Fake):
        def __call__(self, cmd, cwd, env, timeout_s, stream_path):
            Store(self.s).set_selected([second], False)
            return super().__call__(cmd, cwd, env, timeout_s, stream_path)

    fake = Untick(settings)
    rec = batch(settings, "prepare", fake)
    assert fake.calls == [first]
    assert store.get_status(second) == "scored" and rec["counters"]["gated"] == 1


def test_concurrent_flag_writers_keep_each_others_keys(settings, monkeypatch):
    """flags.json read-modify-writes are serialised: a select racing a clear keeps both changes."""
    import threading

    store = Store(settings)
    p = _posting(4)
    store.save_posting(p)
    orig, inside, gate = Store.load_flags, threading.Event(), threading.Event()

    def slow(self, job_id):
        flags = orig(self, job_id)
        if threading.current_thread().name == "A":
            inside.set()
            gate.wait(5)
        return flags

    monkeypatch.setattr(Store, "load_flags", slow)
    a = threading.Thread(target=store.set_selected, args=([p.job_id], True), name="A")
    a.start()
    assert inside.wait(5)
    b = threading.Thread(target=store.clear_injection, args=(p.job_id,))
    b.start()
    b.join(0.3)
    gate.set()
    a.join(5)
    b.join(5)
    flags = orig(store, p.job_id)
    assert flags["selected"] is True and flags["injection_cleared_at"]
