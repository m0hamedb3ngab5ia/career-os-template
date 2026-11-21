"""Send panel: per draft, read it, open in the Mail app (iPhone or Mac), open a Gmail draft with the résumé attached, or send on request."""
from __future__ import annotations

import email

import pytest

from careeros import outreach_send as o

pytestmark = pytest.mark.unit
D = {"contact": "Sam Lee", "role": "hiring_manager", "to": "sam@x.com", "to_confidence": "medium", "qa_pass": True,
     "email": {"subject": "Hi Sam", "body": "Hi Sam,\n\nAsk.\n\nThank you,\nAlex"}}


def test_message_attaches_the_resume(tmp_path):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    m = o.build_message("me@x.com", D, pdf, "Alex Example")
    assert m["To"] == "sam@x.com" and m["From"] == "me@x.com" and m["Subject"] == "Hi Sam"
    parts = list(m.iter_attachments())
    assert [p.get_filename() for p in parts] == ["Alex_Example_Resume.pdf"] and parts[0].get_content() == b"%PDF-1.4 x"


def test_gmail_draft_appends_to_drafts_and_returns_a_link(tmp_path):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF")
    calls = []

    class Imap:
        def __init__(self, host): calls.append(("host", host))
        def login(self, u, p): calls.append(("login", u))
        def append(self, box, flags, when, raw):
            calls.append(("append", box, raw)); return ("OK", [b"[APPENDUID 7 42] (Success)"])
        def select(self, box): calls.append(("select", box)); return ("OK", [b"3"])
        def uid(self, cmd, uid, what): calls.append(("uid", cmd, uid)); return ("OK", [b"3 (X-GM-MSGID 255 UID 42)"])
        def logout(self): calls.append(("logout",))

    url = o.gmail_draft("me@x.com", "pw", D, pdf, "Alex Example", imap=Imap)
    box, raw = [c for c in calls if c[0] == "append"][0][1:]
    assert box == '"[Gmail]/Drafts"' and email.message_from_bytes(raw)["To"] == "sam@x.com"
    # user 2026-11-19: a search link opened an empty compose; the draft's own id opens the draft itself
    assert ("uid", "FETCH", "42") in calls and url == "https://mail.google.com/mail/u/0/#drafts?compose=ff"


def test_send_needs_explicit_yes_and_records_the_send(tmp_path):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF")
    sent = []
    d = dict(D)
    with pytest.raises(o.SendError, match="--yes"):
        o.send_now("me@x.com", "pw", d, pdf, "Alex", yes=False, smtp=lambda *a: sent.append(a))
    assert not sent and not d.get("sent")
    o.send_now("me@x.com", "pw", d, pdf, "Alex", yes=True, smtp=lambda *a: sent.append(a), today="2026-11-18")
    assert len(sent) == 1 and d["sent"] is True and d["sent_by"] == "candidate" and d["sent_via"] == "careeros"
    with pytest.raises(o.SendError, match="already sent"):
        o.send_now("me@x.com", "pw", d, pdf, "Alex", yes=True, smtp=lambda *a: sent.append(a))


def test_panel_lists_every_unsent_draft_with_four_options():
    rows = [{"n": 1, "job_id": "j1", "company": "Acme", "title": "SWE", "url": "https://e.com/1", "draft": D,
             "gmail": "https://mail.google.com/mail/u/0/#search/x"},
            {"n": 2, "job_id": "j2", "company": "Beta", "title": "SWE", "url": "https://e.com/2",
             "draft": {**D, "contact": "Held Person", "hold": True, "hold_reason": "address unverified"}, "gmail": None}]
    md = o.panel(rows)
    assert "| 1 | Sam Lee" in md and "[Read](#d1)" in md and "[Mail](mailto:sam%40x.com" in md
    assert "[Gmail](https://mail.google.com/mail/u/0/#search/x)" in md and "`send 1`" in md
    assert '<a id="d1"></a>' in md and "Ask." in md
    assert "Held Person" in md and "held: address unverified" in md and "`send 2`" not in md
    assert "bounce" in md.lower()  # the auto-send warning


def test_cli_send_refuses_without_yes(settings, monkeypatch, capsys):
    import argparse
    import json

    from careeros import cli
    from careeros.store import Store

    jd = Store(settings).job_dir("j9")
    jd.mkdir(parents=True, exist_ok=True)
    (jd / "outreach.json").write_text(json.dumps({"drafts": [dict(D)]}))
    monkeypatch.setattr(cli, "_settings", lambda a: settings)
    assert cli.cmd_outreach_send(argparse.Namespace(job_id="j9", contact="Sam Lee", yes=False)) == 1
    assert "bounce" in capsys.readouterr().err and not json.loads((jd / "outreach.json").read_text())["drafts"][0].get("sent")


