"""Batch model + preview (slice 7): per-job eligibility for a stop point, ranking, the hard rules (Tier A never
auto-submitted, LinkedIn never automated, apply one job per run), and the batch file."""
from __future__ import annotations

import json

import pytest
from test_runs_runner import NOW, add_job

from careeros.runs import batches
from careeros.store import Store

pytestmark = pytest.mark.unit


def put(store: Store, jid: str, status: str, tier: str | None = None, qa: bool = False, decision="prepare",
        fit: int = 80, safety: str = "pass") -> str:
    store.set_status(jid, status)
    jd = store.job_dir(jid)
    (jd / "score.json").write_text(json.dumps({"job_id": jid, "decision": decision, "fit": fit, "tier": tier}))
    (jd / "safety.json").write_text(json.dumps({"verdict": safety}))
    if qa:
        (jd / "prepare.json").write_text(json.dumps({"qa_pass": True}))
    return jid


def allow_submit(settings) -> None:
    settings.pipeline = {**settings.pipeline, "runs": {**(settings.pipeline.get("runs") or {}),
                                                       "auto_submit": {"enabled": True, "allow": ["tier_b"]}}}


def by_id(rows):
    return {r["job_id"]: r for r in rows}


def test_selection_picks_first_stage_up_to_stop_and_ranks(settings):
    s = Store(settings)
    fresh = add_job(s, 1, hours_old=2)
    old = add_job(s, 2, hours_old=200)
    scored = put(s, add_job(s, 3), "scored")
    applied = put(s, add_job(s, 4), "applied")
    out = batches.preview(settings, [old, fresh, scored, applied, "nope"], "prepare", now=NOW)
    sel = by_id(out["selected"])
    assert sel[fresh]["stage"] == "score" and sel[fresh]["stages"] == ["score", "prepare"]
    assert sel[scored]["stages"] == ["prepare"]
    assert [r["job_id"] for r in out["selected"]].index(fresh) < [r["job_id"] for r in out["selected"]].index(old)
    ex = by_id(out["excluded"])
    assert ex["nope"]["reason"] == "not found"
    assert ex[applied]["reason"] == "status applied"
    assert out["kind"] == "prepare" and out["stop_at"] == "prepare"


def test_eligibility_depends_on_stop_point(settings):
    s = Store(settings)
    ready = put(s, add_job(s, 1), "prepared", tier="B", qa=True)
    unqa = put(s, add_job(s, 2), "prepared", tier="B")
    assert by_id(batches.preview(settings, [ready], "fill", now=NOW)["selected"])[ready]["stages"] == ["apply"]
    assert batches.preview(settings, [ready], "prepare", now=NOW)["selected"] == []
    ex = by_id(batches.preview(settings, [unqa], "fill", now=NOW)["excluded"])
    assert ex[unqa]["reason"] == "qa not passed"


def test_tier_a_is_never_submitted(settings):
    allow_submit(settings)
    s = Store(settings)
    a = put(s, add_job(s, 1, company="Acme"), "needs_review", tier="A", qa=True)
    b = put(s, add_job(s, 2, company="Other"), "prepared", tier="B", qa=True)
    out = batches.preview(settings, [a, b], "submit", now=NOW)
    sel = by_id(out["selected"])
    assert sel[a]["auto_submit"] is False and "tier_a" in sel[a]["submit_reason"]
    assert sel[b]["auto_submit"] is True
    runs = {r["job_ids"][0]: r for r in batches.job_runs(out)}
    assert runs[a]["auto_submit"] is False and runs[b]["auto_submit"] is True


def test_submit_verdict_only_for_jobs_already_at_apply(settings):
    allow_submit(settings)
    s = Store(settings)
    found = add_job(s, 1)
    out = batches.preview(settings, [found], "submit", now=NOW)
    r = out["selected"][0]
    assert r["stage"] == "score" and r["auto_submit"] is False and r["submit_reason"] == "decided at apply"


def test_fill_never_submits_even_when_allowed(settings):
    allow_submit(settings)
    s = Store(settings)
    b = put(s, add_job(s, 1), "prepared", tier="B", qa=True)
    out = batches.preview(settings, [b], "fill", now=NOW)
    assert out["selected"][0]["auto_submit"] is False


