"""QA: outreach.json obeys the send policy (draft-outreach / follow-up rules), deterministically.

Reads `<job>/outreach.json` (draft-outreach step 4: `drafts[]`, plus an optional top-level `followups[]` for
status follow-ups / thank-yous) and `<job>/contacts.json` (find-contacts: `contacts[]` with `email`,
`email_confidence`, `linkedin_degree`, `mutuals`, optional `replied`). Checks:

  outreach_json_valid       hard  outreach.json parses (only reported when it does not)
  outreach_manual_contacts  hard  a contact `careeros.outreach.needs_manual_outreach` flags (1st degree / mutuals,
                                  switches in config/pipeline.yaml `outreach`) or a draft marked manual has
                                  `manual_tailor: true`, no `send_after`, not system-sent, no follow-ups
  linkedin_draft_only       hard  LinkedIn drafts are never scheduled or sent by the system
  linkedin_note_length      hard  a `linkedin_note` over qa.yaml `outreach.linkedin_note_max_chars` (300): LinkedIn
                                  truncates connection notes, so this is not a style warning
  email_autosend_verified   hard  an email with `send_after` goes to the contact's own `email` whose contacts.json
                                  `email_confidence` is in qa.yaml `outreach.autosend_email_confidence` (["verified"])
  thank_you_manual          hard  interview thank-yous are never scheduled / auto-sent
  outreach_word_counts      soft  word limits from qa.yaml `outreach` (defaults below; templates/outreach,
                                  templates/followup_email), and a stated `linkedin_note_chars` that is wrong
  outreach_cold_limit       hard  a cold contact (never replied, no interview) gets one outreach + at most one
                                  follow-up

"Sent by the system" = `sent: true` unless `sent_by` is candidate/manual/user; `auto_send: true` also counts.
A bare JSON list is read as `drafts[]`. Inputs come from the Checker: `ck.outreach` / `ck.outreach_error`,
`ck.contacts`, `ck.pipeline_cfg`. Results in `ck.extras["outreach_policy"]`.
"""
from __future__ import annotations

from typing import Any

from careeros.outreach import OutreachPolicy, needs_manual_outreach
from careeros.qa import count_words

DEFAULTS: dict[str, Any] = {
    "after_apply_max_words": 120,       # post_apply_outreach.md: ~100 words
    "cold_email_max_words": 150,        # draft-outreach: body 90-150 words
    "status_followup_max_words": 80,    # status_followup.md / followup_7d.md: 40-70 words
    "thank_you_max_words": 120,         # post_interview_thanks.md: 60-120 words
    "linkedin_message_max_words": 120,  # draft-outreach: 60-120 words
    "linkedin_note_max_chars": 300,     # linkedin_note.md: LinkedIn's hard limit
    "autosend_email_confidence": ["verified"],
}

CHECKS = ("outreach_manual_contacts", "linkedin_draft_only", "linkedin_note_length", "email_autosend_verified",
          "thank_you_manual", "outreach_word_counts", "outreach_cold_limit")
LEVELS = {c: "hard" for c in CHECKS} | {"outreach_word_counts": "soft"}

THANKS_KINDS = {"thank_you", "thanks", "post_interview_thanks", "interview_thanks"}
POST_APPLY_KINDS = {"post_apply_outreach", "post_apply", "after_apply"}
STATUS_KINDS = {"status_followup", "status", "no_response"}
MANUAL_SENDERS = {"candidate", "manual", "user", "human"}


def _key(name: Any) -> str:
    return str(name or "").strip().lower()


def _kind(d: dict[str, Any]) -> str:
    for f in ("kind", "type", "template"):
        v = d.get(f)
        if v:
            return str(v).strip().lower().removesuffix(".md").rsplit("/", 1)[-1]
    return ""


def _email_body(d: dict[str, Any]) -> str | None:
    e = d.get("email")
    if isinstance(e, dict):
        return str(e.get("body") or "") or None
    if isinstance(e, str) and e.strip():
        return e
    return str(d["body"]) if d.get("body") else None


def _is_linkedin(d: dict[str, Any]) -> bool:
    ch = _key(d.get("channel"))
    if ch:
        return ch == "linkedin"
    return _email_body(d) is None and bool(d.get("linkedin_note") or d.get("linkedin_message"))


def _system_sent(d: dict[str, Any]) -> bool:
    if d.get("auto_send") is True:
        return True
    return d.get("sent") is True and _key(d.get("sent_by")) not in MANUAL_SENDERS