def _job(settings, drafts):
    import json

    from careeros.store import Store
    jd = Store(settings).job_dir("j9")
    jd.mkdir(parents=True, exist_ok=True)
    (jd / "outreach.json").write_text(json.dumps({"drafts": drafts}))
    (jd / "resume.pdf").write_bytes(b"%PDF")
    return jd


def test_cli_send_refuses_a_held_draft(settings, monkeypatch, capsys):
    import argparse

    from careeros import cli
    jd = _job(settings, [{**D, "hold": True, "hold_reason": "address unverified"}])
    monkeypatch.setattr(cli, "_settings", lambda a: settings)
    monkeypatch.setattr(cli, "_outreach_ctx", lambda s: ("me@x.com", "pw", "Alex"))
    monkeypatch.setattr(o, "_smtp", lambda *a: pytest.fail("held draft was sent"))
    assert cli.cmd_outreach_send(argparse.Namespace(job_id="j9", contact="Sam Lee", yes=True)) == 1
    assert "held" in capsys.readouterr().err and jd.exists()


def test_cli_panel_saves_each_gmail_draft_and_stops_cleanly_on_failure(settings, monkeypatch, capsys):
    """A failure on the second draft must not lose the first one's link (a rerun would duplicate it in Gmail)."""
    import argparse
    import json

    from careeros import cli
    jd = _job(settings, [dict(D), {**D, "contact": "Kim Park", "to": "kim@x.com"}])
    monkeypatch.setattr(cli, "_settings", lambda a: settings)
    monkeypatch.setattr(cli, "_outreach_ctx", lambda s: ("me@x.com", "pw", "Alex"))
    calls = []

    def fake(frm, pw, d, resume, name):
        calls.append(d["to"])
        if len(calls) == 2:
            raise OSError("imap down")
        return "https://mail.google.com/mail/u/0/#search/a"
    monkeypatch.setattr(o, "gmail_draft", fake)
    assert cli.cmd_outreach_panel(argparse.Namespace(job_ids=["j9"], gmail=True)) == 1
    assert "imap down" in capsys.readouterr().err
    saved = json.loads((jd / "outreach.json").read_text())["drafts"]
    assert saved[0]["gmail_draft_url"].startswith("https://") and "gmail_draft_url" not in saved[1]


def test_cli_missing_app_password_is_a_clean_error(settings, monkeypatch, capsys):
    import argparse

    from careeros import cli, notify
    _job(settings, [dict(D)])
    monkeypatch.setattr(cli, "_settings", lambda a: settings)
    monkeypatch.setattr(notify, "config", lambda s: {"email": "me@x.com"})
    monkeypatch.setattr(notify, "keychain_password", lambda e: (_ for _ in ()).throw(notify.NotifyError("no app password")))
    assert cli.cmd_outreach_send(argparse.Namespace(job_id="j9", contact="Sam Lee", yes=True)) == 1
    assert "no app password" in capsys.readouterr().err


def test_no_resume_pdf_refuses_instead_of_sending_without_it():
    """The body says the résumé is attached; never send or draft it without one."""
    with pytest.raises(o.SendError, match="résumé"):
        o.send_now("me@x.com", "pw", dict(D), None, "Alex", yes=True, smtp=lambda *a: pytest.fail("sent"))
    with pytest.raises(o.SendError, match="résumé"):
        o.gmail_draft("me@x.com", "pw", dict(D), None, "Alex", imap=lambda h: pytest.fail("appended"))


def test_gmail_draft_raises_when_gmail_rejects_the_append():
    class Imap:
        def __init__(self, host): pass
        def login(self, u, p): pass
        def append(self, *a): return ("NO", [b"over quota"])
        def logout(self): pass
    import pathlib
    import tempfile
    pdf = pathlib.Path(tempfile.mkdtemp()) / "resume.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(o.SendError, match="over quota"):
        o.gmail_draft("me@x.com", "pw", dict(D), pdf, "Alex", imap=Imap)


