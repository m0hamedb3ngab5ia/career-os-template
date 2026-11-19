"""Contacts sheet mirrors outreach.json: who was reached, did the email land, when the follow-up is due (user 2026-11-19)."""
from __future__ import annotations

import json

import pytest
from openpyxl import load_workbook

from careeros.follow_ups import contact_rows
from careeros.models import Posting
from careeros.store import Store
from careeros.tracker import Tracker

pytestmark = pytest.mark.unit


def _sheet(tr):
    ws = load_workbook(tr.path)["Contacts"]
    rows = list(ws.iter_rows(values_only=True))
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def test_contact_rows_track_reach_email_and_follow_up(settings):
    tr = Tracker(settings=settings)
    tr.init()
    p = Posting(company="Nimbus", title="Engineer", ats="greenhouse", ats_job_id="1", description_text="x",
                url="https://example.com/1")
    st = Store(settings)
    st.save_posting(p)
    (st.job_dir(p.job_id) / "outreach.json").write_text(json.dumps({"drafts": [
        {"contact": "Jane Doe", "to": "jdoe@nimbus.com", "to_confidence": "low", "sent": True,
         "sent_at": "2026-11-19T15:00:00", "bounced": [{"to": "jane.doe@nimbus.com", "error": "550 5.1.1"}]},
        {"contact": "Sam Lee", "to": "sam.lee@nimbus.com", "sent": False, "hold": True,
         "hold_reason": "address inactive 2026-11-19"},
        {"contact": "Ana Ruiz", "to": "aruiz@nimbus.com", "sent": False,
         "bounced": [{"to": "ana.ruiz@nimbus.com", "error": "550 5.1.1"}]},
    ]}))
    tr.sync_contacts(contact_rows(st, settings))
    tr.sync_contacts(contact_rows(st, settings))  # idempotent: one row per job + contact
    rows = {r["Name"]: r for r in _sheet(tr)}
    assert len(_sheet(tr)) == 3
    j = rows["Jane Doe"]
    assert (j["Company"], j["Sent"], j["SentDate"], j["Email"]) == ("Nimbus", "Y", "2026-11-19", "jdoe@nimbus.com")
    assert j["ContactStatus"] == "contacted" and j["EmailStatus"] == "delivered after 1 bounce"
    assert j["FollowUpDue"] == "2026-11-26"
    s = rows["Sam Lee"]
    assert s["ContactStatus"] == "left company" and s["Sent"] == "N" and not s["FollowUpDue"]
    a = rows["Ana Ruiz"]
    assert a["ContactStatus"] == "not reached" and a["EmailStatus"] == "bounced; next try aruiz@nimbus.com"


def test_old_contacts_sheet_gains_the_new_columns_and_keeps_replied(settings):
    tr = Tracker(settings=settings)
    tr.init()
    wb = load_workbook(tr.path)
    ws = wb["Contacts"]
    for c in range(12, ws.max_column + 1):  # a workbook made before the new columns
        ws.cell(row=1, column=c, value=None)
    ws.append(["j1", "Nimbus", "Jane Doe", "", "", "", "", "", "Y", "2026-11-01", "yes"])
    wb.save(tr.path)
    tr.sync_contacts([{"JobID": "j1", "Name": "Jane Doe", "Company": "Nimbus", "ContactStatus": "contacted"}])
    r = _sheet(tr)[0]
    assert r["Replied"] == "yes" and r["ContactStatus"] == "replied" and not r["FollowUpDue"]


def test_email_result_updates_the_contacts_sheet(settings, monkeypatch):
    from careeros.cli import main
    tr = Tracker(settings=settings)
    tr.init()
    p = Posting(company="Nimbus", title="Engineer", ats="greenhouse", ats_job_id="2", description_text="x",
                url="https://example.com/2")
    st = Store(settings)
    st.save_posting(p)
    (st.job_dir(p.job_id) / "outreach.json").write_text(json.dumps({"drafts": [
        {"contact": "Jane Doe", "to": "jane.doe@nimbus.com", "sent": True, "sent_at": "2026-11-19"}]}))
    monkeypatch.setattr("careeros.cli._settings", lambda a: settings)
    assert main(["outreach", "email-result", p.job_id, "--contact", "Jane Doe", "--bounced", "550 5.1.1"]) == 0
    r = _sheet(tr)[0]
    assert r["Name"] == "Jane Doe" and r["ContactStatus"] == "not reached" and r["EmailStatus"].startswith("bounced")
