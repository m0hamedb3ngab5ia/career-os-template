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
    assert "Reach out" in body and "Engineer 1, Nimbus: https://example.com/1" in body
    assert "Applied 14 days ago" in body and "0 days" not in body and "Needs you" in body and "Upload transcript" in body
    assert "Follow up" not in body                       # empty section omitted
    assert p.job_id not in body


def test_digest_none_when_everything_empty(env):
    s, _ = env
    assert notify.build_digest(s, TODAY) is None


class FakeSender:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def __call__(self, cfg, subject, body, password, html=None):
        if self.fail:
            raise OSError("smtp down")
        self.html = html
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


def _scored_job(settings, tr, n, fit, status="queued", closes=None, qa=None, found="2026-11-15"):
    p = Posting(company=f"Co{n}", title=f"Role {n}", ats="greenhouse", ats_job_id=f"s{n}", description_text="x",
                url=f"https://example.com/s{n}", closes_at=closes)
    st = Store(settings)
    st.save_posting(p)
    tr.upsert_jobs([{"job_id": p.job_id, "company": p.company, "title": p.title, "status": status, "fit": fit,
                     "date_found": found}])
    if qa is not None:  # what qa-review writes
        (st.job_dir(p.job_id) / "qa.json").write_text(json.dumps({"pass": qa, "fail_reasons": []}))
    return p


def test_apply_section_best_fit_first_capped_ready_marker_and_excludes(env):
    s, tr = env
    s.pipeline["notify"]["apply_max"] = 2
    _scored_job(s, tr, 1, 70)
    _scored_job(s, tr, 2, 90, qa=True)
    _scored_job(s, tr, 3, 80, status="prepared")
    _scored_job(s, tr, 4, 99, status="applied")
    _scored_job(s, tr, 5, 99, status="skipped")
    _scored_job(s, tr, 6, 99, closes="2026-11-01")          # posting already closed
    body = notify.build_digest(s, TODAY)
    assert "Apply to these" in body and "+1 more: open Today" in body
    assert body.index("Role 2") < body.index("Role 3") and "Role 1" not in body
    assert "https://example.com/s2" in body and "ready" in body.split("Role 3")[0]
    assert "Role 4" not in body and "Role 5" not in body and "Role 6" not in body


def test_apply_section_keeps_reminding_and_lists_new_jobs_first(env):
    s, tr = env
    _scored_job(s, tr, 1, 90)
    at = datetime(2026, 11, 16, 9, 0)
    assert notify.maybe_send_digest(s, at, sender=FakeSender(), keychain=lambda e: "pw") == "sent"
    _scored_job(s, tr, 2, 60)
    body = notify.build_digest(s, date(2026, 11, 17))
    assert body.index("Role 2") < body.index("Role 1")             # new first, though lower fit
    assert "fit 60" in body and "fit 90" in body and "Found today" not in body            # not applied yet: still listed


def test_ready_marker_reads_qa_review_pass_flag(env):
    s, tr = env
    _scored_job(s, tr, 1, 90, qa=False)
    assert "ready" not in notify.build_digest(s, TODAY)


def test_deadlines_section_soonest_first_and_window(env):
    s, tr = env
    s.pipeline["notify"]["deadline_days"] = 7
    _scored_job(s, tr, 1, 70, closes="2026-11-22")
    _scored_job(s, tr, 2, 70, closes="2026-11-19")
    _scored_job(s, tr, 3, 70, closes="2026-12-30")          # outside the window
    _scored_job(s, tr, 4, 70, status="applied", closes="2026-11-18")
    tr.add_action_item("Send transcript", type="other", priority="M", due="2026-11-20", due_reason="portal closes")
    body = notify.build_digest(s, TODAY)
    sec = body.split("Deadlines")[1].split("\n\n")[0]
    assert sec.index("Role 2") < sec.index("Send transcript") < sec.index("Role 1")
    assert "Role 3" not in sec and "Role 4" not in sec and "in 3 days" in sec


def test_sections_ordered_follow_up_deadlines_apply_needs_you(env):
    s, tr = env
    p = _job(s, tr, 1, applied="2026-11-02")
    tr.add_action_item("Reply to recruiter", type="follow_up", job_id=p.job_id, priority="M", detail="follow_up:applied")
    _scored_job(s, tr, 2, 80, closes="2026-11-18")
    tr.add_action_item("Upload transcript", type="other", priority="H")
    body = notify.build_digest(s, TODAY)
    heads = [h for h in ("Follow up", "Deadlines", "Apply to these", "Needs you") if h in body]
    assert heads == sorted(heads, key=body.index) and len(heads) == 4


