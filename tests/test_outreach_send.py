"""Send panel: per draft, read it, open in iPhone Mail, open a Gmail draft with the résumé attached, or send on request."""
from __future__ import annotations

import email

import pytest

from careeros import outreach_send as o

pytestmark = pytest.mark.unit
D = {"contact": "Sam Lee", "role": "hiring_manager", "to": "sam@x.com", "to_confidence": "medium",
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
        def append(self, box, flags, when, raw): calls.append(("append", box, raw))
        def logout(self): calls.append(("logout",))

    url = o.gmail_draft("me@x.com", "pw", D, pdf, "Alex Example", imap=Imap)
    box, raw = [c for c in calls if c[0] == "append"][0][1:]
    assert box == '"[Gmail]/Drafts"' and email.message_from_bytes(raw)["To"] == "sam@x.com"
    assert url.startswith("https://mail.google.com/mail/u/0/#search/in%3Adrafts") and "sam%40x.com" in url


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
