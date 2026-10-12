"""Résumé draft (TASK-028, DEC-014, DEC-018 amendment): profile/resumes/<rid>/draft.json with `rev`."""
from __future__ import annotations

import json
import os
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


def test_startup_cleanup_removes_stale_temp_files_and_dirs(tmp_path: Path):
    rid = _resume(tmp_path)
    resumes.put_draft(tmp_path, rid, DOC, rev=0, author="user")
    d = tmp_path / "profile/resumes" / rid
    (d / ".draft.json.123.abcd1234.tmp").write_text("{")  # crash mid-write
    (d / ".v2.123.tmp").mkdir()  # crash mid-publish (temp dir)
    (d / ".v2.123.tmp" / "resume.json").write_text("{}")
    before = sorted(p.name for p in d.iterdir())
    for p in d.glob("*.tmp"):
        os.utime(p, (0, 0))
    (d / ".draft.json.456.live0000.tmp").write_text("{")  # a write in flight right now: kept
    assert resumes.cleanup_tmp(tmp_path) == 2
    assert sorted(p.name for p in d.iterdir()) == sorted(
        [n for n in before if not n.endswith(".tmp")] + [".draft.json.456.live0000.tmp"])
    assert resumes.cleanup_tmp(tmp_path / "nowhere") == 0
