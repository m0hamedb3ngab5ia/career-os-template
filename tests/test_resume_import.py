"""Import run + verbatim guard (TASK-032, DEC-019, DEC-018 amendment): extract-master's resume.json becomes v2
only if every bullet and field is in v1 text.txt; else import.json failed, v1 kept, Retry."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from careeros import resume_import as imp
from careeros import resumes

TEXT = ("Pat Doe\nEXPERIENCE\nAcme — Dev   2020 – 2023\n• Built the   thing\nfor customers\n"
        "• Shipped the other thing\nHobbies: chess\n")
DOC = {"schema_version": 1, "identity": {"name": "Pat Doe"},
       "experience": [{"id": "e1", "company": "Acme", "title": "Dev", "dates": "2020 – 2023", "bullets": [
           {"id": "b1", "text": "Built the thing for customers"},
           {"id": "b2", "text": "Shipped the other thing", "origin": "user"}]}]}


def _v1(tmp_path: Path, text: str = TEXT) -> tuple[Path, str]:
    """An uploaded v1 with its import run running (only then may save() publish, review MUST)."""
    root = tmp_path / "repo"
    rid = resumes.add(root, "cv.pdf", b"%PDF-1.4\nnot really a pdf\n")["rid"]
    (resumes._dir(root, rid) / "v1" / "text.txt").write_text(text, encoding="utf-8")
    imp.set_state(root, rid, "running", run="r0")
    return root, rid


def test_guard_pass_publishes_v2_with_user_origin_and_not_carried_list(tmp_path: Path):  # E2E-001-04 part 1
    root, rid = _v1(tmp_path)
    out = imp.save(root, rid, copy.deepcopy(DOC))
    assert out["state"] == "done" and out["n"] == 2
    meta = resumes.get(root, rid)
    assert [(v["n"], v["source"]) for v in meta["versions"]] == [(1, "upload"), (2, "import")]
    v2 = resumes.read_resume_json(resumes._dir(root, rid) / "v2" / "resume.json")
    assert {b["origin"] for b in v2["experience"][0]["bullets"]} == {"user"}  # the guard is what sets origin
    assert resumes.user_texts(root, rid) == {"Built the thing for customers", "Shipped the other thing"}
    assert [d["text"] for d in imp.load(root, rid)["dropped"]] == ["Hobbies: chess"]
    assert (resumes._dir(root, rid) / "v1" / "text.txt").read_text(encoding="utf-8").startswith("Pat Doe")


def test_guard_fails_on_date_absent_from_v1(tmp_path: Path):  # E2E-001-03
    root, rid = _v1(tmp_path)
    doc = copy.deepcopy(DOC)
    doc["experience"][0]["dates"] = "2019 – 2023"
    with pytest.raises(imp.ImportRefused, match="2019"):
        imp.save(root, rid, doc)
    st = imp.load(root, rid)
    assert st["state"] == "running" and "2019" in st["reason"]  # run_import fails it if no retry lands
    assert [v["n"] for v in resumes.get(root, rid)["versions"]] == [1]  # v1 kept, no guessed v2


def test_guard_fails_on_reworded_bullet_and_bad_json(tmp_path: Path):
    root, rid = _v1(tmp_path)
    doc = copy.deepcopy(DOC)
    doc["experience"][0]["bullets"][0]["text"] = "Built the thing for 40 customers"
    with pytest.raises(imp.ImportRefused, match="not in the uploaded text"):
        imp.save(root, rid, doc)
    imp.set_state(root, rid, "running")
    with pytest.raises(imp.ImportRefused, match="schema_version"):
        imp.save(root, rid, {**DOC, "schema_version": 9})
    assert "schema_version" in imp.load(root, rid)["reason"]


def test_restore_adds_dropped_line_to_draft_once(tmp_path: Path):  # E2E-001-04 part 2
    root, rid = _v1(tmp_path)
    imp.save(root, rid, copy.deepcopy(DOC))
    did = imp.load(root, rid)["dropped"][0]["id"]
    d = imp.restore(root, rid, did)
    b = d["resume"]["experience"][0]["bullets"][-1]
    assert b["text"] == "Hobbies: chess" and b["origin"] == "user" and d["draft"] is True
    assert resumes.changes(root, rid)[-1]["author"] == "user"
    assert imp.load(root, rid)["dropped"][0]["restored"] is True
    with pytest.raises(resumes.Refused):
        imp.restore(root, rid, did)


def test_run_import_failed_run_marks_failed_and_adds_action(tmp_path: Path, monkeypatch):
    from careeros.ui.services import step

    root, rid = _v1(tmp_path)
    added = []
    monkeypatch.setattr("careeros.tracker.add_action", lambda s, what, type, **kw: added.append((what, type)))
    settings = type("S", (), {"root": root})()
    step.run_import(settings, rid, run_skill=lambda *a, **kw: {"id": "r1", "stop_reason": "error"})
    assert imp.load(root, rid)["state"] == "failed" and len(added) == 1 and added[0][1] == "profile_gap"

    def ok(s, kind, prompt, **kw):
        assert kind == "extract_master" and prompt == f"extract-master {rid}"
        imp.save(root, rid, copy.deepcopy(DOC))
        return {"id": "r2", "stop_reason": "completed"}
    added.clear()
    step.run_import(settings, rid, run_skill=ok)  # Retry
    assert imp.load(root, rid)["state"] == "done" and added == []
    assert json.loads((resumes._dir(root, rid) / "import.json").read_text(encoding="utf-8"))["run"] == "r2"


def test_save_refuses_ai_resume_and_outside_a_running_import(tmp_path: Path):  # review MUST
    root = tmp_path / "repo"
    rid = resumes.add_tailored(root, TEXT, category="x", source="up")["rid"]
    imp.set_state(root, rid, "running", run="r1")
    with pytest.raises(imp.ImportRefused, match="upload"):
        imp.save(root, rid, copy.deepcopy(DOC))
    root, rid = _v1(tmp_path / "b")
    imp.set_state(root, rid, "done")
    with pytest.raises(imp.ImportRefused, match="running"):
        imp.save(root, rid, copy.deepcopy(DOC))
    assert [v["n"] for v in resumes.get(root, rid)["versions"]] == [1]
    assert imp.load(root, rid)["state"] == "done"  # an out-of-run save leaves import.json alone


@pytest.mark.parametrize("v1,bullet", [("• Led team of 50\n", "Led team of 5"),
                                       ("• Did not miss deadlines\n", "miss deadlines"),
                                       ("• Built X\nSkills\n• Go\n", "Built X Skills")])
def test_guard_bullet_is_whole_v1_lines(tmp_path: Path, v1: str, bullet: str):  # review SHOULD
    root, rid = _v1(tmp_path, "Acme\n" + v1)
    with pytest.raises(imp.ImportRefused, match="not in the uploaded text"):
        imp.save(root, rid, {"schema_version": 1, "experience": [{"company": "Acme", "bullets": [{"text": bullet}]}]})


def test_guard_field_within_one_line_case_insensitive(tmp_path: Path):
    root, rid = _v1(tmp_path)
    with pytest.raises(imp.ImportRefused, match="not in the uploaded text"):
        imp.save(root, rid, {"schema_version": 1, "experience": [{"company": "Doe EXPERIENCE"}]})
    imp.set_state(root, rid, "running")
    doc = copy.deepcopy(DOC)
    doc["experience"][0]["bullets"][0]["text"] = "built THE thing for customers"
    assert imp.save(root, rid, doc)["state"] == "done"


def test_leaves_keep_numbers_and_non_structural_keys():
    out = imp._leaves({"source": "x", "experience": [{"id": "e1", "dates": 2019, "bullets": [{"id": "b", "text": "t"}]}]})
    assert ("source", "x") in out and ("experience[0].dates", "2019") in out and all(s not in ("e1", "b") for _, s in out)


def test_dropped_skips_headers_and_compares_whole_lines():
    doc = {"experience": [{"company": "Acme", "title": "Dev", "bullets": [{"text": "Built the thing"}]}]}
    text = "Work Experience\nAcme — Dev\n• Built the thing\n• Built the thing twice\n"
    assert [d["text"] for d in imp._dropped(doc, text)] == ["Built the thing twice"]


def test_restore_after_crash_before_import_json_does_not_double_add(tmp_path: Path, monkeypatch):
    from careeros.runs import atomic

    root, rid = _v1(tmp_path)
    imp.save(root, rid, copy.deepcopy(DOC))
    real = atomic.write_json

    def crash(path, *a, **kw):
        if Path(path).name == "import.json":
            raise OSError("crash")
        return real(path, *a, **kw)
    monkeypatch.setattr(atomic, "write_json", crash)
    with pytest.raises(OSError):
        imp.restore(root, rid, "d1")
    monkeypatch.setattr(atomic, "write_json", real)
    d = imp.restore(root, rid, "d1")
    assert [b["text"] for b in d["resume"]["experience"][0]["bullets"]].count("Hobbies: chess") == 1


def test_publish_refuses_a_draft_changed_since_rev(tmp_path: Path):  # review NIT: import publishes only its commit
    root, rid = _v1(tmp_path)
    imp.save(root, rid, copy.deepcopy(DOC))
    rev = imp.restore(root, rid, "d1")["rev"]
    with pytest.raises(resumes.Refused):
        resumes.publish(root, rid, key="k1", rev=rev - 1)
    assert resumes.publish(root, rid, key="k2", rev=rev)["n"] == 3


def test_run_import_loser_leaves_winner_and_dead_run_reads_failed(tmp_path: Path, monkeypatch):  # review SHOULD
    from careeros.ui.services import step

    root, rid = _v1(tmp_path)
    added = []
    monkeypatch.setattr("careeros.tracker.add_action", lambda *a, **kw: added.append(a))
    settings = type("S", (), {"root": root})()

    def busy(s, kind, prompt, run_id=None):
        imp.set_state(root, rid, "running", run="winner")  # the other fast Retry took over import.json
        return {"id": run_id, "stop_reason": "busy"}
    step.run_import(settings, rid, run_skill=busy, run_id="loser")
    assert imp.load(root, rid)["state"] == "running" and imp.load(root, rid)["run"] == "winner" and added == []
    imp.set_state(root, rid, "running", run="dead", pid=2 ** 22 + 4321)  # its step process crashed
    assert imp.load(root, rid)["state"] == "failed"



def test_guard_field_wrapped_across_v1_lines_passes(tmp_path: Path):  # review-2 MUST
    root, rid = _v1(tmp_path, "Pat Doe\nSummary\nSenior engineer with ten years\nbuilding payment systems.\n")
    doc = {"schema_version": 1, "identity": {"name": "Pat Doe"},
           "summary": "Senior engineer with ten years building payment systems."}
    assert imp.save(root, rid, doc)["state"] == "done"
    root, rid = _v1(tmp_path / "b", "Pat Doe\nSummary\nSenior engineer with ten years\nbuilding payment systems.\n")
    with pytest.raises(imp.ImportRefused, match="not in the uploaded text"):  # whole words still required
        imp.save(root, rid, {"schema_version": 1, "summary": "engineer with ten years build"})


@pytest.mark.parametrize("glyph", ["•", "▪", "◦", "●", "➢"])
def test_guard_bullet_never_spans_a_new_bullet_glyph(tmp_path: Path, glyph: str):  # review-2 SHOULD-1
    root, rid = _v1(tmp_path, f"Acme\n{glyph} Built the API\n{glyph} Cut costs 20%\n")
    with pytest.raises(imp.ImportRefused, match="not in the uploaded text"):
        imp.save(root, rid, {"schema_version": 1, "experience": [{"company": "Acme", "bullets": [
            {"text": "Built the API Cut costs 20%"}]}]})


def test_guard_refusal_keeps_run_open_for_one_retry(tmp_path: Path):  # review-2 SHOULD-2 (SKILL.md retry)
    root, rid = _v1(tmp_path)
    doc = copy.deepcopy(DOC)
    doc["experience"][0]["dates"] = "2019 – 2023"
    with pytest.raises(imp.ImportRefused):
        imp.save(root, rid, doc)
    st = imp.load(root, rid)
    assert st["state"] == "running" and st["run"] == "r0" and "2019" in st["reason"]
    assert imp.save(root, rid, copy.deepcopy(DOC))["state"] == "done"


def test_guard_bullet_wrapped_onto_header_words_passes(tmp_path: Path):  # review-2 NIT
    root, rid = _v1(tmp_path, "Acme\nSkills\n• Ran workshops on tooling\nand skills\n")
    assert imp.save(root, rid, {"schema_version": 1, "experience": [{"company": "Acme", "bullets": [
        {"text": "Ran workshops on tooling and skills"}]}]})["state"] == "done"