def test_every_route_refuses_a_draft_that_failed_qa_and_uses_the_candidates_line(tmp_path):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF")
    bad = {**D, "qa_pass": False, "qa_problems": ["too long"]}
    with pytest.raises(o.SendError, match="QA"):
        o.build_message("me@x.com", bad, pdf, "Alex")
    assert o.mail_link(bad) is None
    lined = {**D, "qa_pass": True, "your_line": "We met at the fintech meetup."}
    body = o.build_message("me@x.com", lined, pdf, "Alex").get_body(("plain",)).get_content()
    assert body.startswith("Hi Sam,\n\nWe met at the fintech meetup.\n\nAsk.")
    assert "We%20met" in o.mail_link(lined)


def test_cli_panel_skips_gmail_for_a_draft_that_failed_qa(settings, monkeypatch):
    import argparse

    from careeros import cli
    _job(settings, [{**D, "qa_pass": False}, {**D, "contact": "Kim Park", "to": "kim@x.com"}])
    monkeypatch.setattr(cli, "_settings", lambda a: settings)
    monkeypatch.setattr(cli, "_outreach_ctx", lambda s: ("me@x.com", "pw", "Alex"))
    made = []
    monkeypatch.setattr(o, "gmail_draft", lambda frm, pw, d, r, n: made.append(d["to"]) or "https://mail.google.com/x")
    assert cli.cmd_outreach_panel(argparse.Namespace(job_ids=["j9"], gmail=True)) == 0
    assert made == ["kim@x.com"]


def test_links_turn_the_named_text_into_a_hyperlink_in_the_html_part(tmp_path):
    """User 2026-11-19: hyperlink the position wherever an email names it."""
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF")
    d = {**D, "email": {"subject": "Hi", "body": "Hi Sam,\n\nI applied to the Acme <SWE> role.\n\nThanks"},
         "links": {"Acme <SWE>": "https://jobs.example.com/1?a=1&b=2"}}
    m = o.build_message("me@x.com", d, pdf, "Alex")
    html = m.get_body(("html",)).get_content()
    assert '<a href="https://jobs.example.com/1?a=1&amp;b=2">Acme &lt;SWE&gt;</a> role.' in html
    assert "<br>" in html
    assert m.get_body(("plain",)).get_content().startswith("Hi Sam,\n\nI applied to the Acme <SWE> role.")
    assert len(list(m.iter_attachments())) == 1
    assert o.build_message("me@x.com", D, pdf, "Alex").get_body(("html",)) is None  # no links, plain only


# ---- follow-up in the same Gmail thread -------------------------------------------------------------
from datetime import date, datetime  # noqa: E402

SENT = {**D, "sent": True, "sent_at": "2026-11-10", "followup_7d": "Hi Sam, following on my note.", "followup_14d": "Last note."}
TUE_10AM = datetime(2026, 11, 17, 10, 0)


