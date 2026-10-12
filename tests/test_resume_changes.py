"""draft.changes.jsonl + revert (TASK-029, DEC-015): every draft write logs per-node changes; revert = inverse change."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from careeros import resumes

pytestmark = pytest.mark.unit

DOC = {"schema_version": 1, "summary": "S", "experience": [{"id": "experience-1", "source": "exp-a", "bullets": [
    {"id": "experience-1.b1", "source": "b-a", "text": "Built the thing"}]}]}


def _resume(tmp_path: Path, doc: dict = DOC) -> str:
    src = tmp_path / "resume.json"
    src.write_text(json.dumps(doc), encoding="utf-8")
    return resumes.add_tailored(tmp_path, "text", category="x", source="job-1", files={"resume.json": src})["rid"]


def _copy(doc: dict = DOC) -> dict:
    return json.loads(json.dumps(doc))


def _log(tmp_path: Path, rid: str) -> list[dict]:
    p = tmp_path / "profile/resumes" / rid / "draft.changes.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]


def test_every_write_logs_bullet_entry_and_field_changes(tmp_path: Path):
    rid = _resume(tmp_path)
    d = _copy()
    d["experience"][0]["bullets"][0]["text"] = "Built the better thing"
    d["experience"][0]["bullets"].append({"id": "mine", "text": "Mine", "origin": "user"})
    d["experience"][0]["title"] = "Lead"
    d["summary"] = "S2"
    resumes.put_draft(tmp_path, rid, d, rev=0, author="user")
    log = _log(tmp_path, rid)
    assert {(c["kind"], c["target_id"], c["op"]) for c in log} == {
        ("bullet", "experience-1.b1", "edit"), ("bullet", "mine", "add"),
        ("entry", "experience-1", "edit"), ("field", "summary", "edit")}
    by = {c["target_id"]: c for c in log}
    assert by["experience-1.b1"]["before"]["text"] == "Built the thing"
    assert by["experience-1.b1"]["after"]["text"] == "Built the better thing"
    assert by["mine"]["before"] is None and by["mine"]["where"] == {
        "section": "experience", "entry": "experience-1", "index": 1}
    assert "bullets" not in by["experience-1"]["after"] and by["experience-1"]["after"]["title"] == "Lead"
    assert all(c["author"] == "user" and c["at"] and "reverts" not in c for c in log)
    assert len({c["id"] for c in log}) == 4
    resumes.put_draft(tmp_path, rid, d, rev=1, author="ai")  # no-op write: nothing to log
    assert len(_log(tmp_path, rid)) == 4
    assert resumes.changes(tmp_path, rid) == log


def test_revert_appends_the_inverse_change(tmp_path: Path):
    rid = _resume(tmp_path)
    d = _copy()
    d["experience"][0]["bullets"][0]["text"] = "AI rewrite"
    resumes.put_draft(tmp_path, rid, d, rev=0, author="ai")
    cid = _log(tmp_path, rid)[0]["id"]
    out = resumes.revert_change(tmp_path, rid, cid)
    assert out["rev"] == 2 and out["resume"] == resumes.migrate(DOC) and out["draft"] is False
    last = _log(tmp_path, rid)[-1]
    assert (last["reverts"], last["author"], last["op"]) == (cid, "user", "edit")
    assert (last["before"]["text"], last["after"]["text"]) == ("AI rewrite", "Built the thing")


def test_revert_restores_deleted_bullet_and_entry_in_place(tmp_path: Path):
    doc = _copy()
    doc["experience"].append({"id": "experience-2", "source": "exp-b", "bullets": [
        {"id": "experience-2.b1", "source": "b-b", "text": "Two"}]})
    doc["experience"][0]["bullets"].append({"id": "experience-1.b2", "source": "b-c", "text": "Second"})
    rid = _resume(tmp_path, doc)
    d = _copy(doc)
    del d["experience"][0]["bullets"][0]
    del d["experience"][1]
    resumes.put_draft(tmp_path, rid, d, rev=0, author="user")
    log = _log(tmp_path, rid)
    ids = {c["target_id"]: c["id"] for c in log}
    with pytest.raises(resumes.Refused, match="experience-2"):  # its entry is gone: revert the entry first
        resumes.revert_change(tmp_path, rid, ids["experience-2.b1"])
    for t in ("experience-1.b1", "experience-2", "experience-2.b1"):
        out = resumes.revert_change(tmp_path, rid, ids[t])
    assert out["resume"] == resumes.migrate(doc)


def test_revert_refused_with_both_texts_when_target_changed_since(tmp_path: Path):
    rid = _resume(tmp_path)
    d = _copy()
    d["experience"][0]["bullets"][0]["text"] = "AI rewrite"
    resumes.put_draft(tmp_path, rid, d, rev=0, author="ai")
    cid = _log(tmp_path, rid)[0]["id"]
    d["experience"][0]["bullets"][0]["text"] = "My later edit"
    resumes.put_draft(tmp_path, rid, d, rev=1, author="user")
    with pytest.raises(resumes.Conflict) as e:
        resumes.revert_change(tmp_path, rid, cid)
    assert (e.value.expected, e.value.current) == ("AI rewrite", "My later edit")
    assert resumes.get_draft(tmp_path, rid)["rev"] == 2 and len(_log(tmp_path, rid)) == 2
    with pytest.raises(LookupError):
        resumes.revert_change(tmp_path, rid, "nope")


def test_user_texts_counts_only_bullets_a_user_change_last_wrote(tmp_path: Path):  # DEC-020
    rid = _resume(tmp_path)
    d = _copy()
    d["experience"][0]["bullets"].append({"id": "mine", "text": "Mine", "origin": "user"})
    d["experience"][0]["bullets"].append({"id": "gone", "text": "Gone", "origin": "user"})
    resumes.put_draft(tmp_path, rid, d, rev=0, author="user")
    del d["experience"][0]["bullets"][2]
    d["experience"][0]["bullets"][0]["text"] = "AI rewrite"
    resumes.put_draft(tmp_path, rid, d, rev=1, author="ai")
    assert resumes.user_texts(tmp_path, rid) == {"Mine"}
    assert resumes.user_texts(tmp_path, "nope") == set()


def _add(d: dict, bid: str, text: str, **kw) -> None:
    d["experience"][0]["bullets"].append({"id": bid, "text": text, **kw})


def _bullet(d: dict, bid: str) -> dict:
    return next(b for b in d["experience"][0]["bullets"] if b["id"] == bid)


def test_user_texts_ignores_user_lines_that_left_the_text_unchanged(tmp_path: Path):  # DEC-020
    rid = _resume(tmp_path)
    d = _copy()
    _add(d, "ai1", "AI text")
    resumes.put_draft(tmp_path, rid, d, rev=0, author="ai")
    _bullet(d, "ai1")["origin"] = "user"
    resumes.put_draft(tmp_path, rid, d, rev=1, author="user")
    assert _log(tmp_path, rid)[-1]["author"] == "user"
    assert "AI text" not in resumes.user_texts(tmp_path, rid)


def test_user_texts_revert_inherits_the_restored_texts_author(tmp_path: Path):  # DEC-020
    rid = _resume(tmp_path)
    d = _copy()
    _add(d, "mine", "Mine", origin="user")
    resumes.put_draft(tmp_path, rid, d, rev=0, author="user")
    _bullet(d, "mine")["text"] = "AI rewrite"
    del _bullet(d, "mine")["origin"]  # DEC-018: an AI text edit drops the mark
    resumes.put_draft(tmp_path, rid, d, rev=1, author="ai")
    resumes.revert_change(tmp_path, rid, _log(tmp_path, rid)[-1]["id"])
    assert resumes.user_texts(tmp_path, rid) == {"Mine"}

    tmp_path = tmp_path / "second"
    tmp_path.mkdir()
    rid = _resume(tmp_path)
    d = _copy()
    _add(d, "ai1", "AI text")
    resumes.put_draft(tmp_path, rid, d, rev=0, author="ai")
    _bullet(d, "ai1")["text"] = "User text"
    resumes.put_draft(tmp_path, rid, d, rev=1, author="user")
    assert resumes.user_texts(tmp_path, rid) == {"User text"}
    resumes.revert_change(tmp_path, rid, _log(tmp_path, rid)[-1]["id"])
    assert _log(tmp_path, rid)[-1]["author"] == "user"  # the actor stays on disk
    assert resumes.user_texts(tmp_path, rid) == set()


def test_user_texts_last_author_wins(tmp_path: Path):  # DEC-020, no monkeypatch
    rid = _resume(tmp_path)
    d = _copy()
    _add(d, "mine", "Mine", origin="user")
    resumes.put_draft(tmp_path, rid, d, rev=0, author="user")
    assert resumes.user_texts(tmp_path, rid) == {"Mine"}
    _bullet(d, "mine")["text"] = "AI took over"
    del _bullet(d, "mine")["origin"]
    resumes.put_draft(tmp_path, rid, d, rev=1, author="ai")
    assert resumes.user_texts(tmp_path, rid) == set()


def test_truncated_log_line_is_skipped_and_next_append_starts_a_new_line(tmp_path: Path):
    rid = _resume(tmp_path)
    d = _copy()
    _add(d, "mine", "Mine", origin="user")
    resumes.put_draft(tmp_path, rid, d, rev=0, author="user")
    p = tmp_path / "profile/resumes" / rid / "draft.changes.jsonl"
    p.write_text(p.read_text(encoding="utf-8") + '{"id": "2.1", "kind": "bul', encoding="utf-8")
    assert resumes.user_texts(tmp_path, rid) == {"Mine"} and len(resumes.changes(tmp_path, rid)) == 1
    d["summary"] = "S2"
    resumes.put_draft(tmp_path, rid, d, rev=1, author="user")
    assert [c["target_id"] for c in resumes.changes(tmp_path, rid)] == ["mine", "summary"]


def test_log_line_truncated_mid_utf8_char_is_skipped(tmp_path: Path):
    rid = _resume(tmp_path)
    d = _copy()
    _add(d, "mine", "Mine", origin="user")
    resumes.put_draft(tmp_path, rid, d, rev=0, author="user")
    p = tmp_path / "profile/resumes" / rid / "draft.changes.jsonl"
    p.write_bytes(p.read_bytes() + '{"after": "café'.encode()[:-1])
    assert resumes.user_texts(tmp_path, rid) == {"Mine"} and len(resumes.changes(tmp_path, rid)) == 1
