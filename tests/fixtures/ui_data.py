"""A small, fictional data tree for the UI tests: jobs across the lifecycle, action items, contacts and runs.

build_ui_data(root, now) writes it with the real Store / Tracker / RunStore under a temp repo root made by
conftest.make_temp_root. Status histories are written with fixed timestamps (relative to `now`) so the stat
maths is deterministic. Companies are made up; nothing here comes from a real candidate.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from careeros.config import Settings
from careeros.models import Posting, Score
from careeros.runs.store import RunStore, iso
from careeros.store import Store
from careeros.tracker import Tracker

# job key -> (company, title, status, fit, tier, safety verdict, days since found, days since applied)
JOBS: dict[str, tuple[str, str, str, int | None, str | None, str | None, int, int | None]] = {
    "found":     ("Acme Robotics", "Backend Engineer", "found", None, None, None, 1, None),
    "scored":    ("Globex", "Software Engineer I", "scored", 72, "C", "pass", 3, None),
    "queued":    ("Initech", "Platform Engineer", "queued", 88, "B", "pass", 4, None),
    "review":    ("Umbrella Labs", "Infrastructure Engineer", "needs_review", 91, "A", "review", 5, None),
    "applied":   ("Hooli", "New Grad Engineer", "applied", 84, "B", "pass", 8, 2),
    "interview": ("Stark Industries", "Software Engineer", "interview", 86, "A", "pass", 20, 12),
    "rejected":  ("Wayne Enterprises", "Data Engineer", "rejected", 77, "C", "pass", 30, 20),
    "skipped":   ("Vandelay Imports", "Sales Engineer", "skipped", 40, "C", "skip", 40, None),
}
# The smallest valid PNG (1x1, transparent): a screenshot stand-in.
PNG_1PX = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000""1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
REVIEW_FLOW = ["found", "scored", "queued", "prepared", "needs_review"]


def _history(status: str, found: datetime, applied: datetime | None) -> list[dict[str, Any]]:
    flow = {"found": ["found"], "scored": ["found", "scored"], "queued": ["found", "scored", "queued"],
            "needs_review": REVIEW_FLOW, "skipped": ["found", "skipped"],
            "applied": ["found", "scored", "queued", "applied"],
            "interview": ["found", "scored", "queued", "applied", "screening", "interview"],
            "rejected": ["found", "scored", "queued", "applied", "rejected"]}[status]
    out = []
    at = found
    for st in flow:
        if st == "applied" and applied:
            at = applied
        elif st in ("screening", "interview", "rejected") and applied:
            at = at + timedelta(days=3)
        else:
            at = at + timedelta(hours=1) if out else found
        out.append({"status": st, "at": iso(at), "note": None})
    return out


def build_ui_data(root: Path, now: datetime) -> dict[str, Any]:
    s = Settings.load(root)
    store = Store(s)
    ids: dict[str, str] = {}
    for key, (company, title, status, fit, tier, safety, found_days, applied_days) in JOBS.items():
        found = now - timedelta(days=found_days)
        applied = now - timedelta(days=applied_days) if applied_days is not None else None
        # One remote posting so the location filter and sort have something to separate.
        p = Posting(company=company, title=title, location="Remote" if company == "Globex" else "New York, NY",
                    ats="greenhouse",
                    ats_job_id=f"{key}-1", url=f"https://boards.example.com/{key}", fetched_at=iso(found),
                    description_text=f"{title} at {company}.")
        jid = p.job_id
        ids[key] = jid
        store._write(jid, "posting.json", p.model_dump())
        hist = _history(status, found, applied)
        store._write(jid, "status.json", {"status": status, "updated_at": hist[-1]["at"], "history": hist})
        store.append_log(jid, f"status -> {status}", component="fixture")
        if fit is not None:
            store.save_score(Score(job_id=jid, category="swe_backend", fit=fit, tier=tier,  # type: ignore[arg-type]
                                   reasons=["fixture"]))
        if safety:
            store._write(jid, "safety.json", {"job_id": jid, "checked_at": iso(found), "verdict": safety,
                                              "flags": [], "runs": []})
        if key in ("queued", "review", "applied", "interview"):
            # the qa-review skill's qa.json (.claude/skills/qa-review/SKILL.md section 6)
            store._write(jid, "qa.json", {
                "job_id": jid, "reviewed_at": iso(found), "deterministic": {"pass": True, "checks": []},
                "rubric": {k: {"score": v, "why": "fixture"} for k, v in (
                    ("relevance", 8), ("specificity", 8), ("voice_match", 8), ("zero_fabrication", 9),
                    ("ats_safety", 8))},
                "fabrication_audit": [], "unsupported_count": 0, "mean": 8.2, "pass": True, "fail_reasons": [],
                "regenerate_suggestions": [], "regenerations": 0})
            (store.job_dir(jid) / "resume.pdf").write_bytes(b"%PDF-1.4 fixture\n")
            (store.job_dir(jid) / "cover_letter.md").write_text("Hi,\n\nFixture letter.\n", encoding="utf-8")
    # Job detail's Safety flags, Apply session timeline and screenshot for the needs-review job.
    rid = ids["review"]
    store._write(rid, "safety.json", {
        "job_id": rid, "checked_at": iso(now - timedelta(days=5)), "verdict": "review", "runs": [],
        "flags": [{"code": "GHOST_OLD_POST", "level": "review", "detail": "Posted 45 days ago",
                   "evidence": ["https://boards.example.com/review"], "at": iso(now - timedelta(days=5))}]})
    shots = store.job_dir(rid) / "screenshots"
    shots.mkdir(exist_ok=True)
    (shots / "01_form.png").write_bytes(PNG_1PX)
    store._write(rid, "apply_session.json", {
        "job_id": rid, "ats": "greenhouse", "started": iso(now - timedelta(days=1)),
        "finished": iso(now - timedelta(days=1, minutes=-6)), "tier": "A", "auto_submit": False,
        "steps": [{"time": iso(now - timedelta(days=1)), "action": "open_form", "ok": True, "note": ""},
                  {"time": iso(now - timedelta(days=1, minutes=-5)), "action": "finish", "ok": False,
                   "note": "needs_review: Tier A: you submit"}],
        "screenshots": [str(shots / "01_form.png")], "outcome": "needs_review", "reason": "Tier A: you submit",
        "submit_clicked": False, "status": "needs_review", "n_steps": 2})
    contacts = {"contacts": [
        {"name": "Pat Rivers", "role": "Engineering Manager", "linkedin": "https://www.linkedin.com/in/example-pat",
         "email": "pat@example.com", "linkedin_degree": 1},
        {"name": "Sam Lee", "role": "Recruiter", "linkedin": "https://www.linkedin.com/in/example-sam",
         "mutuals": 0},
    ]}
    (store.job_dir(ids["interview"]) / "contacts.json").write_text(json.dumps(contacts, indent=2), encoding="utf-8")

    tr = Tracker(settings=s)
    tr.init()
    actions = {
        "high": tr.add_action_item("Review and submit", type="review", job_id=ids["review"], company="Umbrella Labs",
                                   role="Infrastructure Engineer", link="https://boards.example.com/review",
                                   priority="H", needs="laptop", due=iso(now + timedelta(days=1)),
                                   due_reason="posting closes"),
        "medium": tr.add_action_item("Answer the salary question", type="salary", job_id=ids["queued"],
                                     company="Initech", role="Platform Engineer", priority="M", needs="anytime"),
        "low": tr.add_action_item("Send the LinkedIn note", type="send_linkedin", job_id=ids["interview"],
                                  company="Stark Industries", role="Software Engineer", priority="L", needs="phone"),
        "done": tr.add_action_item("Solve the captcha", type="captcha", job_id=ids["applied"], company="Hooli",
                                   role="New Grad Engineer", priority="M", needs="laptop"),
    }
    tr.mark_action_done(actions["done"])

    rs = RunStore(s)
    runs = {}
    for name, kind, stop, started in (("score", "score", "completed", now - timedelta(hours=5)),
                                      ("prepare", "prepare", "usage_limit", now - timedelta(hours=3))):
        run = rs.new_run(kind, "schedule", {"preset": "small", "max_jobs": 2, "max_minutes": 30}, started)
        run.update({"status": "done", "stop_reason": stop, "ended_at": iso(started + timedelta(minutes=7)),
                    "duration_s": 420, "counters": {"attempted": 1, "ok": 1 if stop == "completed" else 0}})
        rs.save_run(run)
        rs.save_attempt(run["id"], {"n": 1, "job_id": ids["queued"], "outcome": "ok" if stop == "completed"
                                    else "usage_limit", "duration_s": 400, "session_id": "sess-1", "detail": ""})
        runs[name] = run["id"]
    return {"settings": s, "jobs": ids, "actions": actions, "runs": runs, "now": now}


def add_outreach_data(data: dict[str, Any]) -> dict[str, Any]:
    """Opt-in extra for the Contacts and Inbox screens: contacts + outreach drafts (the find-contacts and
    draft-outreach skills' shapes), an inbox-sync log line and a pending sync update. Kept out of build_ui_data so
    the counts other tests assert stay as they are. All names and addresses are fictional (example.com)."""
    s, ids, now = data["settings"], data["jobs"], data["now"]
    store = Store(s)
    hooli, stark = ids["applied"], ids["interview"]
    (store.job_dir(hooli) / "contacts.json").write_text(json.dumps({"job_id": hooli, "company": "Hooli", "contacts": [
        {"name": "Dana Cruz", "title": "Technical Recruiter", "role": "recruiter", "confidence": "high",
         "linkedin": "https://www.linkedin.com/in/example-dana", "email": "dana.cruz@example.com",
         "email_confidence": "verified", "email_candidates": ["dana.cruz@example.com"],
         "linkedin_degree": None, "mutuals": None},
    ]}, indent=2), encoding="utf-8")
    base = {"linkedin_note_chars": 0, "bullet_ids": [], "narrative_ids": [], "facts_used": [],
            "manual_tailor": False, "manual_reason": None, "send_after": None, "linkedin_send_after": None,
            "auto_send": False, "sent": False, "sent_by": None, "followup_7d": None, "followup_14d": None}
    (store.job_dir(hooli) / "outreach.json").write_text(json.dumps({
        "job_id": hooli, "company": "Hooli", "drafted_at": iso(now - timedelta(days=1)),
        "drafts": [{**base, "contact": "Dana Cruz", "role": "recruiter", "to": "dana.cruz@example.com",
                    "to_confidence": "verified", "kind": "post_apply_outreach", "channel": "email",
                    "linkedin_note": "Hi Dana, I applied to the New Grad Engineer role at Hooli.",
                    "linkedin_message": None,
                    "email": {"subject": "New Grad Engineer application",
                              "body": "Hi Dana,\n\nI applied for the New Grad Engineer role this week. "
                                      "[SPECIFIC CONNECTION]\n\nHappy to share more about "
                                      "[MOST RELEVANT EXPERIENCE]. Thanks for reading.\n\nAlex"}}],
        "followups": [], "review_required": True}, indent=2), encoding="utf-8")
    (store.job_dir(stark) / "outreach.json").write_text(json.dumps({
        "job_id": stark, "company": "Stark Industries", "drafted_at": iso(now - timedelta(days=9)),
        "drafts": [
            {**base, "contact": "Pat Rivers", "role": "hiring_manager", "to": "pat@example.com",
             "to_confidence": "low", "kind": "cold_email", "channel": "linkedin", "manual_tailor": True,
             "manual_reason": "LINKEDIN_CONNECTED", "linkedin_note": "Hi Pat, good to see the team growing.",
             "linkedin_message": "Hi Pat,\n\nI applied to the Software Engineer role on your team.",
             "email": {"subject": "Software Engineer", "body": "Hi Pat,\n\nShort note."}},
            {**base, "contact": "Sam Lee", "role": "recruiter", "to": None, "to_confidence": "low",
             "kind": "cold_email", "channel": "linkedin",
             "linkedin_note": "Hi Sam, I applied to the Software Engineer role at Stark Industries.",
             "linkedin_message": "Hi Sam,\n\nI applied to the Software Engineer role and would like to connect.",
             "email": None},
        ],
        "followups": [{**base, "contact": "Pat Rivers", "kind": "post_interview_thanks", "channel": "email",
                       "to": "pat@example.com", "to_confidence": "low",
                       "email": {"subject": "Thank you", "body": "Hi Pat,\n\nThank you for [INTERVIEW DETAIL]."}}],
        "review_required": True}, indent=2), encoding="utf-8")
    invite_at = now - timedelta(days=2)
    # the inbox-sync skill's log line (section 4), stamped at a fixed local time so tests are deterministic
    with (store.job_dir(stark) / "log.md").open("a", encoding="utf-8") as f:
        f.write(f"- {invite_at.astimezone().strftime('%Y-%m-%d %H:%M:%S')} [inbox-sync] interview_invite from "
                f"recruiting@example.com {invite_at.date().isoformat()} -> status interview "
                f"(https://mail.google.com/mail/u/0/#all/thread-stark-1)\n")
    Path(s.paths["jobs_dir"]).parent.joinpath("sync_updates.json").write_text(json.dumps([
        {"job_id": hooli, "company": "Hooli", "status": "screening", "note": "assessment invite",
         "source_thread": "thread-hooli-1", "date": invite_at.date().isoformat(), "applied": False}]), encoding="utf-8")
    return data


def add_scam_case(data: dict[str, Any]) -> dict[str, Any]:
    """A blocked posting at a made-up company, its flagged-registry entry and the open `scam_suspected` item the
    safety gate writes (Action Items' Block company / Mark posting safe). Kept out of build_ui_data so the counts
    other tests rely on stay put. Returns {"job_id", "action_id", "company"}."""
    from careeros.safety import registry

    s, now = data["settings"], data["now"]
    store = Store(s)
    company = "Obsidian Quant Partners"
    found = now - timedelta(days=2)
    p = Posting(company=company, title="Quant Developer", location="Remote", ats="custom", ats_job_id="scam-1",
                url="https://obsidian-careers.example/jobs/1", fetched_at=iso(found),
                description_text="Buy the equipment kit before your first day.")
    jid = p.job_id
    store._write(jid, "posting.json", p.model_dump())
    hist = [{"status": st, "at": iso(found + timedelta(hours=i)), "note": None}
            for i, st in enumerate(["found", "scored", "needs_review"])]
    store._write(jid, "status.json", {"status": "needs_review", "updated_at": hist[-1]["at"], "history": hist})
    store.save_score(Score(job_id=jid, category="swe_backend", fit=74, tier=None, reasons=["fixture"]))
    store._write(jid, "safety.json", {"job_id": jid, "checked_at": iso(found), "verdict": "block", "runs": [],
                                      "flags": [{"code": "SCAM_PAYMENT_REQUEST", "level": "block",
                                                 "detail": "asks for payment", "evidence": []}]})
    registry.add_or_bump(registry.default_path(s), company, domain="obsidian-careers.example",
                         reason="SCAM_PAYMENT_REQUEST", job_id=jid)
    aid = Tracker(settings=s).add_action_item(
        "Posting asks for a paid equipment kit. Block the company or mark the posting safe", type="scam_suspected",
        job_id=jid, company=company, role="Quant Developer", link="https://obsidian-careers.example/jobs/1",
        priority="H", needs="phone")
    data["jobs"]["scam"] = jid
    data["actions"]["scam"] = aid
    return {"job_id": jid, "action_id": aid, "company": company}


def add_prepare_candidates(settings: Settings, now: datetime) -> dict[str, str]:
    """Scored jobs the next prepare run ranks: several companies and fits (fit-first within a company), a
    deadline stated only in the description, a first_published date, and the ones select_candidates drops or
    excludes (pruned, already prepared, a deferred requeue that counts, a title the scout filters reject)."""
    from careeros.company_policy import DEFERRED_REASONS

    store = Store(settings)
    ids: dict[str, str] = {}
    rows = [  # key, company, title, status, fit, decision, extra posting fields, extra files
        ("p_hi", "Globex", "Software Engineer", "scored", 91, "prepare", {}, {}),
        ("p_lo", "Globex", "Backend Engineer", "scored", 70, "prepare", {}, {}),
        ("p_mid", "Hooli", "Software Engineer", "found", 80, "prepare",
         {"description_text": "Applications close 2026-09-30."}, {}),
        ("p_pub", "Pied Piper", "Software Engineer", "scored", 75, "prepare",
         {"first_published": iso(now - timedelta(days=1))}, {}),
        ("p_req", "Vandelay", "Software Engineer", "scored", 65, "skip", {}, {}),
        ("p_pruned", "Soylent", "Software Engineer", "scored", 88, "prepare", {"pruned": True}, {}),
        ("p_done", "Wonka", "Software Engineer", "scored", 90, "prepare", {}, {"prepare.json": {"qa_pass": True}}),
        ("p_title", "Tyrell", "Office Manager", "scored", 85, "prepare", {}, {}),
    ]
    for i, (key, company, title, status, fit, decision, extra, files) in enumerate(rows):
        found = now - timedelta(days=3 + i)
        p = Posting(company=company, title=title, location="New York, NY", ats="greenhouse",
                    ats_job_id=f"{key}-1", url=f"https://boards.example.com/{key}", fetched_at=iso(found),
                    description_text=extra.pop("description_text", f"{title} at {company}."),
                    first_published=extra.pop("first_published", None))
        jid = p.job_id
        ids[key] = jid
        store._write(jid, "posting.json", {**p.model_dump(), **extra})
        store._write(jid, "status.json", {"status": status, "updated_at": iso(found),
                                          "history": [{"status": status, "at": iso(found)}]})
        score = {"job_id": jid, "category": "swe_backend", "fit": fit, "decision": decision}
        if key == "p_req":
            score["skip_reason"] = next(iter(DEFERRED_REASONS))
        store._write(jid, "score.json", score)
        for name, body in files.items():
            store._write(jid, name, body)
    return ids
