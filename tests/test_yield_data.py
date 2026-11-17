"""Yield-model data: channel on status history, per-application outcome, Wilson interval, report, goal config."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

import pytest
import yaml
from conftest import EXAMPLE_REPO

from careeros.config import ConfigError, Settings
from careeros.models import Posting
from careeros.store import Store
from careeros.yield_data import outcome, wilson, yield_rows

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


def h(*pairs):
    return [{"status": s, "at": f"2026-{at}T12:00:00+00:00", "note": None} for s, at in pairs]


def test_store_channel_default_and_set(settings):
    st = Store(settings)
    st.save_posting(Posting(job_id="a1", company="Acme", title="SWE", ats="greenhouse"))
    st.set_status("a1", "applied")
    assert st.get_channel("a1") == ("cold", None)
    st.set_status("a1", "applied", channel="referral", referral_contact_id="c9")
    assert st.get_channel("a1") == ("referral", "c9")
    st.set_status("a1", "interview")  # a later status keeps the channel
    assert st.get_channel("a1") == ("referral", "c9")
    assert st._read("a1", "status.json")["history"][-2]["channel"] == "referral"
    with pytest.raises(ValueError):
        st.set_status("a1", "interview", channel="bogus")


def test_cli_job_status_channel_and_jobs_list(settings, monkeypatch, capsys):
    import careeros.cli as cli

    monkeypatch.setattr(cli, "_settings", lambda args: settings)
    st = Store(settings)
    st.save_posting(Posting(job_id="a1", company="Acme", title="SWE", ats="greenhouse"))
    assert cli.main(["job", "status", "a1", "applied", "--channel", "sourced", "--referral-contact", "c1"]) == 0
    assert st.get_channel("a1") == ("sourced", "c1")
    capsys.readouterr()
    cli.main(["jobs", "list", "--json"])
    assert json.loads(capsys.readouterr().out)[0]["channel"] == "sourced"
    with pytest.raises(SystemExit):
        cli.main(["job", "status", "a1", "applied", "--channel", "nope"])


@pytest.mark.parametrize("hist,expect", [
    (h(("applied", "10-20"), ("interview", "11-01")), "interview"),
    (h(("applied", "10-20"), ("screening", "11-01"), ("rejected", "11-10")), "rejected"),
    (h(("applied", "10-20"), ("rejected", "11-01")), "rejected"),
    (h(("applied", "10-20")), "censored"),   # 26 days old
    (h(("applied", "09-01")), "open"),       # 75 days, no reply
    (h(("applied", "09-01"), ("ghosted", "10-30")), "open"),
    (h(("applied", "09-01"), ("screening", "09-10")), "open"),          # assessment only: not an interview
    (h(("queued", "10-01"), ("interview", "10-05")), "interview"),       # sourced: no applied entry
])
def test_outcome_cases(hist, expect):
    o = outcome(hist, "2026-10-10T00:00:00+00:00", "cold", NOW)
    assert o["outcome"] == expect and o["channel"] == "cold"


def test_outcome_dates_and_age():
    o = outcome(h(("applied", "10-20"), ("interview", "11-01")), "2026-10-10", "referral", NOW)
    assert o["applied_at"].startswith("2026-10-20") and o["first_interview_at"].startswith("2026-11-01")
    assert o["posting_age_days_at_apply"] == 10
    assert outcome(h(("scored", "10-20")), None, "cold", NOW) is None  # never applied
    assert outcome(h(("applied", "10-20")), None, "cold", NOW)["posting_age_days_at_apply"] is None


def test_wilson():
    lo, hi = wilson(3, 100)
    assert (round(lo, 3), round(hi, 3)) == (0.010, 0.085)
    assert wilson(0, 0) == (0.0, 1.0)
    assert wilson(0, 10)[0] == 0.0 and wilson(10, 10)[1] == 1.0


def test_yield_rows_excludes_censored_from_rate(settings):
    st = Store(settings)
    for jid, ch, status in [("j1", "cold", "interview"), ("j2", "cold", "rejected"), ("j3", "referral", "applied")]:
        st.save_posting(Posting(job_id=jid, company=jid, title="SWE", ats="greenhouse"))
        st.set_status(jid, "applied", channel=ch)
        if status != "applied":
            st.set_status(jid, status)
    rows = yield_rows(st, datetime.now(timezone.utc))  # all applied "now" => censored unless replied
    cold = next(r for r in rows if r["channel"] == "cold")
    assert (cold["n"], cold["interviews"], cold["rate"]) == (2, 1, 0.5)
    ref = next(r for r in rows if r["channel"] == "referral")
    assert ref["n"] == 0 and ref["censored"] == 1


def test_cli_yield_report(settings, monkeypatch, capsys):
    import careeros.cli as cli

    monkeypatch.setattr(cli, "_settings", lambda args: settings)
    assert cli.main(["yield", "report", "--json"]) == 0
    assert {r["channel"] for r in json.loads(capsys.readouterr().out)} == {"cold", "referral", "sourced", "hm_dm"}


# --- goal config ---------------------------------------------------------------------------

def _root(tmp_path, edit):
    root = tmp_path / "r"
    shutil.copytree(EXAMPLE_REPO / "config", root / "config")
    shutil.copytree(EXAMPLE_REPO / "profile", root / "profile")
    p = root / "config" / "targets.yaml"
    d = yaml.safe_load(p.read_text())
    edit(d)
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    return root


def test_example_goal_loads(tmp_path):
    g = Settings.load(_root(tmp_path, lambda d: None)).targets["goal"]
    assert set(g) == {"pay_bar", "minutes_per_week", "locations", "flex_for_prestige"}


@pytest.mark.parametrize("key,bad", [("pay_bar", -1), ("pay_bar", "x"), ("minutes_per_week", 0),
                                      ("locations", "NYC"), ("flex_for_prestige", "yes")])
def test_bad_goal_is_config_error(tmp_path, key, bad):
    with pytest.raises(ConfigError, match=f"goal.{key}"):
        Settings.load(_root(tmp_path, lambda d: d["goal"].update({key: bad})))


def test_goal_not_a_mapping_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="goal must be a mapping"):
        Settings.load(_root(tmp_path, lambda d: d.update({"goal": "x"})))


def test_outcome_screening_counted_apart():
    o = outcome(h(("applied", "09-01"), ("screening", "09-10")), None, "cold", NOW)
    assert o["screening"] is True and o["first_interview_at"] is None


def test_outcome_sourced_starts_at_first_reply():
    o = outcome(h(("queued", "10-01"), ("screening", "10-03")), None, "sourced", NOW)
    assert o["channel"] == "sourced" and o["applied_at"].startswith("2026-10-03")


def test_doctor_warns_without_goal(tmp_path):
    from test_doctor import details, doctor, filled

    root = filled(tmp_path)
    assert not any("goal" in x for x in details(doctor(root), "warn"))
    p = root / "config" / "targets.yaml"
    d = yaml.safe_load(p.read_text())
    d.pop("goal")
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert any("goal" in x for x in details(doctor(root), "warn"))
    p.write_text(yaml.safe_dump({**d, "goal": {"pay_bar": None}}, sort_keys=False))
    assert any("minutes_per_week" in x for x in details(doctor(root), "warn"))


@pytest.mark.integration
def test_cli_channel_then_report_through_status_json(settings, monkeypatch, capsys):
    from careeros import cli

    monkeypatch.setattr(cli, "_settings", lambda a: settings)
    Store(settings).save_posting(Posting(job_id="r1", company="Acme", title="SWE", ats="greenhouse"))
    assert cli.main(["job", "status", "r1", "applied", "--channel", "referral", "--referral-contact", "c9"]) == 0
    st = json.loads((settings.paths["jobs_dir"] / "r1" / "status.json").read_text())
    assert st["channel"] == "referral" and st["history"][-1]["referral_contact_id"] == "c9"
    capsys.readouterr()
    assert cli.main(["yield", "report", "--json"]) == 0
    ref = next(r for r in json.loads(capsys.readouterr().out) if r["channel"] == "referral")
    assert ref["censored"] == 1 and ref["n"] == 0
