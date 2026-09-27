"""careeros.ui.services.contacts and .inbox: the Contacts table (index + outreach.json + the relationship gate), the
`outreach mark` write, and the Inbox & follow-ups list and thread (status history, inbox-sync log lines, pending
sync updates, drafts with their placeholders)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from conftest import make_temp_root
from fixtures.ui_data import add_outreach_data, build_ui_data

from careeros.config import Settings
from careeros.ui.index import Index
from careeros.ui.services import contacts as contacts_svc
from careeros.ui.services import inbox as inbox_svc

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def data(tmp_path):
    return add_outreach_data(build_ui_data(make_temp_root(tmp_path / "repo"), NOW))


@pytest.fixture
def idx(data):
    ix = Index(data["settings"])
    ix.rebuild()
    yield ix
    ix.close()


@pytest.fixture
def empty(tmp_path):
    s = Settings.load(make_temp_root(tmp_path / "empty"))
    ix = Index(s)
    ix.rebuild()
    yield s, ix
    ix.close()


# --- pure helpers ----------------------------------------------------------------------------------------------

def test_placeholders_are_the_bracketed_variables_in_order_without_repeats():
    text = "Hi [NAME],\n\n[SPECIFIC CONNECTION] and [NAME] again. Plain (parens) stay."
    assert inbox_svc.placeholders(text) == ["[NAME]", "[SPECIFIC CONNECTION]"]
    assert inbox_svc.placeholders("") == [] and inbox_svc.placeholders(None) == []


def test_inbox_sync_log_lines_parse_and_other_lines_are_ignored():
    log = ("- 2026-09-22 09:00:00 [fixture] status -> applied\n"
           "- 2026-09-22 16:41:00 [inbox-sync] confirmation from jobs@example.com 2026-09-22 -> status applied "
           "(https://mail.google.com/mail/u/0/#all/abc)\n"
           "- 2026-09-23 10:00:00 [inbox-sync] garbled line without a link\n")
    got = inbox_svc.parse_inbox_log(log)
    assert len(got) == 1
    e = got[0]
    assert e["class"] == "confirmation" and e["from"] == "jobs@example.com"
    assert e["link"] == "https://mail.google.com/mail/u/0/#all/abc" and e["status"] == "applied"
    assert e["at"].startswith("2026-09-22T16:41:00")


def test_draft_view_marks_verified_email_and_counts_placeholders():
    d = {"contact": "Dana", "kind": "post_apply_outreach", "channel": "email", "to": "d@example.com",
         "to_confidence": "verified", "email": {"subject": "Hi", "body": "Hi Dana, [ONE] and [TWO]."},
         "linkedin_note": "note", "manual_tailor": False, "sent": False}
    v = inbox_svc.draft_view(d)
    assert v["verified"] is True and v["placeholders"] == ["[ONE]", "[TWO]"] and v["body"].startswith("Hi Dana")
    assert v["mode"] == "verified_email" and v["words"] == 5
    linked = inbox_svc.draft_view({**d, "to_confidence": "low", "email": None, "linkedin_message": "Hi there"})
    assert linked["verified"] is False and linked["mode"] == "linkedin" and linked["body"] == "Hi there"
    assert inbox_svc.draft_view({**d, "manual_tailor": True})["mode"] == "manual"
    assert inbox_svc.draft_view({**d, "kind": "post_interview_thanks"})["mode"] == "always_manual"
    assert inbox_svc.draft_view({**d, "sent": True, "sent_by": "candidate"})["mode"] == "sent"


# --- contacts --------------------------------------------------------------------------------------------------

def test_contacts_list_joins_jobs_outreach_and_the_relationship_gate(data, idx):
    got = contacts_svc.list_contacts(data["settings"], idx)
    by = {c["name"]: c for c in got["items"]}
    assert set(by) == {"Pat Rivers", "Sam Lee", "Dana Cruz"}
    pat = by["Pat Rivers"]
    assert pat["company"] == "Stark Industries" and pat["job_status"] == "interview"
    assert pat["manual"] is True and pat["manual_reason"] == "LINKEDIN_CONNECTED" and pat["mode"] == "manual"
    assert pat["manual_detail"] == "connected on LinkedIn"
    assert by["Sam Lee"]["mode"] == "linkedin_draft" and by["Sam Lee"]["manual"] is False
    assert by["Sam Lee"]["draft"]["body"].startswith("Hi Sam")
    assert by["Dana Cruz"]["mode"] == "email_draft" and by["Dana Cruz"]["email_confidence"] == "verified"
    assert got["linkedin_drafts"] == 1
    assert got["policy"] == {"manual_if_connected": True, "manual_if_mutuals": True}


def test_contacts_without_drafts_and_the_mutuals_gate(data, idx):
    jd = data["settings"].paths["jobs_dir"]
    from pathlib import Path

    (Path(jd) / data["jobs"]["interview"] / "outreach.json").unlink()
    contacts_svc.mark(data["settings"], data["jobs"]["interview"], "Sam Lee", mutuals=4)
    idx.update_jobs([data["jobs"]["interview"]])
    by = {c["name"]: c for c in contacts_svc.list_contacts(data["settings"], idx)["items"]}
    assert by["Sam Lee"]["mode"] == "manual" and by["Sam Lee"]["manual_detail"] == "4 mutual connections"
    assert by["Pat Rivers"]["draft"] is None


def test_contacts_empty(empty):
    s, ix = empty
    assert contacts_svc.list_contacts(s, ix) == {"items": [], "linkedin_drafts": 0,
                                                 "policy": {"manual_if_connected": True, "manual_if_mutuals": True}}


def test_mark_writes_through_outreach_mark_contact(data):
    jid = data["jobs"]["interview"]
    got = contacts_svc.mark(data["settings"], jid, "sam lee", degree=1, mutuals=2)
    assert got["linkedin_degree"] == 1 and got["mutuals"] == 2
    from pathlib import Path

    saved = json.loads((Path(data["settings"].paths["jobs_dir"]) / jid / "contacts.json").read_text())
    assert saved["contacts"][1]["linkedin_degree"] == 1


def test_mark_refuses_bad_input(data):
    jid = data["jobs"]["interview"]
    with pytest.raises(ValueError):
        contacts_svc.mark(data["settings"], jid, "Sam Lee")
    with pytest.raises(ValueError):
        contacts_svc.mark(data["settings"], jid, "Sam Lee", degree=5)
    with pytest.raises(LookupError):
        contacts_svc.mark(data["settings"], jid, "Nobody Here", degree=1)
    with pytest.raises(LookupError):
        contacts_svc.mark(data["settings"], data["jobs"]["found"], "Sam Lee", degree=1)   # no contacts.json
    with pytest.raises(LookupError):
        contacts_svc.mark(data["settings"], "../config", "Sam Lee", degree=1)


# --- inbox -----------------------------------------------------------------------------------------------------

def test_inbox_lists_post_apply_jobs_with_next_step_and_due_dates(data, idx):
    got = inbox_svc.list_inbox(data["settings"], idx, NOW)
    by = {r["company"]: r for r in got["items"]}
    assert set(by) == {"Hooli", "Stark Industries"}          # applied + interview; rejected is closed
    hooli = by["Hooli"]
    assert hooli["days_since_applied"] == 2 and hooli["status"] == "applied"
    assert hooli["next"]["kind"] == "post_apply_outreach" and hooli["next"]["mode"] == "verified_email"
    applied = datetime.fromisoformat(hooli["applied_at"])
    assert datetime.fromisoformat(hooli["next"]["due"]) == applied + timedelta(days=3)
    assert hooli["placeholders"] == 2 and hooli["drafts"] == 1
    stark = by["Stark Industries"]
    assert stark["last_email"]["class"] == "interview_invite"
    assert stark["next"]["kind"] == "post_interview_thanks" and stark["next"]["mode"] == "always_manual"
    assert stark["next"]["due"] is None
    assert got["last_sync"] is None
    assert got["sync"] == {"available": False, "reason": "Inbox sync isn't set up yet"}
    assert got["sending"] == {"available": False, "reason": "Follow-up sending isn't built yet"}
    assert got["items"][0]["company"] == "Hooli"               # soonest due first


def test_inbox_due_days_come_from_config(data, idx):
    s = data["settings"]
    s.pipeline.setdefault("ui", {})["followup_after_apply_days"] = 1
    hooli = next(r for r in inbox_svc.list_inbox(s, idx, NOW)["items"] if r["company"] == "Hooli")
    assert datetime.fromisoformat(hooli["next"]["due"]) == datetime.fromisoformat(hooli["applied_at"]) + timedelta(days=1)


def test_inbox_detail_thread_and_drafts(data, idx):
    d = inbox_svc.inbox_detail(data["settings"], idx, data["jobs"]["interview"], NOW)
    kinds = [e["type"] for e in d["thread"]]
    assert "email" in kinds and "status" in kinds
    assert d["thread"] == sorted(d["thread"], key=lambda e: e["at"], reverse=True)
    applied = [e for e in d["thread"] if e["type"] == "status" and e["status"] == "applied"]
    assert applied
    assert [x["contact"] for x in d["drafts"]] == ["Pat Rivers", "Sam Lee", "Pat Rivers"]
    assert d["drafts"][d["primary"]]["kind"] == "post_interview_thanks"
    hooli = inbox_svc.inbox_detail(data["settings"], idx, data["jobs"]["applied"], NOW)
    pending = [e for e in hooli["thread"] if e["type"] == "pending_update"]
    assert pending and pending[0]["status"] == "screening"
    assert hooli["drafts"][hooli["primary"]]["placeholders"] == ["[SPECIFIC CONNECTION]", "[MOST RELEVANT EXPERIENCE]"]


def test_inbox_detail_unknown_or_not_post_apply(data, idx):
    assert inbox_svc.inbox_detail(data["settings"], idx, "nope00000000", NOW) is None
    assert inbox_svc.inbox_detail(data["settings"], idx, "../config", NOW) is None
    queued = inbox_svc.inbox_detail(data["settings"], idx, data["jobs"]["queued"], NOW)
    assert queued is not None and queued["drafts"] == [] and queued["primary"] is None


def test_inbox_empty(empty):
    s, ix = empty
    got = inbox_svc.list_inbox(s, ix, NOW)
    assert got["items"] == [] and got["last_sync"] is None


def test_inbox_last_sync_from_inbox_sync_runs(data, idx):
    from careeros.runs.store import RunStore, iso

    rs = RunStore(data["settings"])
    run = rs.new_run("inbox_sync", "schedule", {}, NOW - timedelta(hours=6))
    run.update({"status": "done", "stop_reason": "completed", "ended_at": iso(NOW - timedelta(hours=6))})
    rs.save_run(run)
    idx.sync()
    assert inbox_svc.list_inbox(data["settings"], idx, NOW)["last_sync"] == iso(NOW - timedelta(hours=6))


def test_broken_outreach_json_is_ignored(data, idx):
    from pathlib import Path

    (Path(data["settings"].paths["jobs_dir"]) / data["jobs"]["applied"] / "outreach.json").write_text("{nope")
    hooli = next(r for r in inbox_svc.list_inbox(data["settings"], idx, NOW)["items"] if r["company"] == "Hooli")
    assert hooli["drafts"] == 0 and hooli["next"]["mode"] == "no_draft"


# --- review round 1 --------------------------------------------------------------------------------------------

def _set_status(data, key, status, at):
    from pathlib import Path

    from careeros.runs.store import iso

    jid = data["jobs"][key]
    f = Path(data["settings"].paths["jobs_dir"]) / jid / "status.json"
    st = json.loads(f.read_text())
    st["history"].append({"status": status, "at": iso(at), "note": None})
    st["status"], st["updated_at"] = status, iso(at)
    f.write_text(json.dumps(st))
    return jid


def test_screening_status_followup_due_from_config(data, idx):
    since = NOW - timedelta(days=1)
    jid = _set_status(data, "applied", "screening", since)
    idx.update_jobs([jid])
    s = data["settings"]
    s.pipeline.setdefault("ui", {})["followup_no_response_days"] = 10
    row = next(r for r in inbox_svc.list_inbox(s, idx, NOW)["items"] if r["job_id"] == jid)
    assert row["next"]["kind"] == "status_followup"
    assert datetime.fromisoformat(row["next"]["due"]) == since + timedelta(days=10)


def test_offer_next_is_offer_reply(data, idx):
    jid = _set_status(data, "interview", "offer", NOW - timedelta(hours=2))
    idx.update_jobs([jid])
    row = next(r for r in inbox_svc.list_inbox(data["settings"], idx, NOW)["items"] if r["job_id"] == jid)
    assert row["next"] == {"kind": "offer_reply", "due": None, "mode": "you_reply"}


def test_interview_invite_without_thanks_draft_is_reply_with_slot(data, idx):
    from pathlib import Path

    jid = data["jobs"]["interview"]
    f = Path(data["settings"].paths["jobs_dir"]) / jid / "outreach.json"
    o = json.loads(f.read_text())
    o["followups"] = []
    f.write_text(json.dumps(o))
    row = next(r for r in inbox_svc.list_inbox(data["settings"], idx, NOW)["items"] if r["job_id"] == jid)
    assert row["next"] == {"kind": "reply_with_slot", "due": None, "mode": "you_reply"}


def test_sync_reason_when_schedule_has_inbox_sync_on(data, idx):
    s = data["settings"]
    s.pipeline["schedule"]["jobs"]["inbox_sync"]["enabled"] = True
    assert inbox_svc.list_inbox(s, idx, NOW)["sync"] == {"available": False, "reason": inbox_svc.SYNC_NO_BUTTON}


def test_marking_a_contact_connected_makes_its_inbox_draft_manual(data, idx):
    jid = data["jobs"]["applied"]
    assert inbox_svc.inbox_detail(data["settings"], idx, jid, NOW)["drafts"][0]["mode"] == "verified_email"
    contacts_svc.mark(data["settings"], jid, "Dana Cruz", degree=1)
    d = inbox_svc.inbox_detail(data["settings"], idx, jid, NOW)
    assert d["drafts"][d["primary"]]["mode"] == "manual"
    assert d["drafts"][d["primary"]]["manual_reason"] == "LINKEDIN_CONNECTED"
    row = next(r for r in inbox_svc.list_inbox(data["settings"], idx, NOW)["items"] if r["job_id"] == jid)
    assert row["next"]["mode"] == "manual"
    contacts_svc.mark(data["settings"], jid, "Dana Cruz", degree=2, mutuals=3)
    d = inbox_svc.inbox_detail(data["settings"], idx, jid, NOW)
    assert d["drafts"][d["primary"]]["mode"] == "manual"


# --- review round 2 --------------------------------------------------------------------------------------------

def _outreach(data, key):
    from pathlib import Path

    return Path(data["settings"].paths["jobs_dir"]) / data["jobs"][key] / "outreach.json"


def _log_email(data, key, at, cls="other"):
    from pathlib import Path

    f = Path(data["settings"].paths["jobs_dir"]) / data["jobs"][key] / "log.md"
    ts = at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    line = f"- {ts} [inbox-sync] {cls} from hr@example.com -> status screening (https://mail.google.com/x)\n"
    f.write_text((f.read_text() if f.exists() else "") + line)


def test_screening_followup_due_counts_from_the_latest_email_after_the_status_change(data, idx):
    t0 = NOW - timedelta(days=6)
    jid = _set_status(data, "applied", "screening", t0)
    _log_email(data, "applied", t0 + timedelta(days=5))
    idx.update_jobs([jid])
    s = data["settings"]
    s.pipeline.setdefault("ui", {})["followup_no_response_days"] = 7
    row = next(r for r in inbox_svc.list_inbox(s, idx, NOW)["items"] if r["job_id"] == jid)
    assert datetime.fromisoformat(row["next"]["due"]) == t0 + timedelta(days=12)


def test_a_sent_thank_you_moves_interview_next_to_a_status_followup_with_a_due_date(data, idx):
    f = _outreach(data, "interview")
    o = json.loads(f.read_text())
    for d in o["followups"]:
        d["sent"], d["sent_date"] = True, (NOW - timedelta(days=1)).isoformat()
    f.write_text(json.dumps(o))
    jid = data["jobs"]["interview"]
    row = next(r for r in inbox_svc.list_inbox(data["settings"], idx, NOW)["items"] if r["job_id"] == jid)
    assert row["next"]["kind"] == "status_followup" and row["next"]["due"] is not None


def test_bare_list_outreach_and_nested_followups_are_read_like_qa_ext(data):
    from pathlib import Path

    f = _outreach(data, "applied")
    o = json.loads(f.read_text())
    first = o["drafts"][0]
    nested = {"kind": "status_followup", "email": {"subject": "Checking in", "body": "Hi again"}}
    f.write_text(json.dumps([{**first, "followups": [nested]}]))
    got = inbox_svc.job_drafts(Path(f).parent)
    assert [d["kind"] for d in got] == [first["kind"], "status_followup"]
    assert got[1]["contact"] == first["contact"] and got[1]["body"] == "Hi again"
    f.write_text(json.dumps({"drafts": [{**first, "followups": [nested]}], "followups": []}))
    assert len(inbox_svc.job_drafts(Path(f).parent)) == 2


# --- SHOULD-FIX: malformed outreach.json shapes must not crash --------------------------------------------------

@pytest.mark.parametrize("bad", [
    {"drafts": [{"email": {"subject": 5}}]},
    {"drafts": [{"linkedin_message": 7}]},
    {"drafts": [{"followups": [{"body": {}}]}]},
])
def test_non_string_draft_fields_are_treated_as_missing_not_crashed(data, bad):
    from pathlib import Path

    f = _outreach(data, "applied")
    f.write_text(json.dumps(bad))
    got = inbox_svc.job_drafts(Path(f).parent)
    assert got  # normalized, no exception raised above
    for d in got:
        assert d["placeholders"] == []
        assert isinstance(d["words"], int)


def test_interview_thank_you_all_sent_is_not_reported_as_sent_mode(data, idx):
    f = _outreach(data, "interview")
    o = json.loads(f.read_text())
    for d in o["followups"]:
        d["sent"], d["sent_date"] = True, (NOW - timedelta(days=1)).isoformat()
    f.write_text(json.dumps(o))
    jid = data["jobs"]["interview"]
    row = next(r for r in inbox_svc.list_inbox(data["settings"], idx, NOW)["items"] if r["job_id"] == jid)
    assert row["next"]["kind"] == "status_followup"
    assert row["next"]["mode"] != "sent"


# --- review round 2 --------------------------------------------------------------------------------------------

def test_applied_job_with_all_outreach_sent_has_no_due_and_sent_mode(data, idx):
    f = _outreach(data, "applied")
    o = json.loads(f.read_text())
    for d in o["drafts"]:
        d["sent"], d["sent_by"], d["sent_date"] = True, "candidate", (NOW - timedelta(days=1)).isoformat()
    f.write_text(json.dumps(o))
    hooli = next(r for r in inbox_svc.list_inbox(data["settings"], idx, NOW)["items"] if r["company"] == "Hooli")
    assert hooli["next"]["kind"] == "post_apply_outreach"
    assert hooli["next"]["due"] is None and hooli["next"]["mode"] == "sent"


def test_linkedin_channel_draft_shows_the_linkedin_variant_not_the_email():
    d = {"contact": "Sam", "kind": "cold_email", "channel": "linkedin", "to": "sam@x.com", "to_confidence": "verified",
         "linkedin_note": "Hi Sam, quick note.", "linkedin_message": "Hi Sam, I applied to the role.",
         "email": {"subject": "Role at [Company]", "body": "Hi [Name], email body."}}
    v = inbox_svc.draft_view(d)
    assert v["body"] == "Hi Sam, I applied to the role."
    assert v["placeholders"] == [] and v["mode"] == "linkedin"
    assert inbox_svc.draft_view({**d, "channel": "email"})["body"] == "Hi [Name], email body."


def test_draft_followup_7d_and_14d_are_listed_after_their_draft(data):
    from pathlib import Path

    f = _outreach(data, "applied")
    o = json.loads(f.read_text())
    first = o["drafts"][0]
    o["drafts"] = [{**first, "followup_7d": "Following up on my note.", "followup_14d": "Closing the loop."}]
    f.write_text(json.dumps(o))
    got = inbox_svc.job_drafts(Path(f).parent)
    assert [d["kind"] for d in got] == [first["kind"], "followup_7d", "followup_14d"]
    assert got[1]["body"] == "Following up on my note." and got[1]["contact"] == first["contact"]
    assert got[2]["body"] == "Closing the loop." and not got[1]["sent"]


def test_last_sync_ignores_failed_inbox_sync_runs(data, idx):
    from careeros.runs.store import RunStore, iso

    rs = RunStore(data["settings"])
    ok = rs.new_run("inbox_sync", "schedule", {}, NOW - timedelta(hours=6))
    ok.update({"status": "done", "stop_reason": "completed", "ended_at": iso(NOW - timedelta(hours=6))})
    rs.save_run(ok)
    bad = rs.new_run("inbox_sync", "schedule", {}, NOW - timedelta(hours=1))
    bad.update({"status": "failed", "stop_reason": "error", "ended_at": iso(NOW - timedelta(hours=1))})
    rs.save_run(bad)
    idx.sync()
    assert inbox_svc.list_inbox(data["settings"], idx, NOW)["last_sync"] == iso(NOW - timedelta(hours=6))
