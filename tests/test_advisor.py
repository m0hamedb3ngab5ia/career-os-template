"""Storage snapshots, the suggest-only advisor, and the comment-preserving YAML edit behind `advise apply`."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from careeros.config import ConfigError
from careeros.runs import advisor, storage, yamledit
from careeros.runs.store import RunStore

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
MB = 1024 * 1024


# --- measuring --------------------------------------------------------------------------------------------

def _file(p: Path, n: int) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * n)


def test_measure_splits_data_by_category(settings, tmp_path):
    jobs = settings.paths["jobs_dir"]
    _file(jobs / "j1" / "posting.json", 100)
    _file(jobs / "j1" / "resume.pdf", 200)
    _file(jobs / "j1" / "cover_letter.md", 10)
    _file(jobs / "j1" / "submitted" / "20260101" / "resume.pdf", 50)
    _file(jobs / "j1" / "screenshots" / "01_form.png", 300)
    _file(jobs / "j1" / "status.json", 7)
    runs = RunStore(settings).dir
    _file(runs / "r1" / "run.log", 40)
    _file(runs / "r1" / "attempts" / "001.stream.jsonl", 60)
    _file(runs / "r1" / "run.json", 5)
    _file(settings.paths["tracker_xlsx"], 70)
    got = storage.measure(settings, disk=lambda p: (1000 * MB, 250 * MB))
    assert got["bytes"] == {"postings": 100, "resumes_pdfs": 260, "screenshots": 300, "run_logs": 100,
                            "tracker": 70, "other": 12}
    assert got["total"] == 842
    assert got["disk"] == {"total": 1000 * MB, "free": 250 * MB, "free_pct": 25.0}


def test_snapshots_append_and_load(settings):
    rs = RunStore(settings)
    storage.append_snapshot(rs, {"bytes": {"postings": 1}, "total": 1, "disk": {}}, trigger="prune", now=NOW,
                            pruned_bytes=5)
    storage.append_snapshot(rs, {"bytes": {"postings": 2}, "total": 2, "disk": {}}, trigger="manual",
                            now=NOW + timedelta(days=1))
    snaps = storage.load_snapshots(rs)
    assert [s["total"] for s in snaps] == [1, 2] and snaps[0]["pruned_bytes"] == 5 and snaps[1]["trigger"] == "manual"
    assert (rs.dir / "storage.jsonl").read_text().count("\n") == 2


# --- storage advice ---------------------------------------------------------------------------------------

def snap(days_ago: float, total_mb: float, dominant: str = "postings", free_pct: float = 50, pruned: int | None = 0,
         trigger: str = "prune") -> dict:
    cats = {c: 0 for c in storage.CATEGORIES}
    cats[dominant] = int(total_mb * MB * 0.8)
    cats["other"] = int(total_mb * MB) - cats[dominant]
    return {"at": (NOW - timedelta(days=days_ago)).isoformat(), "bytes": cats, "total": int(total_mb * MB),
            "disk": {"total": 100_000 * MB, "free": int(free_pct * 1000 * MB), "free_pct": free_pct},
            "trigger": trigger, "pruned_bytes": pruned}


PIPE = {"retention": {"screenshots_after_closed_days": 30, "unprepared_posting_days": 90, "run_logs_days": 30,
                      "run_summaries_days": 365}}


def test_no_storage_advice_before_advise_after_days():
    out = advisor.storage_advice([snap(10, 100), snap(0, 900)], PIPE, NOW)
    assert out["ready"] is False and out["days"] == 10 and out["recommendations"] == []


def test_fast_growth_tightens_the_dominant_category():
    snaps = [snap(21, 100), snap(14, 300), snap(7, 500), snap(0, 700)]
    out = advisor.storage_advice(snaps, PIPE, NOW)
    assert out["ready"] and out["projection"]["90d"] > out["projection"]["30d"] > 700 * MB
    rec = next(r for r in out["recommendations"] if r["id"] == "tighten-unprepared_posting_days")
    assert rec["change"] == {"file": "config/pipeline.yaml", "path": "retention.unprepared_posting_days",
                             "from": 90, "to": 60}


@pytest.mark.parametrize("cat,key,to", [("screenshots", "screenshots_after_closed_days", 14),
                                        ("run_logs", "run_logs_days", 14)])
def test_dominant_category_picks_its_retention_key(cat, key, to):
    snaps = [snap(21, 100, cat), snap(0, 900, cat)]
    rec = next(r for r in advisor.storage_advice(snaps, PIPE, NOW)["recommendations"] if r["id"] == f"tighten-{key}")
    assert rec["change"]["to"] == to


def test_resumes_dominant_is_advice_only():
    snaps = [snap(21, 100, "resumes_pdfs"), snap(0, 900, "resumes_pdfs")]
    recs = advisor.storage_advice(snaps, PIPE, NOW)["recommendations"]
    assert any(r["id"] == "storage-resumes_pdfs" and r["change"] is None for r in recs)


def test_slow_growth_under_budget_gives_no_tighten():
    snaps = [snap(21, 100, pruned=100), snap(0, 101, pruned=100)]
    assert [r for r in advisor.storage_advice(snaps, PIPE, NOW)["recommendations"]
            if r["id"].startswith("tighten")] == []


def test_low_disk_warns():
    recs = advisor.storage_advice([snap(20, 10), snap(0, 10, free_pct=5)], PIPE, NOW)["recommendations"]
    assert any(r["id"] == "disk-low" and r["severity"] == "warn" for r in recs)


def test_prune_removing_nothing_for_weeks_suggests_loosening():
    snaps = [snap(35, 10, pruned=0), snap(28, 10, pruned=0), snap(21, 10, pruned=0), snap(14, 10, pruned=0),
             snap(7, 10, pruned=0), snap(0, 10, pruned=0)]
    rec = next(r for r in advisor.storage_advice(snaps, PIPE, NOW)["recommendations"]
               if r["id"] == "loosen-unprepared_posting_days")
    assert rec["change"]["from"] == 90 and rec["change"]["to"] > 90


def test_budget_and_thresholds_come_from_config():
    snaps = [snap(21, 100), snap(0, 120)]
    cfg = {**PIPE, "storage": {"budget_mb": 100, "warn_at_pct": 50}}
    assert any(r["id"].startswith("tighten") for r in advisor.storage_advice(snaps, cfg, NOW)["recommendations"])


@pytest.mark.parametrize("bad", [{"storage": {"budget_mb": 0}}, {"storage": {"warn_at_pct": 120}},
                                 {"advisor": {"advise_after_days": -1}}, {"storage": {"bogus": 1}}])
def test_advisor_config_validated(bad):
    with pytest.raises(ConfigError):
        advisor.load_advisor_config(bad)


# --- run efficiency ---------------------------------------------------------------------------------------

def run(kind="score", stop="completed", attempted=5, ok=5, candidates=5, max_jobs=25, durations=(60,) * 5,
        outcomes=None, days_ago=1):
    atts = [{"stage": kind, "duration_s": d, "outcome": (outcomes or ["ok"] * len(durations))[i],
             "result": {"decision": "prepare"} if kind == "score" else {}} for i, d in enumerate(durations)]
    return {"kind": kind, "stop_reason": stop, "status": "done",
            "counters": {"attempted": attempted, "ok": ok, "failed": attempted - ok, "candidates": candidates},
            "budget": {"preset": "medium", "max_jobs": max_jobs, "max_minutes": 90},
            "started_at": (NOW - timedelta(days=days_ago)).isoformat(), "_attempts": atts}


RUNS_CFG = {"runs": {"preset": "medium"}, "schedule": {"jobs": {"score": {"every_hours": 6}}}}


def test_run_advice_needs_enough_runs():
    out = advisor.run_advice([run()], RUNS_CFG, NOW)
    assert out["ready"] is False and out["recommendations"] == []


def test_slow_jobs_near_the_timeout_raise_it():
    runs = [run(durations=(540, 560, 580, 590, 500)) for _ in range(5)]
    rec = next(r for r in advisor.run_advice(runs, RUNS_CFG, NOW)["recommendations"] if r["id"] == "timeout-score")
    assert rec["change"]["path"] == "runs.job_timeout_minutes.score" and rec["change"]["to"] > 10


def test_usage_limit_stops_suggest_a_smaller_preset():
    runs = [run(stop="usage_limit") for _ in range(3)] + [run() for _ in range(3)]
    rec = next(r for r in advisor.run_advice(runs, RUNS_CFG, NOW)["recommendations"] if r["id"] == "preset-down")
    assert rec["change"] == {"file": "config/pipeline.yaml", "path": "runs.preset", "from": "medium", "to": "small"}


def test_backlog_growing_at_budget_suggests_a_bigger_preset():
    runs = [run(stop="budget_reached", attempted=25, ok=25, candidates=120, durations=(60,) * 25) for _ in range(5)]
    rec = next(r for r in advisor.run_advice(runs, RUNS_CFG, NOW)["recommendations"] if r["id"] == "preset-up")
    assert rec["change"]["to"] == "large"


def test_high_failure_rate_is_advice_only_and_metrics_are_reported():
    runs = [run(attempted=5, ok=2, durations=(60,) * 5,
                outcomes=["ok", "ok", "invalid_result", "error", "error"]) for _ in range(5)]
    out = advisor.run_advice(runs, RUNS_CFG, NOW)
    rec = next(r for r in out["recommendations"] if r["id"] == "failures-score")
    assert rec["change"] is None
    m = out["metrics"]["score"]
    assert m["runs"] == 5 and m["failure_rate"] == 0.6 and m["avg_job_s"] == 60


# --- YAML edit (ruamel round trip) -------------------------------------------------------------------------

YAML = """# top comment
retention:                       # keep me
  unprepared_posting_days: 90    # inline note
  run_logs_days: 30