@pytest.mark.parametrize("extra", [{"url": "https://www.linkedin.com/jobs/view/1"},
                                   {"apply_url": "https://www.linkedin.com/jobs/view/1"}])
def test_linkedin_excluded_from_fill_and_submit(settings, extra):
    s = Store(settings)
    li = put(s, add_job(s, 1, **extra), "prepared", tier="B", qa=True)
    for stop in ("fill", "submit"):
        out = batches.preview(settings, [li], stop, now=NOW)
        assert out["selected"] == [] and "LinkedIn" in out["excluded"][0]["reason"]
    found = add_job(s, 2, **extra)
    assert batches.preview(settings, [found], "score", now=NOW)["selected"][0]["job_id"] == found


def test_apply_is_one_job_per_run(settings):
    s = Store(settings)
    ids = [put(s, add_job(s, n, company=f"C{n}"), "prepared", tier="B", qa=True) for n in range(3)]
    found = add_job(s, 9)
    runs = batches.job_runs(batches.preview(settings, [*ids, found], "fill", now=NOW))
    assert all(len(r["job_ids"]) == 1 for r in runs)
    assert sorted(r["job_ids"][0] for r in runs if r["kind"] == "apply") == sorted([*ids, found])
    assert [r["kind"] for r in runs if r["job_ids"] == [found]] == ["score", "prepare", "apply"]
    assert not any(r["auto_submit"] for r in runs)


def test_create_saves_and_loads_dry_run_does_not(settings):
    s = Store(settings)
    j = add_job(s, 1)
    dry = batches.create(settings, [j], "score", dry_run=True, now=NOW)
    assert dry["dry_run"] is True and "id" not in dry
    assert batches.list_ids(settings) == []
    b = batches.create(settings, [j], "score", name="First", now=NOW)
    assert b["status"] == "queued" and b["name"] == "First"
    assert batches.load(settings, b["id"]) == b
    assert batches.list_ids(settings) == [b["id"]]


def test_refusals(settings):
    j = add_job(Store(settings), 1)
    with pytest.raises(ValueError, match="stop_at"):
        batches.preview(settings, [j], "mass_apply", now=NOW)
    with pytest.raises(ValueError, match="job"):
        batches.preview(settings, [], "score", now=NOW)
    with pytest.raises(ValueError, match="no job"):
        batches.create(settings, ["nope"], "score", now=NOW)
    assert batches.load(settings, "../../etc") is None
    assert batches.load(settings, "missing") is None


# --- REQ-118: per-job stop points, capped server-side ------------------------------------------------------------
def test_linkedin_found_with_ats_apply_url_is_not_capped(settings):
    s = Store(settings)  # REQ-118 amends REQ-045: keyed on the apply URL host, not the board it was found on
    jid = put(s, add_job(s, 1, ats="linkedin", url="https://www.linkedin.com/jobs/view/1",
                         apply_url="https://boards.greenhouse.io/x/jobs/1"), "prepared", tier="B", qa=True)
    r = batches.preview(settings, [jid], "fill", now=NOW)["selected"][0]
    assert r["stages"] == ["apply"] and "cap" not in r


def test_per_job_stops_override_the_default(settings):
    s = Store(settings)
    a, b, c = (add_job(s, n, company=f"C{n}") for n in range(3))
    out = batches.preview(settings, [a, b, c], "fill", now=NOW, stops={b: "prepare", c: "submit"})
    sel = by_id(out["selected"])
    assert sel[a]["stop_at"] == "fill" and sel[a]["stages"] == ["score", "prepare", "apply"]
    assert sel[b]["stop_at"] == "prepare" and sel[b]["stages"] == ["score", "prepare"]
    assert sel[c]["stop_at"] == "submit" and sel[c]["submit_reason"] == "decided at apply"
    assert sel[a]["submit_reason"] == "stop point fill: never submits"
    assert out["stops"] == {b: "prepare", c: "submit"} and out["stop_at"] == "fill"
    assert [r["kind"] for r in batches.job_runs(out) if r["job_id"] == b] == ["score", "prepare"]
    assert "stops" not in batches.preview(settings, [a], "fill", now=NOW)  # no stops: the batch file as before