def test_every_days_cadence(env):
    s, tr = env
    s.pipeline["notify"]["every_days"] = 3
    _scored_job(s, tr, 1, 80)
    snd, kc = FakeSender(), lambda e: "pw"
    assert notify.maybe_send_digest(s, datetime(2026, 11, 16, 9), sender=snd, keychain=kc) == "sent"
    _scored_job(s, tr, 2, 80)
    assert notify.maybe_send_digest(s, datetime(2026, 11, 18, 9), sender=snd, keychain=kc) == "not_today"
    assert notify.maybe_send_digest(s, datetime(2026, 11, 19, 7), sender=snd, keychain=kc) == "too_early"
    assert notify.maybe_send_digest(s, datetime(2026, 11, 19, 9), sender=snd, keychain=kc) == "sent"
    s.pipeline["notify"]["digest"] = "off"
    assert notify.maybe_send_digest(s, datetime(2026, 11, 25, 9), sender=snd, keychain=kc) == "disabled"


def test_html_part_subject_and_escaping(env):
    s, tr = env
    _scored_job(s, tr, 1, 85, qa=True)
    p = _scored_job(s, tr, 2, 80)
    tr.upsert_jobs([{"job_id": p.job_id, "title": "R&D <b>Lead</b>"}])
    Store(s).save_posting(p.model_copy(update={"title": "R&D <b>Lead</b>"}))
    tr.add_action_item("Upload transcript", type="other", priority="H")
    snd = FakeSender()
    assert notify.maybe_send_digest(s, datetime(2026, 11, 16, 9), sender=snd, keychain=lambda e: "pw") == "sent"
    subject = snd.sent[0][1]
    assert subject.startswith("career-os: ") and "2 jobs to apply to" in subject and "1 task waiting on you" in subject
    h = snd.html
    assert "<table" in h and 'href="https://example.com/s1"' in h and "R&amp;D &lt;b&gt;" in h and "<b>Lead" not in h
    assert "max-width:600px" in h and "prefers-color-scheme: dark" in h and "http://" not in h.replace("https://", "").replace("http://127.0.0.1", "")
    assert "<img" not in h and "<link" not in h


def test_smtp_send_is_multipart_alternative(env, monkeypatch):
    s, _ = env
    got = {}

    class SM:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self): pass
        def login(self, *a): pass
        def send_message(self, m): got["m"] = m

    monkeypatch.setattr(notify.smtplib, "SMTP", SM)
    notify.smtp_send(notify.config(s), "subj", "plain body", "pw", html="<p>hi</p>")
    m = got["m"]
    assert m.get_content_type() == "multipart/alternative"
    assert m.get_body(("plain",)).get_content().strip() == "plain body"
    assert "<p>hi</p>" in m.get_body(("html",)).get_content()


def test_cli_digest_html_file(env, monkeypatch, tmp_path):
    from careeros.cli import main

    s, tr = env
    _scored_job(s, tr, 1, 85)
    monkeypatch.setattr("careeros.cli._settings", lambda a: s)
    out = tmp_path / "d.html"
    assert main(["notify", "digest", "--dry-run", "--html", str(out)]) == 0
    assert "Role 1" in out.read_text()


# ---- brief digest (REQ-155): one row per job, grouped Needs you, caps, LinkedIn-alert look -------------------------
def _outreach(s, p, *names, sent_at="2026-11-14", fu7=None, fu7_sent=None, replied=False):
    drafts = [{"contact": n, "to": "x@example.com", "sent": True, "sent_at": sent_at, "followup_7d": fu7,
               "followup_7d_sent_at": fu7_sent, "replied": replied} for n in names]
    (Store(s).job_dir(p.job_id) / "outreach.json").write_text(json.dumps({"drafts": drafts}))


def _follow_items(s, tr, p):
    from careeros.follow_ups import raise_follow_ups
    raise_follow_ups(s, TODAY)


