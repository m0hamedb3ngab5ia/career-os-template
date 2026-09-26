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
        p = Posting(company=company, title=title, location="New York, NY", ats="greenhouse",
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
                                   priority="H", needs="laptop"),
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
