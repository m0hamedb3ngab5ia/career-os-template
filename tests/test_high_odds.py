"""REQ-161 fresh first, REQ-162 outreach QA gate + your line, REQ-163 volume yields to outreach."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from careeros import high_odds as h
from careeros.models import Posting, Score
from careeros.runs.ranking import Candidate, score_candidate
from careeros.store import Store
from careeros.tracker import Tracker, add_action

pytestmark = pytest.mark.unit
NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
W = {"freshness_weight": 60, "fresh_hours": 48, "stale_days": 30, "dream_bonus": 0, "deadline_bonus": 0,
     "deadline_days": 7, "fit_weight": 0, "retry_bonus": 0, "fresh_boost": 20, "fresh_boost_hours": 72}


def _job(s, n, fit, hours):
    p = Posting(company="Initech", title=f"Eng {n}", ats="greenhouse", ats_job_id=str(n), description_text="x",
                url=f"https://e.com/{n}", posted_at=(NOW - timedelta(hours=hours)).isoformat())
    Store(s).save_posting(p)
    Store(s).save_score(Score(job_id=p.job_id, category="swe", fit=fit))
    return p


def test_fresh_boost_only_within_window():
    def pts(hrs):
        return score_candidate(Candidate("a", "C", "T", "queued", NOW - timedelta(hours=hrs), None, False, 80), W, NOW, "prepare")
    assert pts(60)[0] - pts(80)[0] > 20 - 1 and any("fresh boost" in x for x in pts(60)[1])
    assert not any("fresh boost" in x for x in pts(80)[1])


def test_scan_fresh_emails_once_for_fresh_fitting_job(settings):
    Tracker(settings=settings).init()
    old = _job(settings, 0, 90, 5)
    assert h.scan_fresh(settings, NOW, send=lambda *x, **k: "sent") == []  # first run: baseline, no flood
    a, _b, _c = _job(settings, 1, 90, 10), _job(settings, 2, 90, 100), _job(settings, 3, 40, 10)
    calls = []
    got = h.scan_fresh(settings, NOW, send=lambda *x, **k: calls.append(x[1]) or "sent")
    assert got == [a.job_id] and calls == [f"job:{a.job_id}"] and old.job_id not in got


def test_age_ignores_fetched_at():
    p = Posting(company="C", title="T", ats="greenhouse", ats_job_id="1", description_text="x", url="https://e.com/1",
                fetched_at=NOW.isoformat())
    assert h.age_hours(p, NOW) is None


def test_fresh_watched_job_emails_once(settings, monkeypatch):
    from careeros import notify
    from careeros.watch import scan_watch

    Tracker(settings=settings).init()
    settings.companies["dream_list"] = ["Initech"]
    monkeypatch.setattr(notify, "config", lambda s: {"enabled": True, "urgent": True, "email": "me@x.com"})
    mails = []
    monkeypatch.setattr(notify, "smtp_send", lambda *a, **k: mails.append(a[1]))
    monkeypatch.setattr(notify, "keychain_password", lambda e: "pw")
    scan_watch(settings)
    h.scan_fresh(settings, NOW)  # baselines
    p = _job(settings, 5, 95, 2)
    h.scan_fresh(settings, NOW)
    scan_watch(settings)
    assert len(mails) == 1
    assert notify.send_urgent(settings, f"job:{p.job_id}", "x", "y") == "already_sent"


GOOD = {"contact": "Sam", "to": "s@x.com", "email": {"subject": "Hi", "body": "I built a stock reconciler. Would you point me to the right person?"},
        "facts_used": [{"fact": "ships daily", "source": "posting"}], "bullet_ids": ["b1"]}


def test_gate_flags_slop_and_requires_your_line():
    bad = {**GOOD, "email": {**GOOD["email"], "body": "I hope this finds you well. " + "word " * 130}, "facts_used": []}
    probs = h.draft_problems(bad, ["I hope this finds you well"])
    assert any("too long" in p for p in probs) and any("banned" in p for p in probs) and any("fact" in p for p in probs)
    d = dict(GOOD)
    data = {"drafts": [d]}
    assert h.gate_outreach(data, []) == [] and d["qa_pass"] is True and d["ready"] is False and d["your_line"] == ""
    assert h.compose_url(d) is None
    d["your_line"] = "I also ran a similar migration."
    d["ready"] = h.draft_ready(d)
    assert d["ready"] and h.compose_url(d).startswith("https://mail.google.com/mail/?view=cm") and "to=s%40x.com" in h.compose_url(d)


def test_compose_falls_back_to_email_to_and_fact_source():
    d = {**GOOD, "ready": True, "your_line": "hi"}
    del d["to"]
    d["email"] = {**d["email"], "to": "e@x.com"}
    assert "to=e%40x.com" in h.compose_url(d)
    legacy = {**GOOD, "facts_used": [], "fact_source": "posting"}
    assert h.draft_problems(legacy, []) == []


def _reach(s, jid, due):
    return add_action(s, f"Reach out {jid}", "follow_up", job_id=jid, detail="reach_out", priority="H", due=due.isoformat(), id=jid)


def test_reach_first_item_raised_and_closed(settings):
    Tracker(settings=settings).init()
    today = date(2026, 11, 16)
    for i in range(4):
        _reach(settings, f"r{i}", today - timedelta(days=3))
    assert len(h.raise_reach_first(settings, today)) == 1 and h.raise_reach_first(settings, today) == []
    open_ = [i for i in Tracker(settings=settings).list_action_items(open_only=True) if "reach_first" in str(i.get("Detail"))]
    assert len(open_) == 1
    for i in range(3):
        Tracker(settings=settings).mark_action_done(f"r{i}")
    h.raise_reach_first(settings, today)
    assert not [i for i in Tracker(settings=settings).list_action_items(open_only=True) if "reach_first" in str(i.get("Detail"))]


def test_digest_leads_with_reach_first_and_has_why(settings):
    from careeros import notify

    Tracker(settings=settings).init()
    today = date(2026, 11, 16)
    for i in range(4):
        _reach(settings, f"r{i}", today - timedelta(days=3))
    h.raise_reach_first(settings, today)
    body = notify.build_digest(settings, today)
    assert body.startswith("Reach out before applying to more") and "40%" in body


def test_cli_outreach_qa_records_line_and_prints_link(settings, monkeypatch, capsys):
    import argparse
    import json

    from careeros import cli

    p = _job(settings, 9, 90, 5)
    path = Store(settings).job_dir(p.job_id) / "outreach.json"
    path.write_text(json.dumps({"drafts": [dict(GOOD)]}))
    monkeypatch.setattr(cli, "_settings", lambda a: settings)
    ns = argparse.Namespace(job_id=p.job_id, contact=None, line=None)
    assert cli.cmd_outreach_qa(ns) == 0 and "needs your line" in capsys.readouterr().out
    ns.line = "I ran a similar migration."
    assert cli.cmd_outreach_qa(ns) == 0 and "send: https://mail.google.com" in capsys.readouterr().out
    assert json.loads(path.read_text())["drafts"][0]["ready"] is True


def test_reach_first_stays_open_across_ticks_and_reraises(settings):
    from careeros.follow_ups import raise_follow_ups

    tr = Tracker(settings=settings)
    tr.init()
    today = date(2026, 11, 16)
    for i in range(4):
        _reach(settings, f"r{i}", today - timedelta(days=3))
    h.raise_reach_first(settings, today)
    raise_follow_ups(settings, today)
    raise_follow_ups(settings, today)
    h.raise_reach_first(settings, today)

    def rf():
        return [i for i in tr.list_action_items(open_only=True) if "reach_first" in str(i.get("Detail"))]
    assert len(rf()) == 1
    for i in range(3):
        tr.mark_action_done(f"r{i}")
    h.raise_reach_first(settings, today)
    assert not rf()
    for i in range(3):
        tr.reopen_action(f"r{i}")
    assert len(h.raise_reach_first(settings, today)) == 1 and len(rf()) == 1


def test_send_kit_links_and_copy_blocks():
    """One block per unsent draft: LinkedIn people-search link (never automated), the note to paste, the Gmail
    link once the draft is ready, and the one command that records the send."""
    out = {"company": "Garage", "drafts": [
        {"contact": "Alaz Sengul", "role": "hiring_manager", "linkedin": None, "linkedin_note": "Hi, I applied.",
         "email": {"subject": "S", "body": "B"}, "to": "a@x.com", "ready": True, "your_line": "Mine."},
        {"contact": "Recruiter (unnamed)", "linkedin_note": "Hi there.", "email": {"subject": "S", "body": "B"}},
        {"contact": "Old", "linkedin_note": "x", "sent": True}]}
    contacts = {"search_urls": {"recruiter": "https://www.linkedin.com/search/results/people/?keywords=Garage%20recruiter"}}
    kit = h.send_kit("j1", "Software Engineer", out, contacts)
    assert "keywords=Alaz%20Sengul%20Garage" in kit and "```\nHi, I applied.\n```" in kit
    assert "https://mail.google.com/mail/?view=cm" in kit and "to=a%40x.com" in kit
    assert 'careeros outreach sent j1 --contact "Alaz Sengul"' in kit
    assert "keywords=Garage%20recruiter" in kit and "needs your line" in kit
    assert "Old" not in kit


def test_send_kit_referral_uses_the_message_and_flags_manual_tailor():
    out = {"company": "Acme", "drafts": [{"contact": "Pat Kim", "role": "referral", "linkedin_degree": 1,
                                          "linkedin_message": "Hey Pat, would you refer me?", "manual_tailor": True,
                                          "manual_reason": "connected"}]}
    kit = h.send_kit("j2", "SWE", out, {})
    assert "Message, paste:" in kit and "Hey Pat, would you refer me?" in kit and "Connect" not in kit
    assert "Tailor by hand before sending (connected)" in kit


def test_compose_puts_your_line_after_the_greeting_once():
    """The candidate's line goes after "Hi Sam," (not above it), and is not repeated when the body already has it."""
    from urllib.parse import unquote
    d = {**GOOD, "ready": True, "your_line": "Fellow alum here.",
         "email": {"subject": "S", "body": "Hi Sam,\n\nAsk."}}
    assert unquote(h.compose_url(d).split("&body=")[1]) == "Hi Sam,\n\nFellow alum here.\n\nAsk."
    d["email"]["body"] = "Hi Sam,\n\nFellow alum here. Ask."
    assert unquote(h.compose_url(d).split("&body=")[1]) == "Hi Sam,\n\nFellow alum here. Ask."


