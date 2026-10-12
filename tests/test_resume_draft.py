"""Résumé draft (TASK-028, DEC-014, DEC-018 amendment): profile/resumes/<rid>/draft.json with `rev`."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from careeros import resumes

pytestmark = pytest.mark.unit

DOC = {"schema_version": 1, "experience": [{"id": "experience-1", "source": "exp-a", "bullets": [
    {"id": "experience-1.b1", "source": "b-a", "text": "Built the thing"}]}]}


def _resume(tmp_path: Path, doc: dict = DOC) -> str:
    src = tmp_path / "resume.json"
    src.write_text(json.dumps(doc), encoding="utf-8")
    return resumes.add_tailored(tmp_path, "text", category="x", source="job-1", files={"resume.json": src})["rid"]


def test_draft_starts_from_latest_and_rejects_stale_rev(tmp_path: Path):
    rid = _resume(tmp_path)
    d = resumes.get_draft(tmp_path, rid)
    assert d == {"rev": 0, "resume": resumes.migrate(DOC), "draft": False}
    edited = json.loads(json.dumps(DOC))
    edited["experience"][0]["bullets"][0]["text"] = "Built the better thing"
    out = resumes.put_draft(tmp_path, rid, edited, rev=0, author="user")
    assert out["rev"] == 1 and out["draft"] is True
    assert json.loads((tmp_path / "profile/resumes" / rid / "draft.json").read_text())["rev"] == 1
    with pytest.raises(resumes.Stale):  # a second tab still on rev 0
        resumes.put_draft(tmp_path, rid, DOC, rev=0, author="user")
    assert resumes.get_draft(tmp_path, rid)["resume"] == resumes.migrate(edited)


def _with_origin(doc: dict, text: str) -> dict:
    doc = json.loads(json.dumps(doc))
    doc["experience"][0]["bullets"].append({"id": "experience-1.b2", "text": text, "origin": "user"})
    return doc


def test_undo_by_hand_clears_draft_status(tmp_path: Path):
    rid = _resume(tmp_path)
    resumes.put_draft(tmp_path, rid, _with_origin(DOC, "Mine"), rev=0, author="user")
    out = resumes.put_draft(tmp_path, rid, DOC, rev=1, author="user")
    assert (out["rev"], out["draft"]) == (2, False)


def test_only_a_user_write_may_set_origin(tmp_path: Path):  # DEC-018 amendment
    rid = _resume(tmp_path)
    with pytest.raises(ValueError, match="origin"):
        resumes.put_draft(tmp_path, rid, _with_origin(DOC, "AI claim"), rev=0, author="ai")
    assert not (tmp_path / "profile/resumes" / rid / "draft.json").exists()
    mine = _with_origin(DOC, "Mine")
    assert resumes.put_draft(tmp_path, rid, mine, rev=0, author="user")["rev"] == 1
    # an AI write may keep the user's mark untouched, but not move it onto new text
    assert resumes.put_draft(tmp_path, rid, mine, rev=1, author="ai")["rev"] == 2
    with pytest.raises(ValueError, match="origin"):
        resumes.put_draft(tmp_path, rid, _with_origin(DOC, "Mine, embellished"), rev=2, author="ai")
    bad = _with_origin(DOC, "x")
    bad["experience"][0]["bullets"][1]["origin"] = "master"
    with pytest.raises(ValueError, match="origin"):
        resumes.put_draft(tmp_path, rid, bad, rev=2, author="user")
    with pytest.raises(ValueError, match="author"):
        resumes.put_draft(tmp_path, rid, DOC, rev=2, author="bot")


def test_startup_cleanup_removes_stale_temp_files_only(tmp_path: Path):
    rid = _resume(tmp_path)
    resumes.put_draft(tmp_path, rid, DOC, rev=0, author="user")
    d = tmp_path / "profile/resumes" / rid
    (d / ".draft.json.123.abcd1234.tmp").write_text("{")  # crash mid-write
    (d / ".v2.123.tmp").mkdir()  # not a file: skipped (no producer of temp dirs)
    target = tmp_path / "outside.txt"
    target.write_text("keep")
    (d / ".evil.tmp").symlink_to(target)  # symlink: skipped, never followed
    before = sorted(p.name for p in d.iterdir())
    for p in d.glob("*.tmp"):
        os.utime(p, (0, 0), follow_symlinks=False)
    (d / ".draft.json.456.live0000.tmp").write_text("{")  # a write in flight right now: kept
    assert resumes.cleanup_tmp(tmp_path) == 1
    assert sorted(p.name for p in d.iterdir()) == sorted(
        [n for n in before if n != ".draft.json.123.abcd1234.tmp"] + [".draft.json.456.live0000.tmp"])
    assert target.read_text() == "keep"
    assert resumes.cleanup_tmp(tmp_path / "nowhere") == 0


TWO = {"schema_version": 1, "experience": [
    {"id": "e1", "bullets": [{"id": "e1.b1", "text": "Built the thing"}]},
    {"id": "e2", "bullets": [{"id": "e2.b1", "text": "Ran the thing"}]}]}


def _draft_rev(tmp_path: Path, rid: str) -> int:
    return json.loads((tmp_path / "profile/resumes" / rid / "draft.json").read_text())["rev"]


def test_ai_may_not_move_a_marked_bullet_to_another_entry(tmp_path: Path):
    rid = _resume(tmp_path, TWO)
    mine = json.loads(json.dumps(TWO))
    mine["experience"][0]["bullets"].append({"id": "m", "text": "Mine", "origin": "user"})
    resumes.put_draft(tmp_path, rid, mine, rev=0, author="user")
    moved = json.loads(json.dumps(mine))
    moved["experience"][1]["bullets"].append(moved["experience"][0]["bullets"].pop())
    with pytest.raises(ValueError, match="origin"):
        resumes.put_draft(tmp_path, rid, moved, rev=1, author="ai")
    assert _draft_rev(tmp_path, rid) == 1


def test_marked_bullet_with_non_string_text_does_not_wedge_the_draft(tmp_path: Path):
    rid = _resume(tmp_path, TWO)
    odd = json.loads(json.dumps(TWO))
    odd["experience"][0]["bullets"].append({"id": "m", "text": ["x"], "origin": "user"})
    resumes.put_draft(tmp_path, rid, odd, rev=0, author="user")
    assert resumes.put_draft(tmp_path, rid, odd, rev=1, author="ai")["rev"] == 2

def test_ai_write_ids_omitted_reordered_and_duplicated(tmp_path: Path):
    rid = _resume(tmp_path)
    mine = _with_origin(DOC, "Mine")
    resumes.put_draft(tmp_path, rid, mine, rev=0, author="user")
    no_ids = json.loads(json.dumps(mine))
    for b in no_ids["experience"][0]["bullets"]:
        del b["id"]
    assert resumes.put_draft(tmp_path, rid, no_ids, rev=1, author="ai")["rev"] == 2  # same positional ids
    reordered = json.loads(json.dumps(mine))
    reordered["experience"][0]["bullets"].reverse()
    assert resumes.put_draft(tmp_path, rid, reordered, rev=2, author="ai")["rev"] == 3  # ids kept: fine
    no_ids["experience"][0]["bullets"].reverse()  # reordered without ids: mark lands on a new id
    with pytest.raises(ValueError, match="origin"):
        resumes.put_draft(tmp_path, rid, no_ids, rev=3, author="ai")
    dup = json.loads(json.dumps(mine))
    dup["experience"][0]["bullets"].append(dict(dup["experience"][0]["bullets"][1]))  # copy gets id -2
    with pytest.raises(ValueError, match="origin"):
        resumes.put_draft(tmp_path, rid, dup, rev=3, author="ai")
    assert _draft_rev(tmp_path, rid) == 3


def test_pre_v1_doc_is_migrated_on_put(tmp_path: Path):
    rid = _resume(tmp_path)
    old = {"experience": [{"id": "exp-a", "bullets": [{"id": "b-a", "text": "Built the thing"}]}]}
    out = resumes.put_draft(tmp_path, rid, old, rev=0, author="user")
    assert out["resume"] == resumes.migrate(old) and out["resume"]["schema_version"] == 1
    assert out["resume"]["experience"][0]["bullets"][0]["source"] == "b-a"


def test_concurrent_puts_exactly_one_wins(tmp_path: Path):
    rid = _resume(tmp_path)
    go, results = threading.Barrier(2), []

    def put(text: str) -> None:
        go.wait()
        try:
            results.append(resumes.put_draft(tmp_path, rid, _with_origin(DOC, text), rev=0, author="user")["rev"])
        except resumes.Stale:
            results.append("stale")

    ts = [threading.Thread(target=put, args=(t,)) for t in ("a", "b")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(results, key=str) == [1, "stale"]


def test_put_returns_what_it_wrote(tmp_path: Path, monkeypatch):
    rid = _resume(tmp_path)
    monkeypatch.setattr(resumes, "get_draft", lambda *a: pytest.fail("read after unlock"))
    out = resumes.put_draft(tmp_path, rid, _with_origin(DOC, "Mine"), rev=0, author="user")
    assert (out["rev"], out["draft"]) == (1, True)


def test_bad_rid_and_no_structured_version_refuse_like_get(tmp_path: Path):
    for rid in ("../x", "Bad"):
        with pytest.raises(LookupError):
            resumes.get_draft(tmp_path, rid)
        with pytest.raises(LookupError):
            resumes.put_draft(tmp_path, rid, DOC, rev=0, author="user")
    rid = resumes.add_tailored(tmp_path, "text", category="x", source="job-1")["rid"]
    with pytest.raises(LookupError) as g:
        resumes.get_draft(tmp_path, rid)
    with pytest.raises(LookupError) as p:
        resumes.put_draft(tmp_path, rid, DOC, rev=0, author="user")
    assert str(p.value) == str(g.value)
    assert not (tmp_path / "profile/resumes" / rid / "draft.json").exists()


@pytest.mark.parametrize("bad", [{"experience": [{"bullets": 5}]}, {"experience": 5}, {"sections": 5}])
def test_odd_shapes_are_value_errors(tmp_path: Path, bad: dict):
    rid = _resume(tmp_path)
    with pytest.raises(ValueError):
        resumes.put_draft(tmp_path, rid, bad, rev=0, author="user")
