"""Email digest to self (REQ-155) and the outreach nag (REQ-156). Fake sender + fake keychain: no network, no `security`."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime

import pytest

from careeros import notify
from careeros.follow_ups import raise_reach_outs
from careeros.models import Posting
from careeros.store import Store
from careeros.tracker import Tracker

pytestmark = pytest.mark.unit

TODAY = date(2026, 11, 16)


def _job(settings, tr, n, applied="2026-11-14", status="applied"):
    p = Posting(company="Nimbus", title=f"Engineer {n}", ats="greenhouse", ats_job_id=str(n),
                description_text="x", url=f"https://example.com/{n}")
    Store(settings).save_posting(p)
    tr.upsert_jobs([{"job_id": p.job_id, "company": p.company, "title": p.title, "status": status,
                     "date_applied": applied}])
    return p


@pytest.fixture
def env(settings):
    tr = Tracker(settings=settings)
    tr.init()
    settings.pipeline["notify"] = {"enabled": True, "email": "me@example.com", "send_at": "08:00"}
    return settings, tr


def _reach(tr):
    return [i for i in tr.list_action_items() if i["Type"] == "follow_up" and i["Detail"] == "reach_out"]


def test_reach_out_item_for_recent_applied_job_only(env):
    s, tr = env
    p = _job(s, tr, 1, applied="2026-11-14")
    _job(s, tr, 2, applied="2026-10-01")               # outside the 14-day window
    _job(s, tr, 3, status="queued")
    assert len(raise_reach_outs(s, TODAY)) == 1
    assert raise_reach_outs(s, TODAY) == []             # deduped
    (it,) = _reach(tr)
    assert it["JobID"] == p.job_id and it["Priority"] == "H" and "recruiter or hiring manager" in it["What to do"]
    assert "Engineer 1" in it["What to do"] and "Nimbus" in it["What to do"]


def test_reach_out_closes_when_outreach_sent_or_done_sticks(env):
    s, tr = env
    p = _job(s, tr, 1)
    raise_reach_outs(s, TODAY)
    d = Store(s).job_dir(p.job_id)
    (d / "outreach.json").write_text(json.dumps({"drafts": [{"sent": True, "sent_at": "2026-11-15"}]}))
    raise_reach_outs(s, TODAY)
    assert _reach(tr) == []
    assert raise_reach_outs(s, TODAY) == []             # done item still dedups


def test_digest_sections_and_days(env):
    s, tr = env
    p = _job(s, tr, 1, applied="2026-11-02")
    raise_reach_outs(s, date(2026, 11, 13))             # due 11-13 -> 3 days overdue on 11-16
    tr.add_action_item("Upload transcript", type="other", priority="H")
    body = notify.build_digest(s, TODAY)
    assert "Reach out" in body and "Engineer 1 @ Nimbus" in body and "https://example.com/1" in body
    assert "3 days" in body and "Needs you" in body and "Upload transcript" in body
    assert "Follow up" not in body                       # empty section omitted
    assert p.job_id not in body


def test_digest_none_when_everything_empty(env):
    s, _ = env
    assert notify.build_digest(s, TODAY) is None


class FakeSender:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def __call__(self, cfg, subject, body, password):
        if self.fail:
            raise OSError("smtp down")
        self.sent.append((cfg["email"], subject, body, password))


def _due(env):
    s, tr = env
    _job(s, tr, 1)
    raise_reach_outs(s, TODAY)
    return s


def test_send_once_per_day_after_send_at(env):
    s = _due(env)
    snd, kc = FakeSender(), lambda email: "fake-pw"
    early = datetime(2026, 11, 16, 7, 0)
    assert notify.maybe_send_digest(s, early, sender=snd, keychain=kc) == "too_early"
    at = datetime(2026, 11, 16, 8, 5)
    assert notify.maybe_send_digest(s, at, sender=snd, keychain=kc) == "sent"
    assert notify.maybe_send_digest(s, at, sender=snd, keychain=kc) == "already_sent"
    assert len(snd.sent) == 1 and snd.sent[0][3] == "fake-pw" and snd.sent[0][0] == "me@example.com"


def test_failure_is_returned_and_retried_next_tick(env):
    s = _due(env)
    at = datetime(2026, 11, 16, 9, 0)
    assert notify.maybe_send_digest(s, at, sender=FakeSender(fail=True), keychain=lambda e: "pw").startswith("error")
    assert notify.maybe_send_digest(s, at, sender=FakeSender(), keychain=lambda e: "pw") == "sent"


def test_disabled_and_nothing_to_send(env):
    s = _due(env)
    at = datetime(2026, 11, 16, 9, 0)
    s.pipeline["notify"]["enabled"] = False
    assert notify.maybe_send_digest(s, at, sender=FakeSender(), keychain=lambda e: "pw") == "disabled"
    s.pipeline["notify"]["enabled"] = True
    s.pipeline["notify"]["email"] = None
    assert notify.maybe_send_digest(s, at, sender=FakeSender(), keychain=lambda e: "pw") == "no_email"


def test_nothing_sent_when_all_empty(env):
    s, _ = env
    snd = FakeSender()
    assert notify.maybe_send_digest(s, datetime(2026, 11, 16, 9, 0), sender=snd, keychain=lambda e: "pw") == "empty"
    assert snd.sent == []


def test_keychain_uses_security_binary_and_never_leaks(monkeypatch):
    calls = []

    class R:
        returncode, stdout, stderr = 0, "secret-pw\n", ""

    monkeypatch.setattr(notify.subprocess, "run", lambda cmd, **k: calls.append(cmd) or R())
    assert notify.keychain_password("me@example.com") == "secret-pw"
    assert calls[0][:2] == ["security", "find-generic-password"] and "-w" in calls[0]


def test_keychain_missing_gives_clear_error(monkeypatch):
    class R:
        returncode, stdout, stderr = 44, "", "not found"

    monkeypatch.setattr(notify.subprocess, "run", lambda cmd, **k: R())
    with pytest.raises(notify.NotifyError, match="notify setup"):
        notify.keychain_password("me@example.com")


def test_store_password_lets_security_prompt_so_we_never_see_it(monkeypatch):
    seen = {}

    class R:
        returncode = 0

    monkeypatch.setattr(notify.subprocess, "run", lambda cmd, **k: seen.update(cmd=cmd, kw=k) or R())
    notify.store_password("me@example.com")
    assert seen["cmd"][-1] == "-w" and "-U" in seen["cmd"] and "capture_output" not in seen["kw"]


def test_cli_digest_dry_run_prints_body_and_test_sends(env, monkeypatch, capsys):
    from careeros.cli import main

    s = _due(env)
    sent = FakeSender()
    monkeypatch.setattr("careeros.cli._settings", lambda a: s)
    monkeypatch.setattr(notify, "smtp_send", sent)
    monkeypatch.setattr(notify, "keychain_password", lambda e: "pw")
    assert main(["notify", "digest", "--dry-run"]) == 0
    assert "Reach out" in capsys.readouterr().out and sent.sent == []
    assert main(["notify", "test"]) == 0
    assert len(sent.sent) == 1


def test_tick_sends_digest_and_survives_failure(env, monkeypatch):
    from careeros.runs import tick as t

    s = _due(env)
    monkeypatch.setattr(notify, "keychain_password", lambda e: "pw")
    monkeypatch.setattr(notify, "smtp_send", FakeSender(fail=True))
    out: dict = {}
    t._notify(s, out, lambda m: None, datetime(2026, 11, 16, 9, 0))
    assert out["notify"].startswith("error")


def test_weekly_digest_only_on_its_day_and_off_never(env):
    s = _due(env)
    s.pipeline["notify"]["digest"] = "weekly"
    s.pipeline["notify"]["weekly_day"] = "tue"
    mon, tue = datetime(2026, 11, 16, 9, 0), datetime(2026, 11, 17, 9, 0)
    assert notify.maybe_send_digest(s, mon, sender=FakeSender(), keychain=lambda e: "pw") == "not_today"
    assert notify.maybe_send_digest(s, tue, sender=FakeSender(), keychain=lambda e: "pw") == "sent"
    s.pipeline["notify"]["digest"] = "off"
    assert notify.maybe_send_digest(s, datetime(2026, 11, 18, 9, 0), sender=FakeSender(), keychain=lambda e: "pw") == "disabled"


def test_urgent_sends_immediately_once_per_key_and_can_be_off(env):
    s, _ = env
    snd, kc = FakeSender(), lambda e: "pw"
    assert notify.send_urgent(s, "match:abc", "Big match at Nimbus", "link", sender=snd, keychain=kc) == "sent"
    assert notify.send_urgent(s, "match:abc", "Big match at Nimbus", "link", sender=snd, keychain=kc) == "already_sent"
    assert notify.send_urgent(s, "match:def", "Another", "x", sender=snd, keychain=kc) == "sent"
    assert [m[1] for m in snd.sent] == ["Urgent: Big match at Nimbus", "Urgent: Another"]
    s.pipeline["notify"]["urgent"] = False
    assert notify.send_urgent(s, "match:ghi", "z", "z", sender=snd, keychain=kc) == "disabled"


def test_urgent_failure_is_retried_and_digest_state_survives(env):
    s = _due(env)
    kc = lambda e: "pw"  # noqa: E731
    assert notify.send_urgent(s, "k", "s", "b", sender=FakeSender(fail=True), keychain=kc).startswith("error")
    assert notify.send_urgent(s, "k", "s", "b", sender=FakeSender(), keychain=kc) == "sent"
    at = datetime(2026, 11, 16, 9, 0)
    assert notify.maybe_send_digest(s, at, sender=FakeSender(), keychain=kc) == "sent"
    assert notify.send_urgent(s, "k", "s", "b", sender=FakeSender(), keychain=kc) == "already_sent"
