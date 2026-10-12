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
