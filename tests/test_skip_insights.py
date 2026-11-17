"""Skip insights: why jobs were skipped, which skills and filters would unlock the most (suggest-only)."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pytest

from careeros import cli, hard_filters
from careeros.runs import advisor
from careeros.runs.skip_insights import skip_insights

pytestmark = pytest.mark.unit


def _s(fit, decision="skip", fails=(), missing=(), reason=None):
    r = reason or (fails[0] if fails else ("below_min_fit" if decision == "skip" else None))
    return {"decision": decision, "fit": fit, "hard_filter_fails": list(fails), "skip_reason": r,
            "missing_skills": list(missing)}


def _none(sk):
    return {}


def test_reasons_counted_and_prepared_ignored():
    out = skip_insights([_s(80, "prepare"), _s(0, fails=["yoe_gt_3"]), _s(0, fails=["yoe_gt_3"]), _s(40)], 60, _none)
    assert out["skipped"] == 3
    assert out["reasons"][0] == {"reason": "yoe_gt_3", "count": 2}
    assert {"reason": "below_min_fit", "count": 1} in out["reasons"]


def test_skills_only_from_near_miss_below_min_fit_and_split_scorer_misses():
    jobs = [_s(55, missing=["Go", "Linux"]), _s(52, missing=["Go"]), _s(20, missing=["Rust"]),
            _s(90, missing=["Zig"], reason="company_cap"), _s(60, missing=["Elixir"])]
    out = skip_insights(jobs, 60, lambda sk: {k: "x" for k in sk if k == "Linux"})
    assert out["skills"]["learnable"] == [{"skill": "Go", "near_miss": 2}]
    assert out["skills"]["scorer_misses"] == [{"skill": "Linux", "count": 1}]


def test_flex_counts_blocked_and_only_fail_via_real_write_skip(settings):
    posting = {"title": "Engineer", "company": "Co"}
    for jid, fails in (("a", ["yoe_gt_3"]), ("b", ["yoe_gt_3", "location_blocked"]), ("c", ["salary_below_min"])):
        hard_filters.write_skip(settings, jid, posting, fails)
    from careeros.runs.skip_insights import load_scores
    f = {x["filter"]: x for x in skip_insights(load_scores(settings.paths["jobs_dir"]), 60, _none)["flex"]}
    assert f["years"] == {"filter": "years", "blocked": 2, "rescored": 1}
    assert f["location"]["rescored"] == 0 and f["salary"]["rescored"] == 1


def _seed(settings):
    d = settings.paths["jobs_dir"] / "j1"
    d.mkdir(parents=True)
    (d / "score.json").write_text(json.dumps(_s(55, missing=["Go"])))
    k = settings.paths["jobs_dir"] / "j2"
    k.mkdir()
    (k / "score.json").write_text(json.dumps(_s(55, missing=["Linux"])))
    settings.targets["thresholds"] = {"min_fit_to_prepare": 60}
    settings.pipeline["match"] = {"synonyms": {}, "implies": {}}
    settings.profile = {"skills": {"Cloud": ["Linux"]}}


def test_advise_is_advice_only_and_excludes_evidenced_skills(settings):
    _seed(settings)
    out = advisor.advise(settings, datetime(2026, 11, 16, tzinfo=timezone.utc))
    assert [x["skill"] for x in out["skips"]["skills"]["learnable"]] == ["Go"]
    assert all(r["change"] is None for r in out["recommendations"] if r["kind"] == "skips")


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_prints_scorer_misses(settings, monkeypatch, capsys, as_json):
    _seed(settings)
    monkeypatch.setattr(cli, "_settings", lambda a: settings)
    assert cli.cmd_advise(argparse.Namespace(json=as_json)) == 0
    out = capsys.readouterr().out
    if as_json:
        assert json.loads(out)["skips"]["skills"]["scorer_misses"] == [{"skill": "Linux", "count": 1}]
    else:
        assert "scorer misses" in out and "Linux 1" in out