def test_stops_reject_bad_input(settings):
    s = Store(settings)
    a = add_job(s, 1)
    with pytest.raises(ValueError, match="stop_at must be"):
        batches.preview(settings, [a], "fill", now=NOW, stops={a: "mass"})
    with pytest.raises(ValueError, match="not picked"):
        batches.preview(settings, [a], "fill", now=NOW, stops={"other": "fill"})


def test_tier_a_submit_is_lowered_to_fill(settings):
    allow_submit(settings)
    s = Store(settings)
    a = put(s, add_job(s, 1), "prepared", tier="A", qa=True)
    r = batches.preview(settings, [a], "prepare", now=NOW, stops={a: "submit"})["selected"][0]
    assert r["stop_at"] == "fill" and "tier_a" in r["cap"]
    assert r["auto_submit"] is False and r["submit_reason"] == r["cap"]


def test_linkedin_submit_is_lowered_to_prepare(settings):
    s = Store(settings)
    li = add_job(s, 1, apply_url="https://www.linkedin.com/jobs/view/1")
    r = batches.preview(settings, [li], "score", now=NOW, stops={li: "submit"})["selected"][0]
    assert r["stop_at"] == "prepare" and r["stages"] == ["score", "prepare"] and "LinkedIn" in r["cap"]



@pytest.mark.parametrize("posting,want", [
    ({"apply_url": "www.linkedin.com/jobs/view/1"}, True),  # scheme-less: must not fail open
    ({"url": "linkedin.com/jobs/view/1"}, True),
    ({"ats": "linkedin"}, True),  # no URL at all: the board is the only signal
    ({"ats": "LinkedIn", "apply_url": "https://boards.greenhouse.io/x/jobs/1"}, False),
    ({"apply_url": "boards.greenhouse.io/x/jobs/1"}, False),
    ({"apply_url": "https://notlinkedin.com/x"}, False),
])
def test_is_linkedin(posting, want):
    assert batches.is_linkedin(posting) is want


def test_schemeless_linkedin_apply_url_is_capped(settings):
    s = Store(settings)
    li = add_job(s, 1, apply_url="www.linkedin.com/jobs/view/1")
    r = batches.preview(settings, [li], "score", now=NOW, stops={li: "submit"})["selected"][0]
    assert r["stop_at"] == "prepare" and "LinkedIn" in r["cap"]


def test_kind_follows_the_highest_stop(settings):
    s = Store(settings)
    a, c = add_job(s, 1), add_job(s, 2, company="C2")
    assert batches.preview(settings, [a, c], "prepare", now=NOW, stops={c: "fill"})["kind"] == "apply"

@pytest.mark.readiness
def test_readiness_open_caps_fill_and_submit_at_prepare(settings):
    s = Store(settings)  # the example root still has example data: readiness must-haves open
    a = add_job(s, 1)
    r = batches.preview(settings, [a], "submit", now=NOW)["selected"][0]
    assert r["stop_at"] == "prepare" and r["stages"] == ["score", "prepare"] and "readiness" in r["cap"]


def test_flagged_posting_is_excluded_whatever_its_stop(settings):
    s = Store(settings)
    a = put(s, add_job(s, 1), "scored", tier="B")
    (s.job_dir(a) / "flags.json").write_text(json.dumps({"injection_suspected": True}))
    out = batches.preview(settings, [a], "prepare", now=NOW, stops={a: "submit"})
    assert out["selected"] == [] and "injection" in out["excluded"][0]["reason"]


@pytest.mark.unit
def test_named_jobs_count_as_ticked_and_start_ticks_them(settings):
    """#144 decision: Start pipeline review takes the Jobs-table row selection, not the persisted REQ-104 tick."""
    s = Store(settings)
    jid = put(s, add_job(s, 1), "scored")
    s.set_selected([jid], False)
    out = batches.preview(settings, [jid], "prepare", now=NOW)
    assert [r["job_id"] for r in out["selected"]] == [jid], out["excluded"]
    assert not s.is_selected(jid)  # a preview never ticks
    batches.create(settings, [jid], "prepare", now=NOW)
    assert s.is_selected(jid)  # Start ticks it, so the driver's mid-run untick check still applies
