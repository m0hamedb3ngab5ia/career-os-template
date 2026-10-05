"""Profile page writers (REQ-107, REQ-101): saved answers edit/delete, lesson delete, writing samples."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from careeros import learning, voice

pytestmark = pytest.mark.unit

ANSWERS = """\
answers:
  - key: work_authorization
    match: ["authorized to work"]
    answer: "Yes"                    # INSERT: keep me
  - key: relocate
    match: ["relocation"]
    answer: "No"
company_answers:
  Acme:
    - key: why_us
      match: ["why acme"]
      answer: "Rockets."
eeo:
  gender:
    answer: "Decline"
"""


@pytest.fixture
def s(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(ANSWERS)
    (tmp_path / "l.yaml").write_text("lessons:\n  - id: abc12345\n    text: \"Workday needs a login\"\n")
    return SimpleNamespace(root=tmp_path, paths={"standard_answers": str(tmp_path / "a.yaml"),
                                                 "apply_lessons": str(tmp_path / "l.yaml")})


def test_list_answers_covers_general_company_and_eeo(s):
    rows = learning.list_answers(s)
    assert [(r["scope"], r["key"], r["company"]) for r in rows] == [
        ("general", "work_authorization", None), ("general", "relocate", None), ("company", "why_us", "Acme"),
        ("eeo", "gender", None)]
    assert rows[0]["answer"] == "Yes" and rows[0]["match"] == ["authorized to work"]


def test_edit_answer_keeps_comments_and_other_entries(s):
    learning.edit_answer(s, key="work_authorization", answer="No")
    learning.edit_answer(s, key="why_us", answer="Space.", company="acme")
    learning.edit_answer(s, key="gender", answer="Female", eeo=True)
    text = Path(s.paths["standard_answers"]).read_text()
    assert "# INSERT: keep me" in text
    d = yaml.safe_load(text)
    assert d["answers"][0]["answer"] == "No" and d["answers"][1]["answer"] == "No"
    assert d["company_answers"]["Acme"][0]["answer"] == "Space." and d["eeo"]["gender"]["answer"] == "Female"
    with pytest.raises(ValueError):
        learning.edit_answer(s, key="relocate", answer="  ")
    with pytest.raises(KeyError):
        learning.edit_answer(s, key="nope", answer="x")


def test_delete_answer_removes_only_that_entry(s):
    learning.delete_answer(s, key="relocate")
    learning.delete_answer(s, key="gender", eeo=True)
    learning.delete_answer(s, key="why_us", company="Acme")
    d = yaml.safe_load(Path(s.paths["standard_answers"]).read_text())
    assert [e["key"] for e in d["answers"]] == ["work_authorization"]
    assert "gender" not in d["eeo"] and d["company_answers"]["Acme"] == []
    with pytest.raises(KeyError):
        learning.delete_answer(s, key="relocate")


def test_delete_lesson(s):
    learning.delete_lesson(s, "abc12345")
    assert learning.load_lessons(s) == []
    with pytest.raises(KeyError):
        learning.delete_lesson(s, "abc12345")


GUIDE = "# Voice\n\n## Samples\n\nPut files here.\n\n## Learned\n\n- short sentences\n- opens with a question\n"


def test_samples_add_list_remove_and_learned(tmp_path: Path):
    (tmp_path / "profile" / "voice").mkdir(parents=True)
    (tmp_path / "profile" / "voice" / "style_guide.md").write_text(GUIDE)
    assert voice.list_samples(tmp_path) == []
    voice.add_sample(tmp_path, "letter.md", b"Dear team")
    voice.add_sample(tmp_path, "essay.txt", b"Hello")
    assert [x["name"] for x in voice.list_samples(tmp_path)] == ["essay.txt", "letter.md"]
    for bad in ("../x.md", ".hidden.md", "a/b.md", ""):
        with pytest.raises(ValueError):
            voice.add_sample(tmp_path, bad, b"x")
    with pytest.raises(voice.Unsupported):
        voice.add_sample(tmp_path, "x.exe", b"x")
    assert voice.learned(tmp_path) == "- short sentences\n- opens with a question"
    voice.remove_sample(tmp_path, "essay.txt")
    with pytest.raises(KeyError):
        voice.remove_sample(tmp_path, "essay.txt")
    voice.clear_learned(tmp_path)
    assert voice.learned(tmp_path) == ""
    assert "## Samples\n\nPut files here." in (tmp_path / "profile" / "voice" / "style_guide.md").read_text()
