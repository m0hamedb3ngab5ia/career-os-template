"""`careeros tracker applied-count` and `careeros tracker upsert` (used by the apply-job skill)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from careeros.models import STATUSES
from careeros.tracker import Tracker, parse_field_args

pytestmark = pytest.mark.unit

TODAY = datetime.now().strftime("%Y-%m-%d")


# --- parse_field_args ------------------------------------------------------------------------------

def test_parse_accepts_headers_and_snake_keys():
    got = parse_field_args(["DateApplied=today", "ats=greenhouse", "ResumeVersion=swe_backend-v1",
                            "Status=applied", "fit=88", "QAScore=8.5", "notes=a=b"])
    assert got == {"date_applied": TODAY, "ats": "greenhouse", "resume_version": "swe_backend-v1",
                   "status": "applied", "fit": 88, "qa_score": 8.5, "notes": "a=b"}


def test_parse_header_case_insensitive_and_literal_dates_kept():
    assert parse_field_args(["dateapplied=2026-09-01", "NEXTACTIONDATE=Today"]) == {
        "date_applied": "2026-09-01", "next_action_date": TODAY}


@pytest.mark.parametrize("pairs,msg", [
    (["DateApplied"], "key=value"),
    (["Bogus=1"], "unknown field 'Bogus'"),
    (["JobID=x"], "positional"),
    (["job_id=x"], "positional"),
    (["Status=hired"], "invalid status"),
    (["Fit=high"], "Fit must be an integer"),
    (["QAScore=good"], "QAScore must be a number"),
])
def test_parse_rejects(pairs, msg):
    with pytest.raises(ValueError, match=msg):
        parse_field_args(pairs)


def test_parse_every_status_allowed():
    for st in STATUSES:
        assert parse_field_args([f"Status={st}"]) == {"status": st}


# --- CLI handlers (in-process, settings on tmp) -----------------------------------------------------

@pytest.fixture
def cli(settings, monkeypatch):
    import careeros.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_settings", lambda args: settings)
    return cli_mod.main


def test_applied_count_without_tracker_prints_zero_and_creates_nothing(cli, settings, capsys):
    assert cli(["tracker", "applied-count", "Acme"]) == 0
    assert capsys.readouterr().out.strip() == "0"
    assert not settings.paths["tracker_xlsx"].exists()


def test_upsert_creates_then_updates_and_count_follows(cli, settings, capsys):
    assert cli(["tracker", "upsert", "j1", "--field", "Company=Acme Inc", "--field", "Role=SWE"]) == 0
    assert "j1: created" in capsys.readouterr().out
    assert cli(["tracker", "applied-count", "acme"]) == 0
    assert capsys.readouterr().out.strip() == "0"  # not applied yet

    assert cli(["tracker", "upsert", "j1", "--field", "DateApplied=today", "--field", "Status=applied",
                "--field", "ATS=greenhouse", "--field", "ResumeVersion=swe_backend-v1"]) == 0
    assert "j1: updated (ats, date_applied, resume_version, status)" in capsys.readouterr().out
    row = Tracker(settings=settings).get_job("j1")
    assert (row["Company"], row["Role"], row["Status"], row["DateApplied"], row["ATS"], row["ResumeVersion"]) == (
        "Acme Inc", "SWE", "applied", TODAY, "greenhouse", "swe_backend-v1")

    assert cli(["tracker", "applied-count", "ACME"]) == 0  # normalized company name
    assert capsys.readouterr().out.strip() == "1"


def test_applied_count_respects_days(cli, settings, capsys):
    old = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
    tr = Tracker(settings=settings)
    tr.upsert_job({"job_id": "o1", "company": "Initech", "date_applied": old})
    tr.upsert_job({"job_id": "n1", "company": "Initech", "date_applied": TODAY})
    cli(["tracker", "applied-count", "Initech"])
    assert capsys.readouterr().out.strip() == "1"
    cli(["tracker", "applied-count", "Initech", "--days", "365"])
    assert capsys.readouterr().out.strip() == "2"
    tr.upsert_job({"job_id": "h1", "company": "Hooli", "date_applied": TODAY})
    cli(["tracker", "applied-count", "--days", "1"])  # all companies, today only (daily cap)
    assert capsys.readouterr().out.strip() == "2"
    cli(["tracker", "applied-count", "--days", "365"])
    assert capsys.readouterr().out.strip() == "3"


@pytest.mark.parametrize("argv,err", [
    (["tracker", "upsert", "j1"], "at least one --field"),
    (["tracker", "upsert", "j1", "--field", "Nope=1"], "unknown field"),
    (["tracker", "upsert", "j1", "--field", "Status=hired"], "invalid status"),
])
def test_upsert_bad_input_exits_2_and_writes_nothing(cli, settings, capsys, argv, err):
    assert cli(argv) == 2
    assert err in capsys.readouterr().err
    assert not settings.paths["tracker_xlsx"].exists()


def test_upsert_status_also_updates_status_json_so_sync_keeps_it(cli, settings, capsys):
    from careeros.models import Posting
    from careeros.store import Store

    store = Store(settings)
    store.save_posting(Posting(job_id="s1", company="Acme", title="SWE", ats="greenhouse"))
    assert cli(["tracker", "upsert", "s1", "--field", "Status=applied", "--field", "DateApplied=today"]) == 0
    assert store.get_status("s1") == "applied"
    assert "status -> applied" in store.read_log("s1")
    assert cli(["tracker", "sync"]) == 0
    assert Tracker(settings=settings).get_job("s1")["Status"] == "applied"


def test_upsert_status_for_unknown_job_touches_only_tracker(cli, settings):
    from careeros.store import Store

    assert cli(["tracker", "upsert", "ghost", "--field", "Status=queued"]) == 0
    assert Tracker(settings=settings).get_job("ghost")["Status"] == "queued"
    assert not Store(settings).job_dir("ghost").exists()
