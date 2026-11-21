"""Follow-up nudges: one `follow_up` Action Item per applied job with no reply after N days, and per sent outreach
with no answer; deduped, closed when the job moves on or the contact replies."""
from __future__ import annotations

import json
from datetime import date

import pytest

from careeros.follow_ups import after_days, raise_follow_ups
from careeros.models import Posting
from careeros.store import Store
from careeros.tracker import Tracker

pytestmark = pytest.mark.unit

TODAY = date(2026, 11, 16)


def _job(settings, tr, n, applied="2026-11-01", status="applied"):
    p = Posting(company="Nimbus", title=f"Engineer {n}", ats="greenhouse", ats_job_id=str(n),
                description_text="x", url=f"https://example.com/{n}")
    Store(settings).save_posting(p)
    tr.upsert_jobs([{"job_id": p.job_id, "company": p.company, "title": p.title, "status": status,
                     "date_applied": applied}])
    return p


def _outreach(settings, p, **draft):
    d = Store(settings).job_dir(p.job_id)
    (d / "outreach.json").write_text(json.dumps({"drafts": [{"sent": True, **draft}]}))


@pytest.fixture
def env(settings):
    tr = Tracker(settings=settings)
    tr.init()
    return settings, tr


def _open(tr):
    return [i for i in tr.list_action_items() if i["Type"] == "follow_up"]


def test_default_is_seven_days(env):
    assert after_days(env[0]) == 7


def test_applied_job_with_no_reply_gets_one_deduped_item(env):
    s, tr = env
    old = _job(s, tr, 1, applied="2026-11-05")
    _job(s, tr, 2, applied="2026-11-12")                  # only 4 days
    _job(s, tr, 3, applied="2026-11-01", status="screening")  # moved on
    assert len(raise_follow_ups(s, TODAY)) == 1
    assert raise_follow_ups(s, TODAY) == []               # second tick adds nothing
    (it,) = _open(tr)
    assert it["JobID"] == old.job_id and "11 days" in it["What to do"]


def test_item_closes_when_job_moves_on(env):
    s, tr = env
    p = _job(s, tr, 1)
    raise_follow_ups(s, TODAY)
    tr.set_status(p.job_id, "interview")
    raise_follow_ups(s, TODAY)
    assert _open(tr) == []


def test_sent_outreach_without_answer_gets_item_and_closes_on_reply(env):
    s, tr = env
    p = _job(s, tr, 1, applied="2026-11-15")              # applied yesterday: no applied nudge
    _outreach(s, p, sent_at="2026-11-02")
    assert len(raise_follow_ups(s, TODAY)) == 1
    assert "message" in _open(tr)[0]["What to do"]
    _outreach(s, p, sent_at="2026-11-02", replied=True)
    raise_follow_ups(s, TODAY)
    assert _open(tr) == []


def test_unsent_or_recent_outreach_is_ignored(env):
    s, tr = env
    p = _job(s, tr, 1, applied="2026-11-15")
    _outreach(s, p, sent_at="2026-11-14")
    d = Store(s).job_dir(p.job_id)
    (d / "outreach.json").write_text(json.dumps({"drafts": [{"sent": False}]}))
    assert raise_follow_ups(s, TODAY) == []


def test_outreach_sent_writes_sent_at_and_triggers_nudge(env, monkeypatch):
    from careeros.cli import main

    s, tr = env
    p = _job(s, tr, 1, applied="2026-11-15")
    d = Store(s).job_dir(p.job_id)
    (d / "outreach.json").write_text(json.dumps({"drafts": [
        {"contact": "Jane Doe", "sent": False, "sent_by": None},
        {"contact": "Bob Ray", "sent": False, "sent_by": None}]}))
    monkeypatch.setattr("careeros.cli._settings", lambda a: s)
    assert main(["outreach", "sent", p.job_id, "--contact", "Jane Doe", "--date", "2026-11-02"]) == 0
    a, b = json.loads((d / "outreach.json").read_text())["drafts"]
    assert a["sent"] is True and a["sent_by"] == "candidate" and a["sent_at"] == "2026-11-02" and b["sent"] is False
    assert len(raise_follow_ups(s, TODAY)) == 1


def test_done_sticks_across_ticks(env):
    s, tr = env
    _job(s, tr, 1)
    raise_follow_ups(s, TODAY)
    tr.mark_action_done(_open(tr)[0]["ID"])
    assert raise_follow_ups(s, TODAY) == []
    assert [i for i in tr.list_action_items() if i["Type"] == "follow_up" and i["Done"] != "Y"] == []


def test_locked_ticks_are_idempotent(env, monkeypatch):
    from openpyxl.workbook.workbook import Workbook

    s, tr = env
    _job(s, tr, 1)
    real_save = Workbook.save

    def locked(self, filename):  # noqa: ANN001, ANN202
        raise PermissionError(13, "locked")

    monkeypatch.setattr(Workbook, "save", locked)
    with pytest.warns(UserWarning):
        raise_follow_ups(s, TODAY)
        raise_follow_ups(s, TODAY)
    monkeypatch.setattr(Workbook, "save", real_save)
    Tracker(settings=s).flush_pending()
    assert len(_open(tr)) == 1


