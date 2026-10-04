"""Review feedback lifecycle (REQ-094..097, UC-002, FLOW-002, TASK-008): review items -> apply (guarded, new ai
version) / comment (redraft) / dismiss; hand edit = new user version, no guard."""
from __future__ import annotations

from pathlib import Path

import pytest

from careeros import resume_feedback as fb
from careeros import resumes

pytestmark = [pytest.mark.unit]

V1 = "Jane Doe\nExperience\nAcme Corp, Engineer 2021-2023\n- Supported migration of 12 services to Python\n"


@pytest.fixture
def rid(tmp_path: Path) -> str:
    m = resumes.add(tmp_path, "cv.pdf", b"%PDF-1.4\n")
    resumes.add_text(tmp_path, m["rid"], V1, author="user", source="edit")  # parsed content to work on
    return m["rid"]


def _item(root: Path, rid: str) -> str:
    out = fb.save_review(root, rid, [{"section": "Experience", "issue": "weak verb", "suggestion": "say what moved"}])
    assert out["review"]["state"] == "done"
    return out["items"][0]["id"]


@pytest.mark.parametrize("new, why", [
    (V1.replace("12 services", "40% of 12 services"), "40%"),       # E2E-002-02 new number
    (V1.replace("Supported", "Led"), "led"),                         # E2E-002-04 stronger claim
    (V1.replace("to Python", "to Python and Kubernetes"), "Kubernetes"),  # new tool
    (V1.replace("2021-2023", "2020-2023"), "2020"),                  # new date
    (V1.replace("Engineer", "Senior Engineer"), "senior"),           # seniority
])
def test_guard_rejects_fabrication(new: str, why: str):
    reasons = fb.guard(V1, new)
    assert reasons and why.lower() in " ".join(reasons).lower()


def test_guard_allows_rewording():
    assert fb.guard(V1, V1.replace("Supported migration of", "Supported moving")) == []


def test_apply_ok_creates_ai_version(tmp_path: Path, rid: str):  # E2E-002-01
    fid = _item(tmp_path, rid)
    new = V1.replace("Supported migration of", "Supported moving")
    meta = fb.apply(tmp_path, rid, fid, new)
    assert meta["versions"][-1] == {**meta["versions"][-1], "n": 3, "author": "ai", "source": fid}
    assert resumes.version(tmp_path, rid, 3)["text"].strip() == new.strip()
    assert fb.load(tmp_path, rid)["items"][0]["state"] == "applied"


def test_apply_guard_fail_keeps_item_open(tmp_path: Path, rid: str):  # E2E-002-02
    fid = _item(tmp_path, rid)
    with pytest.raises(fb.Rejected, match="40%"):
        fb.apply(tmp_path, rid, fid, V1.replace("12 services", "40% of 12 services"))
    assert resumes.get(tmp_path, rid)["versions"][-1]["n"] == 2
    it = fb.load(tmp_path, rid)["items"][0]
    assert it["state"] == "open" and "40%" in it["reason"]


def test_comment_redraft_dismiss(tmp_path: Path, rid: str):
    fid = _item(tmp_path, rid)
    assert fb.comment(tmp_path, rid, fid, "keep the Python line")["state"] == "redrafting"
    it = fb.redraft(tmp_path, rid, fid, "say what moved, keep Python")
    assert it["state"] == "open" and it["suggestion"].endswith("keep Python")
    assert it["comments"][0]["text"] == "keep the Python line"
    assert resumes.get(tmp_path, rid)["versions"][-1]["n"] == 2  # nothing written until Apply
    assert fb.dismiss(tmp_path, rid, fid)["state"] == "dismissed"
    with pytest.raises(fb.Rejected):
        fb.apply(tmp_path, rid, fid, V1)  # only open items apply


def test_hand_edit_is_new_user_version(tmp_path: Path, rid: str):  # E2E-002-03, no guard
    meta = fb.edit(tmp_path, rid, V1.replace("Supported", "Led"))
    assert meta["versions"][-1]["n"] == 3 and meta["versions"][-1]["author"] == "user"
    assert "Supported" in resumes.version(tmp_path, rid, 2)["text"]  # v2 unchanged


def test_review_state_and_bad_items(tmp_path: Path, rid: str):
    fb.set_review(tmp_path, rid, "failed")
    assert fb.load(tmp_path, rid)["review"]["state"] == "failed"
    with pytest.raises(ValueError):
        fb.save_review(tmp_path, rid, [{"section": "x"}])