def test_follow_up_one_row_per_job_merges_applied_and_outreach(env):
    s, tr = env
    p = _job(s, tr, 1, applied="2026-11-04")
    _outreach(s, p, "Tom Rickards", sent_at="2026-11-14")
    s.pipeline.setdefault("follow_ups", {})["after_days"] = 2
    _follow_items(s, tr, p)
    assert len([i for i in tr.list_action_items() if i["Type"] == "follow_up"]) == 2     # two nudges, same job
    (sec,) = [x for x in notify.build_sections(s, TODAY) if x.key == "follow"]
    assert len(sec.rows) == 1 and sec.rows[0].title == "Engineer 1"
    assert sec.rows[0].note == "Applied 4 Nov \u00b7 emailed Tom Rickards 14 Nov \u00b7 no reply (2 days)"


def test_follow_up_applied_only_subtitle_ready_chip_and_order(env):
    s, tr = env
    s.pipeline["follow_ups"] = {"after_days": 2}
    a = _job(s, tr, 1, applied="2026-11-10")                  # applied-only, 6 days
    b = _job(s, tr, 2, applied="2026-11-12")                  # outreach, 4 days, follow-up text ready
    c = _job(s, tr, 3, applied="2026-11-01")                  # outreach, 10 days
    _outreach(s, b, "Ann Lee", "Bo Chen", sent_at="2026-11-12", fu7="Hi again")
    _outreach(s, c, "Cy Day", sent_at="2026-11-06")
    _follow_items(s, tr, a)
    (sec,) = [x for x in notify.build_sections(s, TODAY) if x.key == "follow"]
    assert [r.title for r in sec.rows] == ["Engineer 3", "Engineer 2", "Engineer 1"]       # outreach first, longest wait first
    assert sec.rows[2].note == "Applied 10 Nov \u00b7 no reply (6 days)" and sec.rows[2].chips == []
    assert sec.rows[1].chips == ["follow-up ready"] and sec.rows[0].chips == []
    assert sec.rows[1].note == "Applied 12 Nov \u00b7 emailed Ann Lee, Bo Chen 12 Nov \u00b7 no reply (4 days)"


def test_reach_out_shows_days_since_applied_and_skips_jobs_in_follow_up(env):
    s, tr = env
    s.pipeline["follow_ups"] = {"after_days": 2}
    a = _job(s, tr, 1, applied="2026-11-10")
    b = _job(s, tr, 2, applied="2026-11-15")
    raise_reach_outs(s, TODAY)                                # items due today: the old "0 days" bug
    _follow_items(s, tr, a)                                   # a also has an applied nudge
    secs = {x.key: x for x in notify.build_sections(s, TODAY)}
    assert [r.title for r in secs["follow"].rows] == ["Engineer 1"]
    assert [r.title for r in secs["reach"].rows] == ["Engineer 2"]
    assert secs["reach"].rows[0].note == "Applied 1 day ago \u00b7 no contact yet"


def _needs(tr, type_, n, what="x", job_id=""):
    for i in range(n):
        tr.add_action_item(f"{what} {i}" if n > 1 else what, type=type_, job_id=job_id, priority="L")


def test_needs_you_groups_by_type_with_counts_most_urgent_first(env):
    s, tr = env
    for n in range(1, 6):
        p = _scored_job(s, tr, n, 80, status="needs_review")
        tr.add_action_item("Review and submit", type="review", job_id=p.job_id, priority="M")
    _needs(tr, "question", 7)
    _needs(tr, "injection_suspected", 18, "Possible prompt injection")
    _needs(tr, "qa_fail", 3)
    _needs(tr, "scam_suspected", 2)
    _needs(tr, "ghost_job", 4)
    _needs(tr, "other", 2)
    (sec,) = [x for x in notify.build_sections(s, TODAY) if x.key == "needs"]   # priority M beats L, then type order
    assert [r.title for r in sec.rows] == [
        "5 applications ready for your review: Co1, Co2, Co3 +2", "2 scam warnings", "3 QA failures to decide",
        "18 postings with hidden text to check", "7 form questions to answer"] and sec.more == 2
    assert sec.count == 2 + 5 + 3 + 18 + 7 + 4 + 2 and len(sec.rows) <= 6


def test_needs_you_single_item_text_is_shortened_to_one_line(env):
    s, tr = env
    tr.add_action_item("Upload the transcript to the portal. " * 6, type="other", priority="L")
    (sec,) = [x for x in notify.build_sections(s, TODAY) if x.key == "needs"]
    assert sec.rows[0].title.startswith("Upload the transcript") and len(sec.rows[0].title) <= 90
    assert sec.rows[0].title.endswith("\u2026") and "\n" not in sec.rows[0].title