def test_shared_network_draft_needs_no_bullet_id():
    """A note to a fellow alum leads with the overlap and attaches the résumé, so it may skip the experience proof."""
    d = {k: v for k, v in GOOD.items() if k != "bullet_ids"}
    assert "no profile bullet id" in h.draft_problems(d, [])
    assert h.draft_problems({**d, "shared_network": "State University alum"}, []) == []


def test_mail_app_link_for_iphone():
    """iPhone: a mailto: link opens the default mail app with to/subject/body typed in (the Claude app taps it;
    custom app schemes stay dead). Attachments can't ride a link, so the kit says to attach the résumé."""
    from urllib.parse import unquote
    d = {**GOOD, "ready": True, "your_line": "Mine.", "email": {"subject": "S 1", "body": "Hi Sam,\n\nAsk."}}
    m = h.compose_url(d, mail=True)
    assert m.startswith("mailto:s%40x.com?subject=S%201&body=")
    assert unquote(m.split("&body=")[1]) == unquote(h.compose_url(d).split("&body=")[1])
    assert h.compose_url({**d, "ready": False}, mail=True) is None
    kit = h.send_kit("j1", "SWE", {"drafts": [{**d, "contact": "Sam", "linkedin_note": "x"}]}, {})
    assert "[Mail](mailto:" in kit and "[Gmail](https://mail.google.com" in kit and "attach" in kit.lower()


