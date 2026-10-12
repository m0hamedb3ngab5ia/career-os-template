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
