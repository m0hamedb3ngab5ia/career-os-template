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
