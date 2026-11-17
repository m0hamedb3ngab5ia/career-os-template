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