def test_section_max_caps_every_section_with_more_line(env):
    s, tr = env
    s.pipeline["notify"]["section_max"] = 2
    for n in range(1, 6):
        _scored_job(s, tr, n, 50 + n, closes=f"2026-11-{17 + n}")
    secs = {x.key: x for x in notify.build_sections(s, TODAY)}
    assert len(secs["apply"].rows) == 2 and secs["apply"].more == 3 and secs["apply"].count == 5
    assert len(secs["deadlines"].rows) == 2 and secs["deadlines"].more == 3
    text = notify.render_text(list(secs.values()))
    assert text.count("+3 more: open Today (`careeros ui`)") == 2
    assert "5 jobs to apply to" in notify.subject_for(list(secs.values()))     # subject counts all, not shown
    assert notify.config(s)["section_max"] == 2
    del s.pipeline["notify"]["section_max"]
    assert notify.config(s)["section_max"] == 5


def test_html_looks_like_a_job_alert(env):
    s, tr = env
    p = _scored_job(s, tr, 1, 87, qa=True, closes="2026-11-19")
    Store(s).save_posting(p.model_copy(update={"location": "Austin, TX", "remote": True}))
    s.pipeline["notify"]["every_days"] = 3
    secs = notify.build_sections(s, TODAY)
    h = notify.render_html(secs, TODAY, footer=notify.footer(notify.config(s)))
    assert "Your job search today" in h and "Mon 16 Nov 2026" in h
    assert 'href="https://example.com/s1"' in h and ">Role 1</a>" in h and "font-size:16px" in h
    assert "Co1 &middot; Austin, TX" in h and ">CO<" in h and "border-radius" in h and "fit 87" in h
    assert "closes in 3 days" in h and "ready" in h
    assert "Sent every 3 days by career-os. Change it in pipeline.yaml notify.every_days." in h
    assert ">https://example.com/s1<" not in h and "<img" not in h


def test_badge_colour_is_stable_and_readable():
    def lum(hex_):
        ch = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        ch = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in ch]
        return .2126 * ch[0] + .7152 * ch[1] + .0722 * ch[2]

    assert notify.badge_colour("Acme") == notify.badge_colour("Acme") != notify.badge_colour("Zed Corp")
    for i in range(400):
        assert 1.05 / (lum(notify.badge_colour(f"Company {i}")) + .05) >= 4.5
    assert notify.initials("Jane Street") == "JS" and notify.initials("OpenAI") == "OP" and notify.initials("") == "?"


def test_text_body_one_link_per_job_and_no_bare_urls_elsewhere(env):
    s, tr = env
    _scored_job(s, tr, 1, 80)
    body = notify.build_digest(s, TODAY)
    assert body.count("https://") == 1 and "- Role 1, Co1: https://example.com/s1" in body


def test_subject_stays_short_with_big_counts(env):
    secs = [notify.Section("follow", "Follow up", [notify.Row("a")], count=123),
            notify.Section("deadlines", "Deadlines", [notify.Row("a")], count=45),
            notify.Section("apply", "Apply to these", [notify.Row("a")], count=678),
            notify.Section("needs", "Needs you", [notify.Row("a")], count=999)]
    assert len(notify.subject_for(secs)) <= 60


def test_unscored_job_has_no_fit_chip_and_long_location_is_shortened(env):
    s, tr = env
    s.targets["location"] = {}
    p = _scored_job(s, tr, 1, None)
    p.location = "San Juan, Puerto Rico, New York, NY, District of Columbia, Europe | Spain"
    Store(s).save_posting(p)
    body = notify.build_digest(s, TODAY)
    assert "fit 0" not in body and "fit None" not in body
    assert "San Juan, Puerto Rico and more" in body and "Spain" not in body


