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


def test_add_sample_keeps_same_name_and_skill_types_only(tmp_path: Path):
    """MUST4: a same-name upload never overwrites (name-2.ext); MUST2: only what learn-voice reads."""
    assert voice.add_sample(tmp_path, "letter.md", b"one")["name"] == "letter.md"
    assert voice.add_sample(tmp_path, "letter.md", b"two")["name"] == "letter-2.md"
    assert voice.add_sample(tmp_path, "letter.md", b"three")["name"] == "letter-3.md"
    d = voice.samples_dir(tmp_path)
    assert (d / "letter.md").read_bytes() == b"one" and (d / "letter-3.md").read_bytes() == b"three"
    assert voice.add_sample(tmp_path, "mail.eml", b"x")["name"] == "mail.eml"
    assert not [p for p in d.iterdir() if p.name.startswith(".")]  # no temp files left behind
    for bad in ("cv.doc", "cv.rtf"):
        with pytest.raises(voice.Unsupported):
            voice.add_sample(tmp_path, bad, b"x")


FIXTURE_DOCX = Path(__file__).resolve().parent / "fixtures" / "voice_sample.docx"


def test_docx_sample_stored_as_plain_text_and_pdf_as_is(tmp_path: Path):
    """TASK-021: .docx becomes .txt (stdlib, paragraphs on their own lines); .pdf is kept for learn-voice to Read."""
    assert voice.docx_text(FIXTURE_DOCX.read_bytes()) == "Dear hiring team,\nI build small tools\tthat last.\n\nBest regards"
    assert voice.add_sample(tmp_path, "letter.docx", FIXTURE_DOCX.read_bytes())["name"] == "letter.txt"
    assert voice.add_sample(tmp_path, "letter.docx", FIXTURE_DOCX.read_bytes())["name"] == "letter-2.txt"
    d = voice.samples_dir(tmp_path)
    assert (d / "letter.txt").read_text(encoding="utf-8").startswith("Dear hiring team,")
    assert not list(d.glob("*.docx"))
    assert voice.add_sample(tmp_path, "cv.pdf", b"%PDF-1.4 x")["name"] == "cv.pdf"
    assert (d / "cv.pdf").read_bytes() == b"%PDF-1.4 x"
    with pytest.raises(ValueError, match="not a valid .docx"):
        voice.add_sample(tmp_path, "broken.docx", b"not a zip")


def test_step_skills_get_minimal_tools():
    """SHOULD5: run_skill passes its kind, so learn_voice / extract_master get only what their skills need."""
    from careeros.runs.config import RunsConfig, allowed_tools_for

    cfg = RunsConfig()
    lv = allowed_tools_for(cfg, "learn_voice")
    assert lv == ["Read", "Glob", "Grep", "Edit(profile/voice/**)"]
    em = allowed_tools_for(cfg, "extract_master")
    assert "Bash(.venv/bin/careeros *)" in em and "Edit" not in em and "Bash(.venv/bin/python *)" not in em
    assert "Bash(.venv/bin/python *)" in allowed_tools_for(cfg, "inbox_sync")


def test_run_skill_passes_kind_to_build_command(tmp_path: Path):
    from conftest import make_temp_root

    from careeros.config import Settings
    from careeros.runs import service

    cmds: list = []

    def inv(cmd, *_a):
        cmds.append(cmd)
        raise RuntimeError("stop here")
    try:
        service.run_skill(Settings.load(make_temp_root(tmp_path / "repo")), "learn_voice", "learn-voice", invoke=inv,
                          doctor=lambda r: [])
    except RuntimeError:
        pass
    assert cmds[0][cmds[0].index("--allowedTools") + 1] == "Read,Glob,Grep,Edit(profile/voice/**)"


def test_learn_voice_skill_reads_uploaded_types():
    """TASK-021: learn-voice reads every type the upload stores (docx arrives as .txt, pdf via Read)."""
    skill = (Path(__file__).resolve().parents[1] / ".claude" / "skills" / "learn-voice" / "SKILL.md").read_text()
    assert all(e in skill for e in (".md", ".txt", ".eml", ".pdf"))
