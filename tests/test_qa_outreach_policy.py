"""Unit tests for careeros.qa_ext.outreach_policy: outreach.json obeys the send policy (fictional contacts)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import make_temp_root

from careeros.qa import Checker
from careeros.qa_ext.outreach_policy import check_outreach_policy

pytestmark = pytest.mark.unit

CHECKS = ("outreach_manual_contacts", "linkedin_draft_only", "linkedin_note_length", "email_autosend_verified",
          "thank_you_manual", "outreach_word_counts", "outreach_cold_limit")


def words(n: int) -> str:
    return " ".join(["word"] * n)


def contact(name: str, **kw) -> dict:
    c = {"name": name, "title": "Recruiter", "role": "recruiter", "linkedin": None, "source": "posting",
         "confidence": "high", "email_candidates": [], "email": None, "email_confidence": "low",
         "possible_referral": False, "linkedin_degree": None, "mutuals": None, "note": ""}
    c.update(kw)
    return c


def draft(name: str, **kw) -> dict:
    d = {"contact": name, "role": "recruiter", "linkedin": None, "to": None, "to_confidence": "low",
         "linkedin_note": "Hi, I applied to the Backend role. Would like to connect.",
         "linkedin_message": words(80), "email": {"subject": "Backend application", "body": words(100)},
         "followup_7d": words(50), "followup_14d": None, "bullet_ids": ["acme.1"], "narrative_ids": [],
         "facts_used": [], "manual_tailor": False, "manual_reason": None, "send_after": None, "sent": False}
    d.update(kw)
    return d


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_temp_root(tmp_path / "repo")


def make(root: Path, drafts=None, contacts=None, followups=None, raw: str | None = None) -> Checker:
    job = root / "data" / "jobs" / "t1"
    job.mkdir(parents=True, exist_ok=True)
    if contacts is not None:
        (job / "contacts.json").write_text(json.dumps({"job_id": "t1", "company": "Ledgerline",
                                                       "contacts": contacts}))
    if raw is not None:
        (job / "outreach.json").write_text(raw)
    elif drafts is not None or followups is not None:
        data = {"job_id": "t1", "company": "Ledgerline", "drafts": drafts or [], "review_required": True}
        if followups is not None:
            data["followups"] = followups
        (job / "outreach.json").write_text(json.dumps(data))
    return Checker(job, root)


def run(ck: Checker) -> dict[str, dict]:
    check_outreach_policy(ck)
    return {c["check"]: c for c in ck.checks}


# ---- skip / baseline -------------------------------------------------------------------------------

def test_skips_cleanly_without_outreach_json(root):
    ck = make(root, contacts=[contact("Jane Doe")])
    res = run(ck)
    for name in CHECKS:
        assert res[name]["ok"] and res[name].get("skipped"), name
    assert ck.extras["outreach_policy"]["present"] is False


def test_clean_cold_draft_passes_everything(root):
    ck = make(root, [draft("Jane Doe")], [contact("Jane Doe")])
    res = run(ck)
    for name in CHECKS:
        assert res[name]["ok"] and not res[name].get("skipped"), (name, res[name]["detail"])
    ex = ck.extras["outreach_policy"]
    assert ex["present"] is True and ex["drafts"] == 1 and ex["manual_contacts"] == [] and ex["violations"] == []


def test_invalid_outreach_json_is_hard_fail(root):
    res = run(make(root, raw="{not json"))
    assert res["outreach_json_valid"]["ok"] is False and res["outreach_json_valid"]["level"] == "hard"


def test_bare_list_outreach_json_is_read_as_drafts(root):
    ck = make(root, raw=json.dumps([draft("Jane Doe")]), contacts=[contact("Jane Doe")])
    res = run(ck)
    assert "outreach_json_valid" not in res
    assert ck.extras["outreach_policy"]["drafts"] == 1 and res["linkedin_draft_only"]["ok"]


def test_scalar_outreach_json_is_hard_fail(root):
    res = run(make(root, raw="42"))
    assert res["outreach_json_valid"]["ok"] is False


def test_levels(root):
    res = run(make(root, [draft("Jane Doe")], [contact("Jane Doe")]))
    assert res["outreach_word_counts"]["level"] == "soft"
    for name in set(CHECKS) - {"outreach_word_counts"}:
        assert res[name]["level"] == "hard", name


# ---- 1. manual contacts ----------------------------------------------------------------------------

MANUAL_OK = dict(manual_tailor=True, manual_reason="LINKEDIN_CONNECTED", send_after=None, sent=False,
                 followup_7d=None, followup_14d=None)


@pytest.mark.parametrize("ckw", [{"linkedin_degree": 1}, {"mutuals": 3}])
def test_manual_contact_properly_marked_passes(root, ckw):
    ck = make(root, [draft("Pat Lee", **MANUAL_OK)], [contact("Pat Lee", **ckw)])
    res = run(ck)
    assert res["outreach_manual_contacts"]["ok"], res["outreach_manual_contacts"]["detail"]
    assert ck.extras["outreach_policy"]["manual_contacts"] == ["Pat Lee"]


@pytest.mark.parametrize("override", [
    {"manual_tailor": False},
    {"send_after": "2026-10-01T09:00:00"},
    {"sent": True},
    {"followup_7d": "Following up on my note."},
    {"followup_14d": "Closing the loop."},
])
def test_manual_contact_violations_fail(root, override):
    d = draft("Pat Lee", **{**MANUAL_OK, **override})
    ck = make(root, [d], [contact("Pat Lee", linkedin_degree=1)])
    res = run(ck)
    assert res["outreach_manual_contacts"]["ok"] is False
    assert "Pat Lee" in res["outreach_manual_contacts"]["detail"]
    assert any(v["check"] == "outreach_manual_contacts" for v in ck.extras["outreach_policy"]["violations"])


def test_manual_contact_name_match_is_case_insensitive(root):
    res = run(make(root, [draft("pat lee")], [contact("Pat Lee", mutuals=2)]))
    assert res["outreach_manual_contacts"]["ok"] is False


def test_manual_contact_sent_by_candidate_is_allowed(root):
    d = draft("Pat Lee", **{**MANUAL_OK, "sent": True, "sent_by": "candidate"})
    res = run(make(root, [d], [contact("Pat Lee", linkedin_degree=1)]))
    assert res["outreach_manual_contacts"]["ok"], res["outreach_manual_contacts"]["detail"]


def test_manual_policy_switch_off_in_pipeline_yaml(root):
    p = root / "config" / "pipeline.yaml"
    cfg = yaml.safe_load(p.read_text())
    cfg["outreach"] = {"manual_if_connected": False, "manual_if_mutuals": False}
    p.write_text(yaml.safe_dump(cfg))
    res = run(make(root, [draft("Pat Lee")], [contact("Pat Lee", linkedin_degree=1)]))
    assert res["outreach_manual_contacts"]["ok"], res["outreach_manual_contacts"]["detail"]


def test_manual_flag_on_draft_itself_counts_without_contacts_json(root):
    # the draft says it is manual, yet it is scheduled: still a failure
    d = draft("Pat Lee", manual_tailor=True, manual_reason="LINKEDIN_MUTUALS", send_after="2026-10-01",
              followup_7d=None)
    res = run(make(root, [d]))
    assert res["outreach_manual_contacts"]["ok"] is False


# ---- 2. LinkedIn draft only ------------------------------------------------------------------------

@pytest.mark.parametrize("override", [
    {"channel": "linkedin", "email": None, "send_after": "2026-10-01"},
    {"email": None, "send_after": "2026-10-01"},                       # LinkedIn-only draft scheduled
    {"channel": "linkedin", "email": None, "sent": True, "sent_by": "system"},
    {"linkedin_send_after": "2026-10-01"},
    {"channel": "linkedin", "email": None, "auto_send": True},
])
def test_linkedin_auto_send_fails(root, override):
    ck = make(root, [draft("Jane Doe", **override)], [contact("Jane Doe")])
    res = run(ck)
    assert res["linkedin_draft_only"]["ok"] is False, override


def test_linkedin_sent_by_candidate_is_fine(root):
    d = draft("Jane Doe", channel="linkedin", email=None, sent=True, sent_by="candidate")
    res = run(make(root, [d], [contact("Jane Doe")]))
    assert res["linkedin_draft_only"]["ok"], res["linkedin_draft_only"]["detail"]


# ---- 3. email auto-send requires a verified address ------------------------------------------------

def test_email_scheduled_to_verified_address_passes(root):
    c = contact("Jane Doe", email="jane.doe@ledgerline.com", email_confidence="verified")
    d = draft("Jane Doe", to="jane.doe@ledgerline.com", to_confidence="verified", send_after="2026-10-01")
    res = run(make(root, [d], [c]))
    assert res["email_autosend_verified"]["ok"], res["email_autosend_verified"]["detail"]


@pytest.mark.parametrize("c,d", [
    # contact's address only guessed
    (contact("Jane Doe", email_candidates=["jane.doe@ledgerline.com"], email_confidence="medium"),
     draft("Jane Doe", to="jane.doe@ledgerline.com", to_confidence="medium", send_after="2026-10-01")),
    # draft claims verified but contacts.json does not agree
    (contact("Jane Doe", email_candidates=["jane.doe@ledgerline.com"], email_confidence="low"),
     draft("Jane Doe", to="jane.doe@ledgerline.com", to_confidence="verified", send_after="2026-10-01")),
    # verified address differs from the draft's recipient
    (contact("Jane Doe", email="jane@ledgerline.com", email_confidence="verified"),
     draft("Jane Doe", to="jane.doe@ledgerline.com", send_after="2026-10-01")),
    # no recipient at all
    (contact("Jane Doe"), draft("Jane Doe", to=None, send_after="2026-10-01")),
])
def test_email_scheduled_without_verified_address_fails(root, c, d):
    ck = make(root, [d], [c])
    res = run(ck)
    assert res["email_autosend_verified"]["ok"] is False


def test_email_scheduled_without_contacts_json_fails(root):
    d = draft("Jane Doe", to="jane.doe@ledgerline.com", to_confidence="verified", send_after="2026-10-01")
    res = run(make(root, [d]))
    assert res["email_autosend_verified"]["ok"] is False


def test_unscheduled_email_to_guessed_address_is_fine(root):
    d = draft("Jane Doe", to="jane.doe@ledgerline.com", to_confidence="low", send_after=None)
    res = run(make(root, [d], [contact("Jane Doe")]))
    assert res["email_autosend_verified"]["ok"]


def test_autosend_confidence_configurable(root):
    p = root / "config" / "qa.yaml"
    cfg = yaml.safe_load(p.read_text())
    cfg["outreach"] = {"autosend_email_confidence": ["verified", "pattern_match_high"]}
    p.write_text(yaml.safe_dump(cfg))
    c = contact("Jane Doe", email="jane.doe@ledgerline.com", email_confidence="pattern_match_high")
    d = draft("Jane Doe", to="jane.doe@ledgerline.com", send_after="2026-10-01")
    res = run(make(root, [d], [c]))
    assert res["email_autosend_verified"]["ok"], res["email_autosend_verified"]["detail"]


# ---- 4. thank-you notes always manual --------------------------------------------------------------

THANKS = {"contact": "Jane Doe", "kind": "post_interview_thanks", "to": "jane.doe@ledgerline.com",
          "email": {"subject": "Thank you, Backend interview", "body": words(90)}, "send_after": None, "sent": False}


def test_thank_you_unscheduled_passes(root):
    c = contact("Jane Doe", email="jane.doe@ledgerline.com", email_confidence="verified")
    res = run(make(root, [], [c], followups=[THANKS]))
    assert res["thank_you_manual"]["ok"], res["thank_you_manual"]["detail"]


@pytest.mark.parametrize("override", [
    {"send_after": "2026-10-01"},
    {"kind": "thank_you", "auto_send": True},
    {"type": "thank_you", "kind": None, "sent": True, "sent_by": "scheduler"},
    {"kind": None, "template": "post_interview_thanks.md", "send_after": "2026-10-01"},
])
def test_thank_you_scheduled_fails_even_to_verified_address(root, override):
    c = contact("Jane Doe", email="jane.doe@ledgerline.com", email_confidence="verified")
    res = run(make(root, [], [c], followups=[{**THANKS, **override}]))
    assert res["thank_you_manual"]["ok"] is False, override


def test_thank_you_inside_drafts_list_is_checked_too(root):
    c = contact("Jane Doe", email="jane.doe@ledgerline.com", email_confidence="verified")
    res = run(make(root, [{**THANKS, "send_after": "2026-10-01"}], [c]))
    assert res["thank_you_manual"]["ok"] is False


# ---- 5. word counts (soft) -------------------------------------------------------------------------

@pytest.mark.parametrize("override,field", [
    ({"kind": "post_apply_outreach", "email": {"subject": "x", "body": words(130)}}, "email.body"),
    ({"followup_7d": words(90)}, "followup_7d"),
    ({"linkedin_message": words(140)}, "linkedin_message"),
    ({"email": {"subject": "x", "body": words(160)}}, "email.body"),         # cold email default cap 150
])
def test_word_counts_over_limit_warn(root, override, field):
    ck = make(root, [draft("Jane Doe", **override)], [contact("Jane Doe")])
    res = run(ck)
    wc = res["outreach_word_counts"]
    assert wc["ok"] is False and wc["level"] == "soft" and field in wc["detail"]
    assert any(o["field"] == field for o in ck.extras["outreach_policy"]["word_counts"])


def test_word_count_status_followup_and_thanks(root):
    fu = [{"contact": "Jane Doe", "kind": "status_followup", "email": {"subject": "x", "body": words(85)}},
          {**THANKS, "email": {"subject": "x", "body": words(125)}}]
    ck = make(root, [], [contact("Jane Doe")], followups=fu)
    res = run(ck)
    assert res["outreach_word_counts"]["ok"] is False
    fields = {(o["kind"], o["field"]) for o in ck.extras["outreach_policy"]["word_counts"]}
    assert ("status_followup", "email.body") in fields and ("post_interview_thanks", "email.body") in fields


def test_word_count_limits_configurable(root):
    p = root / "config" / "qa.yaml"
    cfg = yaml.safe_load(p.read_text())
    cfg["outreach"] = {"after_apply_max_words": 50}
    p.write_text(yaml.safe_dump(cfg))
    d = draft("Jane Doe", kind="post_apply_outreach", email={"subject": "x", "body": words(60)})
    res = run(make(root, [d], [contact("Jane Doe")]))
    assert res["outreach_word_counts"]["ok"] is False


def test_linkedin_note_over_300_chars_is_hard(root):
    ck = make(root, [draft("Jane Doe", linkedin_note="x" * 301)], [contact("Jane Doe")])
    res = run(ck)
    c = res["linkedin_note_length"]
    assert c["level"] == "hard" and c["ok"] is False and "301" in c["detail"] and "Jane Doe" in c["detail"]
    assert res["outreach_word_counts"]["ok"] is True  # not double-reported as a soft warning
    assert {"check": "linkedin_note_length", "contact": "Jane Doe", "issue": "linkedin_note 301 chars > 300"} \
        in ck.extras["outreach_policy"]["violations"]


def test_linkedin_note_exactly_300_chars_passes(root):
    res = run(make(root, [draft("Jane Doe", linkedin_note="x" * 300)], [contact("Jane Doe")]))
    assert res["linkedin_note_length"]["ok"] is True


def test_linkedin_note_limit_configurable(root):
    p = root / "config" / "qa.yaml"
    cfg = yaml.safe_load(p.read_text())
    cfg["outreach"] = {"linkedin_note_max_chars": 200}
    p.write_text(yaml.safe_dump(cfg))
    res = run(make(root, [draft("Jane Doe", linkedin_note="x" * 250)], [contact("Jane Doe")]))
    assert res["linkedin_note_length"]["ok"] is False


def test_linkedin_note_chars_mismatch_warns(root):
    d = draft("Jane Doe", linkedin_note="Hi, would like to connect.", linkedin_note_chars=12)
    res = run(make(root, [d], [contact("Jane Doe")]))
    assert res["outreach_word_counts"]["ok"] is False and "linkedin_note_chars" in res["outreach_word_counts"]["detail"]


# ---- 6. cold contacts: one outreach + one follow-up ------------------------------------------------

def test_cold_contact_with_14d_followup_fails(root):
    res = run(make(root, [draft("Jane Doe", followup_14d=words(40))], [contact("Jane Doe")]))
    assert res["outreach_cold_limit"]["ok"] is False and "Jane Doe" in res["outreach_cold_limit"]["detail"]


def test_contact_who_replied_may_get_14d_followup(root):
    res = run(make(root, [draft("Jane Doe", followup_14d=words(40))], [contact("Jane Doe", replied="2026-09-20")]))
    assert res["outreach_cold_limit"]["ok"], res["outreach_cold_limit"]["detail"]


def test_cold_contact_with_two_drafts_fails(root):
    res = run(make(root, [draft("Jane Doe"), draft("Jane Doe")], [contact("Jane Doe")]))
    assert res["outreach_cold_limit"]["ok"] is False


def test_cold_contact_extra_followup_entry_counts(root):
    fu = [{"contact": "Jane Doe", "kind": "status_followup", "email": {"subject": "x", "body": words(40)}}]
    res = run(make(root, [draft("Jane Doe")], [contact("Jane Doe")], followups=fu))
    assert res["outreach_cold_limit"]["ok"] is False


def test_thank_you_does_not_count_against_cold_limit(root):
    c = contact("Jane Doe", email="jane.doe@ledgerline.com", email_confidence="verified")
    res = run(make(root, [draft("Jane Doe")], [c], followups=[THANKS]))
    assert res["outreach_cold_limit"]["ok"], res["outreach_cold_limit"]["detail"]
