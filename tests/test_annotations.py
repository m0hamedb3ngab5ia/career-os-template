"""annotations.json (TASK-030 part A, DEC-016): suggestions + comments, replies, accept through the draft change log."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from careeros import annotations as ann
from careeros import resume_feedback as fb
from careeros import resumes

pytestmark = pytest.mark.unit

DOC = {"schema_version": 1, "summary": "Engineer", "experience": [{"id": "experience-1", "source": "exp-a", "bullets": [
    {"id": "experience-1.b1", "source": "b-a", "text": "Built the billing service"},
    {"id": "mine", "text": "Ran the billing service", "origin": "user"}]}]}


def _resume(tmp_path: Path) -> str:
    src = tmp_path / "resume.json"
    src.write_text(json.dumps(DOC), encoding="utf-8")
    return resumes.add_tailored(tmp_path, "text", category="x", source="job-1", files={"resume.json": src})["rid"]


def _bullet(doc: dict, bid: str) -> dict:
    return next(b for e in doc["experience"] for b in e["bullets"] if b["id"] == bid)


def test_create_list_reply_reject(tmp_path: Path):
    rid = _resume(tmp_path)
    s = ann.create(tmp_path, rid, kind="suggestion", target_id="experience-1.b1", proposed="Built billing",
                   text="shorter", author="ai")
    assert (s["kind"], s["status"], s["base"], s["author"], s["replies"]) == (
        "suggestion", "open", "Built the billing service", "ai", [])
    c = ann.create(tmp_path, rid, kind="comment", target_id="summary", text="too vague")
    assert c["base"] == "Engineer" and c["author"] == "user" and c["id"] != s["id"]
    ann.reply(tmp_path, rid, c["id"], "agreed", author="ai")
    assert [r["text"] for r in ann.list_items(tmp_path, rid)[1]["replies"]] == ["agreed"]
    assert ann.reject(tmp_path, rid, s["id"])["status"] == "rejected"
    with pytest.raises(resumes.Refused):
        ann.accept(tmp_path, rid, s["id"])
    with pytest.raises(ValueError):
        ann.create(tmp_path, rid, kind="suggestion", target_id="summary", text="no proposal")
    with pytest.raises(ValueError):
        ann.create(tmp_path, rid, kind="nope", target_id="summary", text="x")
    with pytest.raises(LookupError):
        ann.create(tmp_path, rid, kind="comment", target_id="missing", text="x")
    with pytest.raises(LookupError):
        ann.reply(tmp_path, rid, "a99", "x")


def test_target_changed_since_base_is_outdated(tmp_path: Path):
    rid = _resume(tmp_path)
    s = ann.create(tmp_path, rid, kind="suggestion", target_id="experience-1.b1", proposed="Built billing", author="ai")
    d = resumes.get_draft(tmp_path, rid)["resume"]
    _bullet(d, "experience-1.b1")["text"] = "Built the billing service fast"
    resumes.put_draft(tmp_path, rid, d, rev=0, author="user")
    assert ann.list_items(tmp_path, rid)[0]["status"] == "outdated"
    with pytest.raises(resumes.Conflict) as e:  # 409 with both texts
        ann.accept(tmp_path, rid, s["id"])
    assert (e.value.expected, e.value.current) == ("Built the billing service", "Built the billing service fast")


def test_accept_writes_ai_draft_change_and_clears_origin(tmp_path: Path):
    rid = _resume(tmp_path)
    s = ann.create(tmp_path, rid, kind="suggestion", target_id="mine", proposed="Ran billing service",
                   text="tighter", author="ai")
    out = ann.accept(tmp_path, rid, s["id"])
    b = _bullet(out["resume"], "mine")
    assert b["text"] == "Ran billing service" and "origin" not in b  # DEC-018 amendment
    last = resumes.changes(tmp_path, rid)[-1]
    assert (last["author"], last["target_id"], last["after"]["text"]) == ("ai", "mine", "Ran billing service")
    assert ann.list_items(tmp_path, rid)[0]["status"] == "accepted"
    assert "Ran billing service" not in resumes.user_texts(tmp_path, rid)
    f = ann.create(tmp_path, rid, kind="suggestion", target_id="summary", proposed="Engineer.", author="ai")
    assert ann.accept(tmp_path, rid, f["id"])["resume"]["summary"] == "Engineer."


def test_accept_refused_by_zero_fabrication_guard(tmp_path: Path):
    rid = _resume(tmp_path)
    s = ann.create(tmp_path, rid, kind="suggestion", target_id="experience-1.b1",
                   proposed="Led the billing service for 40 people", author="ai")
    with pytest.raises(fb.Rejected) as e:
        ann.accept(tmp_path, rid, s["id"])
    assert "40" in str(e.value) and "led" in str(e.value).lower()
    assert ann.list_items(tmp_path, rid)[0]["status"] == "open" and resumes.changes(tmp_path, rid) == []
    with pytest.raises(resumes.Refused):  # comments are not accepted
        ann.accept(tmp_path, rid, ann.create(tmp_path, rid, kind="comment", target_id="summary", text="x")["id"])


def test_feedback_items_migrate_on_read_idempotently(tmp_path: Path):
    rid = _resume(tmp_path)
    p = tmp_path / "profile/resumes" / rid / "feedback.json"
    old = {"review": None, "items": [
        {"id": "f1", "section": "Summary", "issue": "vague", "suggestion": "name the stack", "quote": "Engineer",
         "state": "applied", "comments": [{"text": "ok", "at": "t"}], "reason": None, "v": 1},
        {"id": "f2", "section": "X", "issue": "i", "suggestion": "s", "quote": None, "state": "redrafting",
         "comments": [], "reason": None, "v": 1}]}
    p.write_text(json.dumps(old), encoding="utf-8")
    items = ann.list_items(tmp_path, rid)
    assert [(i["id"], i["kind"], i["status"]) for i in items] == [("f1", "comment", "accepted"), ("f2", "comment", "open")]
    assert items[0]["replies"][0]["text"] == "ok" and "name the stack" in items[0]["text"]
    assert ann.list_items(tmp_path, rid) == items
    ann.reply(tmp_path, rid, "f2", "hi")
    assert [i["id"] for i in ann.list_items(tmp_path, rid)] == ["f1", "f2"]  # persisted once, not re-migrated
    assert json.loads(p.read_text(encoding="utf-8")) == old  # old file kept readable, untouched


def test_ai_text_and_ai_replies_do_not_widen_the_guard(tmp_path: Path):
    rid = _resume(tmp_path)
    rust = "Built the billing service in Rust"
    s = ann.create(tmp_path, rid, kind="suggestion", target_id="experience-1.b1", proposed=rust,
                   text="name the language: Rust", author="ai")
    ann.reply(tmp_path, rid, s["id"], "it was Rust, right?", author="ai")
    with pytest.raises(fb.Rejected, match="rust"):  # AI words never widen the guard
        ann.accept(tmp_path, rid, s["id"])
    ann.reply(tmp_path, rid, s["id"], "yes, Rust")  # the user's own words do
    out = ann.accept(tmp_path, rid, s["id"])
    assert _bullet(out["resume"], "experience-1.b1")["text"] == rust


def test_user_suggestion_accept_is_a_user_change_without_guard(tmp_path: Path):
    rid = _resume(tmp_path)
    s = ann.create(tmp_path, rid, kind="suggestion", target_id="mine", proposed="Ran billing for 40 people")
    out = ann.accept(tmp_path, rid, s["id"])
    b = _bullet(out["resume"], "mine")
    assert b["text"] == "Ran billing for 40 people" and b["origin"] == "user"  # as put_draft: origin untouched
    assert resumes.changes(tmp_path, rid)[-1]["author"] == "user"


def test_new_ids_follow_max_suffix(tmp_path: Path):
    rid = _resume(tmp_path)
    p = tmp_path / "profile/resumes" / rid / "annotations.json"
    p.write_text(json.dumps({"items": [{"id": "a5", "kind": "comment", "target_id": None, "base": None,
                                        "author": "user", "status": "open", "proposed": None, "text": "x",
                                        "replies": [], "at": None}]}), encoding="utf-8")
    assert ann.create(tmp_path, rid, kind="comment", target_id=None, text="y")["id"] == "a6"


def test_new_feedback_items_still_show_after_annotations_exist(tmp_path: Path):
    rid = _resume(tmp_path)
    ann.create(tmp_path, rid, kind="comment", target_id="summary", text="first")  # annotations.json now exists
    p = tmp_path / "profile/resumes" / rid / "feedback.json"
    old = {"review": None, "items": [{"id": "f1", "section": "S", "issue": "i", "suggestion": "s", "quote": None,
                                      "state": "open", "comments": [], "reason": None, "v": 1}]}
    p.write_text(json.dumps(old), encoding="utf-8")
    assert [i["id"] for i in ann.list_items(tmp_path, rid)] == ["a1", "f1"]
    ann.reject(tmp_path, rid, "f1")
    assert [(i["id"], i["status"]) for i in ann.list_items(tmp_path, rid)] == [("a1", "open"), ("f1", "rejected")]
    assert json.loads(p.read_text(encoding="utf-8")) == old  # never written


def test_feedback_base_is_the_first_quote(tmp_path: Path):  # review items store `quotes`; `quote` is legacy
    rid = _resume(tmp_path)
    (tmp_path / "profile/resumes" / rid / "feedback.json").write_text(json.dumps({"review": None, "items": [
        {"id": "f1", "section": "S", "issue": "i", "suggestion": "s", "quotes": ["Engineer", "x"], "state": "open",
         "comments": [], "v": 1},
        {"id": "f2", "section": "S", "issue": "i", "suggestion": "s", "state": "open", "comments": [], "v": 1}]}),
        encoding="utf-8")
    assert [i["base"] for i in ann.list_items(tmp_path, rid)] == ["Engineer", None]


def _run(tmp_path: Path, kind: str, rid: str, item: str | None, fake) -> dict:
    from careeros.ui.services.step import run_resume_skill
    return run_resume_skill(type("S", (), {"root": tmp_path})(), kind, rid, item, run_skill=fake)


def test_apply_comment_run_proposes_and_never_edits_the_draft(tmp_path: Path):  # DEC-016
    rid = _resume(tmp_path)
    c = ann.create(tmp_path, rid, kind="comment", target_id="experience-1.b1", text="shorter please")
    before = resumes.get_draft(tmp_path, rid)

    def skill(settings, stage, prompt, **kw):
        assert (stage, prompt) == ("resume_edit", f"edit-resume {rid} {c['id']}")
        ann.reply(tmp_path, rid, c["id"], "proposed a shorter line", author="ai")
        ann.create(tmp_path, rid, kind="suggestion", target_id="experience-1.b1", proposed="Built billing",
                   author="ai")
        return {"id": "r1", "stop_reason": "completed"}

    _run(tmp_path, "resume_edit", rid, c["id"], skill)
    items = ann.list_items(tmp_path, rid)
    assert [(i["kind"], i["author"], i["status"]) for i in items] == [("comment", "user", "open"),
                                                                       ("suggestion", "ai", "open")]
    assert items[0]["replies"][-1]["author"] == "ai"
    assert resumes.get_draft(tmp_path, rid) == before and resumes.changes(tmp_path, rid) == []
    assert len(resumes.get(tmp_path, rid)["versions"]) == 1


def test_apply_comment_run_keeps_a_version_the_user_published_meanwhile(tmp_path: Path):  # Done during the run
    rid = _resume(tmp_path)
    c = ann.create(tmp_path, rid, kind="comment", target_id="summary", text="shorter")
    n = len(resumes.get(tmp_path, rid)["versions"])

    def skill(*a, **kw):
        fb.edit(tmp_path, rid, "Hand edit published by the user")
        ann.reply(tmp_path, rid, c["id"], "ok", author="ai")
        return {"id": "r1", "stop_reason": "completed"}

    _run(tmp_path, "resume_edit", rid, c["id"], skill)
    assert len(resumes.get(tmp_path, rid)["versions"]) == n + 1
    assert not list((tmp_path / "profile/resumes" / rid).glob("rejected-v*"))


def test_review_run_writing_annotations_is_done(tmp_path: Path):  # review-resume writes annotations, not feedback
    rid = _resume(tmp_path)

    def skill(*a, **kw):
        ann.create(tmp_path, rid, kind="comment", target_id="summary", text="name the stack", author="ai")
        return {"id": "r1", "stop_reason": "completed"}

    _run(tmp_path, "review", rid, None, skill)
    assert fb.load(tmp_path, rid)["review"]["state"] == "done"
    _run(tmp_path, "review", rid, None, lambda *a, **kw: {"id": "r2", "stop_reason": "max_turns"})
    assert fb.load(tmp_path, rid)["review"]["state"] == "failed"


def test_review_and_edit_runs_cannot_write_files():  # DEC-016: annotations only via the CLI, no direct draft edit
    from careeros.runs.config import KIND_ONLY_TOOLS
    narrow = ["Read", "Bash(.venv/bin/careeros resume annotations *)", "Bash(.venv/bin/careeros resume annotate *)",
              "Bash(.venv/bin/careeros resume annotate-reply *)", "Bash(.venv/bin/careeros resume list *)"]  # not every careeros command (e.g. apply-edit)
    for kind in ("review", "resume_edit"):
        assert KIND_ONLY_TOOLS[kind] == narrow


def test_completed_runs_without_new_ai_annotations_fail(tmp_path: Path):  # a "done" run must have proposed something
    rid = _resume(tmp_path)
    old = ann.create(tmp_path, rid, kind="comment", target_id="summary", text="earlier", author="ai")  # not this run's
    u = ann.create(tmp_path, rid, kind="comment", target_id="summary", text="shorter")
    rec = _run(tmp_path, "review", rid, None, lambda *a, **kw: {"id": "r1", "stop_reason": "completed"})
    review = fb.load(tmp_path, rid)["review"]
    assert review["state"] == "failed" and "no annotations" in review["reason"]
    assert rec["stop_reason"] == "failed" and "no annotations" in rec["detail"]

    def reply_only(*a, **kw):
        ann.reply(tmp_path, rid, u["id"], "noted", author="user")
        return {"id": "r2", "stop_reason": "completed"}

    rec = _run(tmp_path, "resume_edit", rid, u["id"], reply_only)
    assert rec["stop_reason"] == "failed" and "no annotations" in rec["detail"]
    assert old["author"] == "ai"

    def ai_reply_only(*a, **kw):  # edit-resume may legitimately only reply and say why (SKILL.md, action replied)
        ann.reply(tmp_path, rid, u["id"], "keeping it, the number is in the source", author="ai")
        return {"id": "r3", "stop_reason": "completed"}

    rec = _run(tmp_path, "resume_edit", rid, u["id"], ai_reply_only)
    assert rec["stop_reason"] == "completed"


def test_run_stamp_and_filter(tmp_path: Path):  # TASK-033b: Apply-comment polling by run id
    rid = _resume(tmp_path)
    u = ann.create(tmp_path, rid, kind="comment", target_id="summary", text="shorter")
    s = ann.create(tmp_path, rid, kind="suggestion", target_id="summary", proposed="Eng", author="ai", run="r1")
    assert s["run"] == "r1" and "run" not in u
    ann.reply(tmp_path, rid, u["id"], "on it", author="ai", run="r2")
    assert [i["id"] for i in ann.list_items(tmp_path, rid, run="r1")] == [s["id"]]
    assert [i["id"] for i in ann.list_items(tmp_path, rid, run="r2")] == [u["id"]]
    assert ann.list_items(tmp_path, rid, run="r9") == []
    assert (ann.run_count(tmp_path, rid, "r1"), ann.run_count(tmp_path, rid, "r2"),
            ann.run_count(tmp_path, rid, "r9")) == (1, 1, 0)


def test_step_counts_only_this_runs_annotations(tmp_path: Path):  # TASK-033b: another run's writes don't count
    from careeros.ui.services.step import run_resume_skill
    rid = _resume(tmp_path)
    u = ann.create(tmp_path, rid, kind="comment", target_id="summary", text="shorter")

    def other_run_writes(*a, **kw):  # a concurrent run on the same résumé proposes; this run wrote nothing
        ann.create(tmp_path, rid, kind="comment", target_id="summary", text="x", author="ai", run="other")
        return {"id": "mine", "stop_reason": "completed"}

    S = type("S", (), {"root": tmp_path})()
    rec = run_resume_skill(S, "resume_edit", rid, u["id"], run_skill=other_run_writes, run_id="mine")
    assert rec["stop_reason"] == "failed" and "no annotations" in rec["detail"]

    def this_run_replies(*a, **kw):
        ann.reply(tmp_path, rid, u["id"], "kept", author="ai", run="mine2")
        return {"id": "mine2", "stop_reason": "completed"}

    rec = run_resume_skill(S, "resume_edit", rid, u["id"], run_skill=this_run_replies, run_id="mine2")
    assert rec["stop_reason"] == "completed"