runs:
  preset: medium                 # small | medium (Recommended)
  job_timeout_minutes: {score: 10, prepare: 45}
"""


def test_set_path_preserves_comments_and_layout(tmp_path):
    p = tmp_path / "pipeline.yaml"
    p.write_text(YAML)
    old = yamledit.set_path(p, "retention.unprepared_posting_days", 60)
    assert old == 90
    text = p.read_text()
    assert "# top comment" in text and "# keep me" in text and "# inline note" in text
    assert "unprepared_posting_days: 60" in text and text.count("\n") == YAML.count("\n")
    yamledit.set_path(p, "runs.job_timeout_minutes.score", 15)
    assert "{score: 15, prepare: 45}" in p.read_text()


def test_set_path_creates_missing_keys(tmp_path):
    p = tmp_path / "pipeline.yaml"
    p.write_text(YAML)
    assert yamledit.set_path(p, "runs.retry.max_attempts", 3) is None
    assert "max_attempts: 3" in p.read_text()


def test_set_path_writes_through_a_symlink(tmp_path):
    real = tmp_path / "private" / "pipeline.yaml"
    real.parent.mkdir()
    real.write_text(YAML)
    link = tmp_path / "config" / "pipeline.yaml"
    link.parent.mkdir()
    link.symlink_to(real)
    yamledit.set_path(link, "runs.preset", "small")
    assert link.is_symlink() and "preset: small" in real.read_text()


def test_apply_rolls_back_when_the_result_does_not_validate(tmp_path):
    p = tmp_path / "pipeline.yaml"
    p.write_text(YAML)

    def validate(path):
        raise ConfigError("nope")

    with pytest.raises(ConfigError):
        yamledit.apply_change(p, "runs.preset", "huge", validate=validate)
    assert p.read_text() == YAML


def test_apply_refuses_a_stale_recommendation(tmp_path):
    p = tmp_path / "pipeline.yaml"
    p.write_text(YAML)
    with pytest.raises(ValueError, match="now"):
        yamledit.apply_change(p, "runs.preset", "small", expect_from="large", validate=lambda path: None)
    assert json.dumps(p.read_text()) == json.dumps(YAML)


def test_aligned_flow_mappings_keep_their_spacing(tmp_path):
    p = tmp_path / "pipeline.yaml"
    text = ("runs:\n  presets:\n    small:  {max_score_jobs: 10}      # a\n    medium: {max_score_jobs: 25}   # b\n"
            "  preset: medium   # c\n")
    p.write_text(text)
    yamledit.set_path(p, "runs.preset", "small")
    got = p.read_text().splitlines()
    assert got[2] == "    small:  {max_score_jobs: 10}      # a" and got[4].startswith("  preset: small")


def test_example_config_documents_advisor_defaults():
    import yaml
    from conftest import EXAMPLE_REPO

    text = (EXAMPLE_REPO / "config" / "pipeline.yaml").read_text()
    data = yaml.safe_load(text)
    assert advisor.load_advisor_config(data) == advisor.load_advisor_config({})
    block = text[text.index("\nstorage:"):text.index("\nnotify:")]
    assert block.count("(Recommended)") >= 8