def test_outreach_email_result_bounce_rotates_to_the_next_guess(env, monkeypatch):
    from careeros.cli import main

    s, tr = env
    p = _job(s, tr, 1, applied="2026-11-15")
    d = Store(s).job_dir(p.job_id)
    (d / "outreach.json").write_text(json.dumps({"drafts": [
        {"contact": "Jane Doe", "to": "jane.doe@acme.com", "sent": True, "sent_by": "candidate"}]}))
    monkeypatch.setattr("careeros.cli._settings", lambda a: s)
    assert main(["outreach", "email-result", p.job_id, "--contact", "Jane Doe", "--bounced", "550 5.1.1"]) == 0
    dr = json.loads((d / "outreach.json").read_text())["drafts"][0]
    assert dr["to"] != "jane.doe@acme.com" and dr["sent"] is False
    assert dr["bounced"][0]["to"] == "jane.doe@acme.com" and dr["bounced"][0]["error"] == "550 5.1.1"
    assert main(["outreach", "email-result", p.job_id, "--contact", "Jane Doe", "--delivered"]) == 0
    pats = json.loads((Store(s).jobs_dir.parent / "email_patterns.json").read_text())
    assert pats["acme.com"]["failed"] == ["{first}.{last}"] and pats["acme.com"]["works"]


def test_outreach_email_result_inactive_mailbox_holds_and_keeps_the_format(env, monkeypatch):
    """550 5.2.1: the address format is right but the person left; hold, no rotation (user 2026-11-19)."""
    from careeros.cli import main

    s, tr = env
    p = _job(s, tr, 1, applied="2026-11-15")
    d = Store(s).job_dir(p.job_id)
    (d / "outreach.json").write_text(json.dumps({"drafts": [
        {"contact": "Jane Doe", "to": "jane.doe@acme.com", "sent": True, "sent_by": "candidate"}]}))
    monkeypatch.setattr("careeros.cli._settings", lambda a: s)
    assert main(["outreach", "email-result", p.job_id, "--contact", "Jane Doe", "--bounced", "550 5.2.1"]) == 0
    dr = json.loads((d / "outreach.json").read_text())["drafts"][0]
    assert dr["to"] == "jane.doe@acme.com" and dr["sent"] is False and dr["hold"] is True
    assert "left" in dr["hold_reason"]
    pats = json.loads((Store(s).jobs_dir.parent / "email_patterns.json").read_text())
    assert pats["acme.com"] == {"works": "{first}.{last}", "failed": []}


def test_7d_followup_sent_closes_item_and_14d_is_raised_later(env):
    s, tr = env
    p = _job(s, tr, 20, applied="2026-12-31")
    _outreach(s, p, sent_at="2026-11-01", followup_7d="a", followup_14d="b")
    raise_follow_ups(s, TODAY)
    assert [i["Detail"] for i in tr.list_action_items()] == ["follow_up:outreach"]
    _outreach(s, p, sent_at="2026-11-01", followup_7d="a", followup_14d="b", followup_7d_sent_at="2026-11-09")
    raise_follow_ups(s, date(2026, 11, 14))  # 13 days after the send: 14d not due yet
    assert tr.list_action_items() == []
    raise_follow_ups(s, date(2026, 11, 15))
    assert [i["Detail"] for i in tr.list_action_items()] == ["follow_up:outreach14"]


def test_no_14d_text_means_no_second_item(env):
    s, tr = env
    p = _job(s, tr, 21, applied="2026-12-31")
    _outreach(s, p, sent_at="2026-11-01", followup_7d="a", followup_7d_sent_at="2026-11-09")
    raise_follow_ups(s, date(2026, 12, 1))
    assert tr.list_action_items() == []


def test_contact_rows_show_followed_up_and_next_due(env):
    from careeros.follow_ups import contact_rows
    s, tr = env
    p = _job(s, tr, 22, applied="2026-12-31")
    _outreach(s, p, contact="Sam", to="s@x.com", sent_at="2026-11-01", followup_7d="a", followup_14d="b")
    assert contact_rows(Store(s), s)[0]["FollowUpDue"] == "2026-11-08"
    _outreach(s, p, contact="Sam", to="s@x.com", sent_at="2026-11-01", followup_7d="a", followup_14d="b",
              followup_7d_sent_at="2026-11-09")
    r = contact_rows(Store(s), s)[0]
    assert r["EmailStatus"] == "delivered; followed up 2026-11-09" and r["FollowUpDue"] == "2026-11-15"
    _outreach(s, p, contact="Sam", to="s@x.com", sent_at="2026-11-01", followup_7d="a", followup_14d="b",
              followup_7d_sent_at="2026-11-09", followup_14d_sent_at="2026-11-15")
    r = contact_rows(Store(s), s)[0]
    assert "followed up 2026-11-15" in r["EmailStatus"] and r["FollowUpDue"] == ""