# ---- digest answers the reader's questions: why, where to click, how fresh, which office -------------------------
def test_follow_up_row_states_basis_dates_and_next_action(env):
    s, tr = env
    s.pipeline["follow_ups"] = {"after_days": 2}
    b = _job(s, tr, 2, applied="2026-11-04")
    _outreach(s, b, "Ann Lee", sent_at="2026-11-12", fu7="Hi again")
    a = _job(s, tr, 1, applied="2026-11-10")
    _follow_items(s, tr, a)
    (sec,) = [x for x in notify.build_sections(s, TODAY) if x.key == "follow"]
    out, app = sec.rows
    assert out.note == "Applied 4 Nov · emailed Ann Lee 12 Nov · no reply (4 days)"
    assert out.action == "" and "follow-up ready" in out.chips          # drafted: the section note says how, once
    assert "send the follow-ups" in sec.note
    assert app.note == "Applied 10 Nov · no reply (6 days)" and "draft" in app.action.lower()
    assert "applied" in sec.note.lower() and "no reply" in sec.note.lower()
    text = notify.render_text([sec], TODAY)
    assert "Applied 4 Nov" in text and "send the follow-ups" in text


def test_needs_you_rows_have_an_action_and_a_today_link(env):
    s, tr = env
    _needs(tr, "question", 7)
    _needs(tr, "injection_suspected", 3)
    secs = notify.build_sections(s, TODAY)
    (sec,) = [x for x in secs if x.key == "needs"]
    assert all(r.action for r in sec.rows)
    assert "answer" in sec.rows[1].action.lower() and "chat" in sec.rows[1].action.lower()
    assert "http://127.0.0.1:8765" in sec.note and "laptop" in sec.note
    assert "http://127.0.0.1:8765" in notify.render_text(secs, TODAY)
    s.pipeline["ui"] = {"port": 9000}
    assert "http://127.0.0.1:9000" in notify.build_digest(s, TODAY)
    summary = notify._summary(secs)
    assert "10 tasks waiting on you" in summary


def test_apply_row_shows_posted_and_found_dates_not_a_bare_new_chip(env):
    s, tr = env
    p = _scored_job(s, tr, 1, 80, found="2026-11-16")
    Store(s).save_posting(p.model_copy(update={"posted_at": "2026-11-12T09:00:00Z"}))
    q = _scored_job(s, tr, 2, 70, found="2026-11-14")          # ATS gave no posted date
    (sec,) = [x for x in notify.build_sections(s, TODAY) if x.key == "apply"]
    notes = {r.title: r.note for r in sec.rows}
    assert notes["Role 1"] == "Posted 12 Nov (4 days ago) · found today"
    assert notes["Role 2"] == "Found 14 Nov (2 days ago)"
    assert all("new" not in r.chips for r in sec.rows)


def test_location_shows_the_candidate_preferred_office(env):
    s, tr = env
    s.targets["location"] = {"preferred": ["Boston MA", "Seattle WA"], "preferred_regions": ["US"], "remote_ok": True}
    p = _scored_job(s, tr, 1, 80)
    Store(s).save_posting(p.model_copy(update={"location": "San Francisco, CA; Seattle, WA; New York, NY"}))
    q = _scored_job(s, tr, 2, 70)
    Store(s).save_posting(q.model_copy(update={"location": "Austin, TX; Denver, CO"}))
    r = _scored_job(s, tr, 3, 60)
    Store(s).save_posting(r.model_copy(update={"location": "Chicago, IL", "remote": True}))
    (sec,) = [x for x in notify.build_sections(s, TODAY) if x.key == "apply"]
    loc = {r_.title: r_.location for r_ in sec.rows}
    assert loc["Role 1"] == "Seattle, WA · +2 other offices"
    assert loc["Role 2"] == "Austin, TX · +1 other office"           # nothing preferred: first one
    assert loc["Role 3"] == "Chicago, IL (remote)"


def test_city_list_without_states_shows_the_preferred_city(env):
    s, tr = env
    s.targets["location"] = {"preferred": ["New York NY"]}
    p = _job(s, tr, 1, applied="2026-11-10")
    p.location = "San Francisco, Seattle, New York"
    assert notify._place(p, s) == "New York, NY · +2 other offices"


def test_needs_you_urgent_types_first_and_every_type_has_its_own_action(env):
    from careeros.models import ACTION_TYPES
    s, tr = env
    for k in range(3):
        tr.add_action_item(f"Answer q{k}", type="question", priority="L")
    tr.add_action_item("Solve captcha", type="captcha", priority="H", due="2026-11-15")
    (sec,) = [x for x in notify.build_sections(s, TODAY) if x.key == "needs"]
    assert sec.rows[0].title == "Solve captcha"                       # overdue + high beats type order
    generic = notify._ACT["other"]
    assert all(notify._ACT.get(t, generic) != generic for t in ACTION_TYPES if t not in ("other", "follow_up"))