def test_word_limit_skips_the_signature():
    """The candidate's template signs off with name and LinkedIn; only the message counts toward the limit."""
    msg = " ".join(["word"] * 118)
    d = {**GOOD, "email": {"subject": "S", "body": f"Hi Sam,\n\n{msg}\n\nThank you,\nAlex Example\n555-0100\nhttps://linkedin.com/in/x"}}
    assert h.draft_problems(d, []) == []
    d["email"]["body"] = f"Hi Sam,\n\n{msg} two more words\n\nThank you,\nAlex Example"
    assert any("too long" in p for p in h.draft_problems(d, []))


def test_a_long_closing_paragraph_starting_with_thanks_still_counts():
    """Only a short sign-off line is skipped; a long last paragraph that opens with "Thank you" is message."""
    msg = " ".join(["word"] * 100)
    long_close = "Thank you " + " ".join(["more"] * 40)
    d = {**GOOD, "email": {"subject": "S", "body": f"Hi Sam,\n\n{msg}\n\n{long_close}\n\nBest,\nAlex Example"}}
    assert any("too long" in p for p in h.draft_problems(d, []))


def test_fresh_urgent_failure_is_retried_next_tick(settings):
    """A failed urgent send must not mark the job seen; the next tick sends it."""
    Tracker(settings=settings).init()
    h.scan_fresh(settings, NOW, send=lambda *x, **k: "sent")  # baseline
    a = _job(settings, 1, 90, 10)
    assert h.scan_fresh(settings, NOW, send=lambda *x, **k: "error: SMTPException: down") == []
    assert h.scan_fresh(settings, NOW, send=lambda *x, **k: "sent") == [a.job_id]
