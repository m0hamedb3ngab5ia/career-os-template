"""Publish (TASK-031, DEC-017/020): one version per Next/Done, JSON only, outputs rendered on demand."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from careeros import annotations as ann
from careeros import resumes

DOC = {"schema_version": 1, "identity": {"name": "Pat Doe"}, "summary": "Engineer.",
       "experience": [{"id": "e1", "company": "Acme", "title": "Dev", "bullets": [
           {"id": "b1", "source": "m1", "text": "Built the thing"},
           {"id": "b2", "source": "m2", "text": "Shipped the other thing"}]}]}


def _rid(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    src = tmp_path / "resume.json"
    src.write_text(json.dumps(DOC), encoding="utf-8")
    return root, resumes.add_tailored(root, "text", category="x", source="job-1", files={"resume.json": src})["rid"]


def _edit(root: Path, rid: str, text: str = "Built the better thing") -> dict:
    d = resumes.get_draft(root, rid)
    doc = copy.deepcopy(d["resume"])
    doc["experience"][0]["bullets"][0]["text"] = text
    return resumes.put_draft(root, rid, doc, rev=d["rev"], author="user")


def test_publish_writes_json_only_version_and_moves_log(tmp_path: Path):
    root, rid = _rid(tmp_path)
    _edit(root, rid)
    out = resumes.publish(root, rid, key="k1")
    assert out["published"] is True and out["n"] == 2
    meta = resumes.get(root, rid)
    assert [v["n"] for v in meta["versions"]] == [1, 2] and meta["versions"][-1]["source"] == "publish"
    v2 = resumes._dir(root, rid) / "v2"
    assert sorted(p.name for p in v2.iterdir()) == ["changes.jsonl", "resume.json"]  # DEC-020: no text/ATS/.tex/PDF
    assert resumes.read_resume_json(v2 / "resume.json")["experience"][0]["bullets"][0]["text"] == "Built the better thing"
    assert [c["target_id"] for c in resumes._read_log(v2 / "changes.jsonl")] == ["b1"]
    assert not (resumes._dir(root, rid) / "draft.changes.jsonl").exists() and resumes.changes(root, rid) == []
    d = resumes.get_draft(root, rid)
    assert d["draft"] is False and d["rev"] > 1  # draft restarts from v2, rev stays monotonic
    assert "Built the better thing" in resumes.user_texts(root, rid)  # provenance survives the move
    assert not list(resumes._dir(root, rid).glob(".v*"))


def test_unchanged_hash_is_noop_and_key_is_idempotent(tmp_path: Path):
    root, rid = _rid(tmp_path)
    assert resumes.publish(root, rid, key="k0")["published"] is False  # no draft at all
    _edit(root, rid)
    _edit(root, rid, "Built the thing")  # edited back: same hash as latest
    assert resumes.publish(root, rid, key="k1")["published"] is False
    assert len(resumes.get(root, rid)["versions"]) == 1
    _edit(root, rid)
    assert resumes.publish(root, rid, key="k2")["published"] is True
    _edit(root, rid, "Another edit")
    again = resumes.publish(root, rid, key="k2")  # double click / retry with the same key
    assert again["published"] is False and again["n"] == 2
    assert len(resumes.get(root, rid)["versions"]) == 2


def test_version_text_rendered_on_demand_and_deterministic(tmp_path: Path):
    root, rid = _rid(tmp_path)
    _edit(root, rid)
    resumes.publish(root, rid, key="k1")
    v = resumes.version(root, rid, 2)  # match / review read through this
    assert "Built the better thing" in v["text"] and v["ats"]["text"] == v["text"]
    assert resumes.rendered(root, rid, 2, "txt") == resumes.rendered(root, rid, 2, "txt")
    tex = resumes.rendered(root, rid, 2, "tex")
    assert "Built the better thing" in tex and tex == resumes.rendered(root, rid, 2, "tex")
    assert sorted(p.name for p in (resumes._dir(root, rid) / "v2").iterdir()) == ["changes.jsonl", "resume.json"]


def test_pdf_cached_for_latest_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, rid = _rid(tmp_path)
    _edit(root, rid)
    resumes.publish(root, rid, key="k1")
    mod = resumes._renderer()
    calls = []

    def fake_compile(tex: Path) -> Path:
        calls.append(tex)
        pdf = tex.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF-fake " + tex.read_bytes()[:20])
        return pdf

    monkeypatch.setattr(mod, "compile_tex", fake_compile)
    pdf = resumes.render_pdf(root, rid, 2)
    assert pdf and pdf.read_bytes().startswith(b"%PDF")
    h = resumes._hash(resumes.read_resume_json(resumes._dir(root, rid) / "v2" / "resume.json"))
    assert pdf.parent == resumes._dir(root, rid) / "cache" and pdf.name == f"{h}-{resumes.renderer_version()}.pdf"
    assert resumes.render_pdf(root, rid, 2) == pdf and len(calls) == 1  # cache hit
    _edit(root, rid, "Third")
    resumes.publish(root, rid, key="k2")
    new = resumes.render_pdf(root, rid, 3)
    assert [p.name for p in (resumes._dir(root, rid) / "cache").iterdir()] == [new.name]  # latest only
    with pytest.raises(LookupError):
        resumes.render_pdf(root, rid, 2)  # older versions: no cached PDF (DEC-020)


def test_annotations_carried_or_outdated(tmp_path: Path):
    root, rid = _rid(tmp_path)
    keep = ann.create(root, rid, kind="comment", target_id="b2", text="tighten")
    gone = ann.create(root, rid, kind="comment", target_id="b1", text="numbers?")
    d = resumes.get_draft(root, rid)
    doc = copy.deepcopy(d["resume"])
    doc["experience"][0]["bullets"].pop(0)
    resumes.put_draft(root, rid, doc, rev=d["rev"], author="user")
    resumes.publish(root, rid, key="k1")
    st = {i["id"]: i["status"] for i in ann.list_items(root, rid)}
    assert st == {keep["id"]: "open", gone["id"]: "outdated"}


def test_crash_between_steps_recovers_on_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, rid = _rid(tmp_path)
    _edit(root, rid)
    d = resumes._dir(root, rid)
    (d / ".v2.tmp").mkdir()  # an older crash before the rename: discarded
    (d / ".v2.tmp" / "resume.json").write_text("{}", encoding="utf-8")
    real = resumes._write

    def boom(dd: Path, meta: dict) -> None:
        raise OSError("crash before meta.json")

    monkeypatch.setattr(resumes, "_write", boom)
    with pytest.raises(OSError):
        resumes.publish(root, rid, key="k1")
    monkeypatch.setattr(resumes, "_write", real)
    assert len(resumes.get(root, rid)["versions"]) == 1  # not published yet: meta.json is the commit point
    assert "Built the better thing" in resumes.user_texts(root, rid)  # no lost edits or provenance meanwhile
    out = resumes.publish(root, rid, key="k1")
    assert out["n"] == 2 and len(resumes.get(root, rid)["versions"]) == 2
    assert [c["target_id"] for c in resumes._read_log(d / "v2" / "changes.jsonl")] == ["b1"]
    assert not (d / ".v2.tmp").exists() and resumes.get_draft(root, rid)["draft"] is False