def test_send_stores_message_id_and_subject(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    d, sent = dict(D), []
    o.send_now("me@x.com", "pw", d, pdf, "Alex", yes=True, smtp=lambda f, p, m: sent.append(m))
    assert d["message_id"].startswith("<") and d["message_id"].endswith("@x.com>") and d["sent_subject"] == "Hi Sam"
    assert sent[0]["Message-ID"] == d["message_id"]


@pytest.mark.parametrize("patch,msg", [
    ({"sent": False}, "not been sent"), ({"bounced": [{"to": "sam@x.com"}]}, "bounced"), ({"replied": "2026-11-12"}, "replied"),
    ({"followup_7d_sent_at": "2026-11-17"}, "already sent"), ({"followup_7d": ""}, "draft-outreach follow-ups")])
def test_followup_refusals(patch, msg):
    with pytest.raises(o.SendError, match=msg):
        o.followup_check({**SENT, **patch}, "7d", today=date(2026, 11, 20))


def test_followup_refuses_when_contact_replied_and_warns_when_early():
    with pytest.raises(o.SendError, match="replied"):
        o.followup_check(SENT, "7d", replied=True, today=date(2026, 11, 20))
    assert "before the due date (2026-11-17)" in o.followup_check(SENT, "7d", today=date(2026, 11, 12))[0]
    assert o.followup_check(SENT, "7d", today=date(2026, 11, 17)) == []


def test_followup_threads_with_stored_message_id():
    d, sent = {**SENT, "message_id": "<abc@x.com>", "sent_subject": "Hi Sam"}, []
    notes = o.send_followup("me@x.com", "pw", d, "7d", yes=True, smtp=lambda f, p, m: sent.append(m),
                            today=date(2026, 11, 17), now=TUE_10AM, imap=lambda h: pytest.fail("no lookup needed"))
    m = sent[0]
    assert m["Subject"] == "Re: Hi Sam" and m["In-Reply-To"] == m["References"] == "<abc@x.com>" and m["To"] == "sam@x.com"
    assert not list(m.iter_attachments()) and d["followup_7d_sent_at"] == "2026-11-17" and notes == []


def test_followup_needs_yes():
    d = {**SENT, "message_id": "<abc@x.com>"}
    with pytest.raises(o.SendError, match="--yes"):
        o.send_followup("me@x.com", "pw", d, "7d", yes=False, smtp=lambda *a: pytest.fail("sent"), today=date(2026, 11, 17))
    assert "followup_7d_sent_at" not in d


class SentBox:
    def __init__(self, found=True): self.found, self.log = found, []
    def __call__(self, host): self.log.append(host); return self
    def login(self, u, p): pass
    def select(self, box, readonly=False): self.log.append(box); return ("OK", [b"1"])
    def search(self, _c, *crit): self.log.append(crit); return ("OK", [b"4 9" if self.found else b""])
    def fetch(self, n, what):
        self.log.append(n)
        subj = b"Hi Sam" if n == b"9" else b"=?utf-8?q?Other_=E2=80=94_r=C3=A9sum=C3=A9?="
        return ("OK", [(b"x {30}", b"Message-ID: <old@mail.gmail.com>\r\nSubject: " + subj + b"\r\n\r\n"), b")"])
    def logout(self): pass


def test_followup_looks_up_message_id_over_imap_for_older_sends():
    d, sent, box = dict(SENT), [], SentBox()
    o.send_followup("me@x.com", "pw", d, "7d", yes=True, smtp=lambda f, p, m: sent.append(m), today=date(2026, 11, 17),
                    now=TUE_10AM, imap=box)
    assert "[Gmail]/Sent Mail" in box.log[1] and ("TO", '"sam@x.com"') in box.log
    assert sent[0]["In-Reply-To"] == "<old@mail.gmail.com>" and d["message_id"] == "<old@mail.gmail.com>"


def test_followup_without_original_goes_unthreaded_and_says_so():
    sent = []
    notes = o.send_followup("me@x.com", "pw", dict(SENT), "7d", yes=True, smtp=lambda f, p, m: sent.append(m),
                            today=date(2026, 11, 17), now=TUE_10AM, imap=SentBox(found=False))
    assert sent[0]["Subject"] == "Re: Hi Sam" and sent[0]["In-Reply-To"] is None and "without threading" in notes[0]


def test_window_hint_outside_tue_thu_morning():
    assert o.window_hint(TUE_10AM) is None
    assert "Tue-Thu 8am-12pm" in o.window_hint(datetime(2026, 11, 21, 10, 0))  # Saturday


def test_cli_followup_dry_run_yes_and_record(settings, monkeypatch, capsys):
    import argparse
    import json

    from careeros import cli
    jd = _job(settings, [{**SENT, "message_id": "<abc@x.com>"}])
    monkeypatch.setattr(cli, "_settings", lambda a: settings)
    monkeypatch.setattr(cli, "_outreach_ctx", lambda s: ("me@x.com", "pw", "Alex"))
    sent = []
    monkeypatch.setattr(o, "_smtp", lambda f, p, m: sent.append(m))
    ns = dict(job_id="j9", contact="Sam Lee", followup="7d")
    assert cli.cmd_outreach_send(argparse.Namespace(**ns, yes=False, dry_run=True)) == 0
    out = capsys.readouterr().out
    assert "[dry run]" in out and "Re: Hi Sam" in out and "<abc@x.com>" in out and not sent
    assert cli.cmd_outreach_send(argparse.Namespace(**ns, yes=False, dry_run=False)) == 1 and not sent
    assert cli.cmd_outreach_send(argparse.Namespace(**ns, yes=True, dry_run=False)) == 0
    assert len(sent) == 1 and json.loads((jd / "outreach.json").read_text())["drafts"][0]["followup_7d_sent_at"]
    assert cli.cmd_outreach_send(argparse.Namespace(**ns, yes=True, dry_run=False)) == 1 and len(sent) == 1
    assert "already sent" in capsys.readouterr().err


def test_followup_lookup_matches_non_ascii_subject():
    box = SentBox()
    d = {**SENT, "email": {**SENT["email"], "subject": "Other — résumé"}}
    assert o.find_message_id("me@x.com", "pw", d, imap=box) == "<old@mail.gmail.com>"