def _followups(d: dict[str, Any]) -> list[str]:
    out = [f for f in ("followup_7d", "followup_14d") if d.get(f)]
    if d.get("followups"):
        out.append("followups")
    return out


def _skip_all(ck: Any, why: str) -> None:
    for c in CHECKS:
        ck.skip(c, LEVELS[c], why)


def _report(ck: Any, check: str, issues: list[str], ok_detail: str) -> None:
    ck.add(check, LEVELS[check], not issues, ok_detail if not issues else "; ".join(issues))


def check_outreach_policy(ck: Any) -> None:
    extras: dict[str, Any] = {"present": False, "drafts": 0, "manual_contacts": [], "violations": [],
                              "word_counts": []}
    ck.extras["outreach_policy"] = extras
    if ck.outreach_raw is None:
        _skip_all(ck, "no outreach.json")
        return
    extras["present"] = True
    if ck.outreach_error:
        ck.add("outreach_json_valid", "hard", False, f"outreach.json: {ck.outreach_error}")
        _skip_all(ck, "outreach.json unparseable")
        return
    data = ck.outreach
    if isinstance(data, list):
        data = {"drafts": data}
    if not isinstance(data, dict):
        ck.add("outreach_json_valid", "hard", False, "outreach.json is not an object")
        _skip_all(ck, "outreach.json unparseable")
        return

    cfg = {**DEFAULTS, **((ck.qa_cfg.get("outreach") or {}) if isinstance(ck.qa_cfg, dict) else {})}
    pcfg = ck.pipeline_cfg.get("outreach") or {}
    pcfg = pcfg if isinstance(pcfg, dict) else {}
    policy = OutreachPolicy(manual_if_connected=bool(pcfg.get("manual_if_connected", True)),
                            manual_if_mutuals=bool(pcfg.get("manual_if_mutuals", True)))
    autosend_ok = {_key(x) for x in (cfg["autosend_email_confidence"] or [])}

    contacts_raw = ck.contacts
    contacts: dict[str, dict[str, Any]] = {}
    if isinstance(contacts_raw, dict):
        for c in contacts_raw.get("contacts") or []:
            if isinstance(c, dict):
                contacts[_key(c.get("name"))] = c

    items = [d for d in (data.get("drafts") or []) if isinstance(d, dict)]
    items += [d for d in (data.get("followups") or []) if isinstance(d, dict)]
    extras["drafts"] = len(items)

    issues: dict[str, list[str]] = {c: [] for c in CHECKS}

    def flag(check: str, who: str, issue: str) -> None:
        issues[check].append(f"{who}: {issue}")
        extras["violations"].append({"check": check, "contact": who, "issue": issue})

    thanked = {_key(d.get("contact")) for d in items if _kind(d) in THANKS_KINDS}
    manual_names: list[str] = []
    per_contact: dict[str, dict[str, Any]] = {}

    for d in items:
        who = str(d.get("contact") or "<unnamed>")
        k = _key(who)
        kind = _kind(d)
        c = contacts.get(k, {})
        send_after = d.get("send_after")

        # 1. manual contacts
        manual, _ = needs_manual_outreach(c, policy) if c else (False, None)
        if not manual:
            manual, _ = needs_manual_outreach(d, policy)
        manual = manual or d.get("manual_tailor") is True or bool(d.get("manual_reason"))
        if manual:
            if who not in manual_names:
                manual_names.append(who)
            if d.get("manual_tailor") is not True:
                flag("outreach_manual_contacts", who, "manual contact without manual_tailor: true")
            if send_after:
                flag("outreach_manual_contacts", who, f"manual contact scheduled (send_after={send_after})")
            if _system_sent(d):
                flag("outreach_manual_contacts", who, "manual contact sent by the system")
            fu = _followups(d)
            if fu:
                flag("outreach_manual_contacts", who, f"manual contact has automated follow-ups ({', '.join(fu)})")

        # 2. LinkedIn is draft-only
        if d.get("linkedin_send_after"):
            flag("linkedin_draft_only", who, "linkedin_send_after set")
        if _is_linkedin(d):
            if send_after:
                flag("linkedin_draft_only", who, f"LinkedIn draft scheduled (send_after={send_after})")
            if _system_sent(d):
                flag("linkedin_draft_only", who, "LinkedIn draft sent by the system")

        # 3. auto-sent email needs the contact's verified address
        if send_after and not _is_linkedin(d) and kind not in THANKS_KINDS:
            to = _key(d.get("to"))
            if not to:
                flag("email_autosend_verified", who, "scheduled email has no recipient")
            elif not c:
                flag("email_autosend_verified", who, f"scheduled email to {to}: contact not in contacts.json")
            elif _key(c.get("email")) != to:
                flag("email_autosend_verified", who, f"scheduled email to {to} is not the contact's verified email")
            elif _key(c.get("email_confidence")) not in autosend_ok:
                flag("email_autosend_verified", who,
                     f"scheduled email to {to} has email_confidence={c.get('email_confidence') or 'unknown'}")

        # 4. thank-yous are always manual
        if kind in THANKS_KINDS:
            if send_after:
                flag("thank_you_manual", who, f"thank-you scheduled (send_after={send_after})")
            if _system_sent(d):
                flag("thank_you_manual", who, "thank-you sent by the system")

        # 5. lengths (soft)
        def over(field: str, n: int, limit: int, unit: str = "words") -> None:
            if n > limit:
                issues["outreach_word_counts"].append(f"{who} {field}: {n} {unit} > {limit}")
                extras["word_counts"].append({"contact": who, "kind": kind or "outreach", "field": field,
                                              unit: n, "limit": limit})

        body = _email_body(d)
        if body is not None:
            if kind in THANKS_KINDS:
                lim = cfg["thank_you_max_words"]
            elif kind in STATUS_KINDS:
                lim = cfg["status_followup_max_words"]
            elif kind in POST_APPLY_KINDS:
                lim = cfg["after_apply_max_words"]
            else:
                lim = cfg["cold_email_max_words"]
            over("email.body", count_words(body), int(lim))
        for f in ("followup_7d", "followup_14d"):
            if isinstance(d.get(f), str):
                over(f, count_words(d[f]), int(cfg["status_followup_max_words"]))
        note = d.get("linkedin_note")
        if isinstance(note, str):
            max_chars = int(cfg["linkedin_note_max_chars"])
            if len(note) > max_chars:  # hard: LinkedIn cuts the note off
                flag("linkedin_note_length", who, f"linkedin_note {len(note)} chars > {max_chars}")
            stated = d.get("linkedin_note_chars")
            if isinstance(stated, int) and stated != len(note):
                issues["outreach_word_counts"].append(
                    f"{who} linkedin_note_chars: says {stated}, note is {len(note)} chars")
        if isinstance(d.get("linkedin_message"), str):
            over("linkedin_message", count_words(d["linkedin_message"]), int(cfg["linkedin_message_max_words"]))

        # 6. tally for the cold-contact limit (thank-yous are not outreach)
        if kind not in THANKS_KINDS:
            pc = per_contact.setdefault(k, {"who": who, "outreach": 0, "followups": 0, "warm": False})
            if kind in STATUS_KINDS:
                pc["followups"] += 1
            else:
                pc["outreach"] += 1
                pc["followups"] += len([f for f in ("followup_7d", "followup_14d") if d.get(f)])
                if isinstance(d.get("followups"), list):
                    pc["followups"] += len(d["followups"])
            pc["warm"] = pc["warm"] or manual or bool(d.get("replied") or d.get("prior_reply"))
            pc["warm"] = pc["warm"] or bool(c.get("replied")) or k in thanked

    for pc in per_contact.values():
        if pc["warm"]:
            continue
        if pc["outreach"] > 1:
            flag("outreach_cold_limit", pc["who"], f"cold contact has {pc['outreach']} outreach drafts (max 1)")
        if pc["followups"] > 1:
            flag("outreach_cold_limit", pc["who"], f"cold contact has {pc['followups']} follow-ups (max 1)")

    extras["manual_contacts"] = manual_names
    _report(ck, "outreach_manual_contacts", issues["outreach_manual_contacts"],
            f"{len(manual_names)} manual contact(s), all hand-tailored and unscheduled")
    _report(ck, "linkedin_draft_only", issues["linkedin_draft_only"], "LinkedIn drafts unscheduled")
    _report(ck, "linkedin_note_length", issues["linkedin_note_length"],
            f"LinkedIn notes within {int(cfg['linkedin_note_max_chars'])} chars")
    _report(ck, "email_autosend_verified", issues["email_autosend_verified"],
            "scheduled emails go to verified addresses only")
    _report(ck, "thank_you_manual", issues["thank_you_manual"], "thank-yous unscheduled")
    _report(ck, "outreach_word_counts", issues["outreach_word_counts"], "lengths within limits")
    _report(ck, "outreach_cold_limit", issues["outreach_cold_limit"],
            "cold contacts: one outreach + at most one follow-up")
