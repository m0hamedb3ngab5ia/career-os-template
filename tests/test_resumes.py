"""Résumé store (REQ-093, REQ-099, REQ-100; DEC-006, DEC-008): profile/resumes/<rid>/meta.json + v<n>/."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from careeros import resumes

pytestmark = pytest.mark.unit

PDF = b"%PDF-1.4\nnot really a pdf\n"


def docx(text: str) -> bytes:
    buf = io.BytesIO()
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
                                        "</w:body></w:document>")
    return buf.getvalue()


def test_add_stores_original_text_and_ats(tmp_path: Path):
    m = resumes.add(tmp_path, "My CV.docx", docx("Jane Doe jane@example.com"))
    d = tmp_path / "profile" / "resumes" / m["rid"]
    assert m["rid"].startswith("my-cv-") and len(m["rid"]) == len("my-cv-") + 4
    assert m["name"] == "My CV" and m["type"] == "master"  # first résumé becomes the master
    assert [v["n"] for v in m["versions"]] == [1] and m["versions"][0]["author"] == "user"
    assert m["versions"][0]["source"] == "upload"
    assert (d / "v1" / "original.docx").read_bytes() == docx("Jane Doe jane@example.com")
    assert "jane@example.com" in (d / "v1" / "text.txt").read_text()
    assert json.loads((d / "v1" / "ats.json").read_text())["fields"]["contact"]["email"] == "jane@example.com"
    assert json.loads((d / "meta.json").read_text()) == m


def test_corrupt_pdf_stored_with_no_text_warning(tmp_path: Path):
    m = resumes.add(tmp_path, "cv.pdf", PDF)
    assert "no text found" in resumes.version(tmp_path, m["rid"], 1)["ats"]["warnings"]


@pytest.mark.parametrize("name,data,exc", [
    ("cv.txt", b"hello", resumes.BadType),
    ("cv.pdf", b"PK\x03\x04 zip", resumes.BadType),  # extension and magic bytes must agree
    ("cv.docx", PDF, resumes.BadType),
    ("cv.pdf", b"%PDF" + b"x" * resumes.MAX_BYTES, resumes.TooLarge),
])
def test_bad_upload_stores_nothing(tmp_path: Path, name, data, exc):
    with pytest.raises(exc):
        resumes.add(tmp_path, name, data)
    assert resumes.list_resumes(tmp_path) == []


def test_one_master_and_types(tmp_path: Path):
    a = resumes.add(tmp_path, "a.pdf", PDF)["rid"]
    b = resumes.add(tmp_path, "b.pdf", PDF, name="Backend")["rid"]
    assert resumes.get(tmp_path, b)["type"] == "variant"
    resumes.update(tmp_path, b, type="master")
    assert resumes.get(tmp_path, a)["type"] == "variant" and resumes.get(tmp_path, b)["type"] == "master"
    with pytest.raises(resumes.Refused):
        resumes.update(tmp_path, b, type="other")  # mark another résumé master instead
    with pytest.raises(ValueError):
        resumes.update(tmp_path, a, type="boss")
    resumes.update(tmp_path, a, type="other", name="Old")
    rows = resumes.list_resumes(tmp_path)
    assert {(r["name"], r["type"], r["latest"]) for r in rows} == {("Old", "other", 1), ("Backend", "master", 1)}


def test_delete_rules(tmp_path: Path):
    a = resumes.add(tmp_path, "a.pdf", PDF)["rid"]
    for _ in range(2):
        resumes.add_version(tmp_path, a, "a.pdf", PDF, author="user", source="edit")
    assert [v["n"] for v in resumes.get(tmp_path, a)["versions"]] == [1, 2, 3]
    resumes.delete_version(tmp_path, a, 1)
    assert [v["n"] for v in resumes.get(tmp_path, a)["versions"]] == [2, 3]
    assert not (tmp_path / "profile" / "resumes" / a / "v1").exists()
    with pytest.raises(resumes.Refused, match="latest"):
        resumes.delete_version(tmp_path, a, 3)
    with pytest.raises(resumes.Refused, match="master"):
        resumes.delete(tmp_path, a)
    b = resumes.add(tmp_path, "b.pdf", PDF)["rid"]
    resumes.delete(tmp_path, b)
    assert [r["rid"] for r in resumes.list_resumes(tmp_path)] == [a]
    with pytest.raises(LookupError):
        resumes.get(tmp_path, b)


@pytest.mark.parametrize("rid", ["../x", "a/b", "..", ""])
def test_rid_cannot_escape(tmp_path: Path, rid: str):
    with pytest.raises(LookupError):
        resumes.get(tmp_path, rid)


def test_blank_name_with_master_retype_changes_nothing(tmp_path: Path):
    a = resumes.add(tmp_path, "a.pdf", PDF)["rid"]
    b = resumes.add(tmp_path, "b.pdf", PDF)["rid"]
    with pytest.raises(ValueError):
        resumes.update(tmp_path, b, type="master", name="  ")
    assert resumes.get(tmp_path, a)["type"] == "master" and resumes.get(tmp_path, b)["type"] == "variant"


def test_concurrent_adds_make_one_master(tmp_path: Path, monkeypatch):
    import threading
    import time

    real = resumes._store
    monkeypatch.setattr(resumes, "_store", lambda *a: (time.sleep(0.2), real(*a)))
    ts = [threading.Thread(target=resumes.add, args=(tmp_path, f"{i}.pdf", PDF)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(r["type"] for r in resumes.list_resumes(tmp_path)) == ["master", "variant"]


@pytest.mark.unit
def test_version_labels_and_download_names(tmp_path: Path):  # 01_X_Original, 02_X_FeedbackApplied, never overwritten
    m = resumes.add(tmp_path, "cv.pdf", b"%PDF-1.4\n", name="Master Resume")
    resumes.add_text(tmp_path, m["rid"], "Jane\nExperience\n", author="ai", source="f1")
    meta = resumes.add_text(tmp_path, m["rid"], "Jane\nExperience 2\n", author="user", source="edit")
    assert [v["label"] for v in meta["versions"]] == ["Original", "Feedback applied", "Edited"]
    names = [resumes.download_name(tmp_path, m["rid"], n)[1] for n in (1, 2, 3)]
    assert names == ["01_MasterResume_Original.pdf", "02_MasterResume_FeedbackApplied.txt", "03_MasterResume_Edited.txt"]
    assert (resumes._dir(tmp_path, m["rid"]) / "v1" / "original.pdf").exists()  # the original stays


@pytest.mark.unit
def test_old_meta_without_labels_gets_defaults(tmp_path: Path):
    m = resumes.add(tmp_path, "cv.pdf", b"%PDF-1.4\n")
    d = resumes._dir(tmp_path, m["rid"])
    raw = json.loads((d / "meta.json").read_text())
    for v in raw["versions"]:
        v.pop("label", None)
    (d / "meta.json").write_text(json.dumps(raw))
    assert resumes.get(tmp_path, m["rid"])["versions"][0]["label"] == "Original"


# --- DEC-018: resume.json schema v1, migrated on read (TASK-027) ------------------------------------------

OLD_RESUME = {
    "identity": {"name": "Alex Example"},
    "sections": [{"type": "experience", "order": 1}, {"type": "projects", "order": 2},
                 {"type": "education", "order": 3}, {"type": "skills", "order": 4}],
    "experience": [{"id": "acme", "company": "Acme", "bullets": [{"id": "acme.1", "text": "a"},
                                                                {"id": "acme.2", "text": "b"}]}],
    "projects": [{"id": "widgetizer", "name": "W", "bullets": [{"id": "widgetizer.1", "text": "c"}]}],
    "education": [{"id": "state_u", "school": "S"}],
    "skills": {"programming": ["Python"]},
}


def test_migrate_old_file_to_v1_moves_master_ids_to_source():
    v1 = resumes.migrate(OLD_RESUME)
    assert v1["schema_version"] == resumes.SCHEMA_VERSION == 1
    exp = v1["experience"][0]
    assert exp["source"] == "acme" and exp["id"] == "experience-1"
    assert [(b["id"], b["source"]) for b in exp["bullets"]] == [("experience-1.b1", "acme.1"), ("experience-1.b2", "acme.2")]
    assert v1["projects"][0]["bullets"][0] == {"id": "projects-1.b1", "source": "widgetizer.1", "text": "c"}
    assert v1["education"][0]["source"] == "state_u" and v1["education"][0]["id"] == "education-1"
    assert [s["id"] for s in v1["sections"]] == ["sec-experience", "sec-projects", "sec-education", "sec-skills"]
    assert OLD_RESUME["experience"][0]["id"] == "acme"  # input not mutated


def test_migrate_ids_stable_across_reads(tmp_path: Path):
    p = tmp_path / "resume.json"
    p.write_text(json.dumps(OLD_RESUME))
    first = resumes.read_resume_json(p)
    assert first == resumes.read_resume_json(p) == resumes.migrate(first)  # v1 is a fixed point
    assert json.loads(p.read_text()) == OLD_RESUME  # migration is in memory only


def test_migrate_v1_keeps_ids_and_fills_missing_without_collision():
    doc = {"schema_version": 1, "experience": [
        {"id": "x", "bullets": [{"id": "experience-1.b2", "text": "kept"}, {"text": "hand-written"}]}]}
    v1 = resumes.migrate(doc)
    e = v1["experience"][0]
    assert e["id"] == "x" and "source" not in e
    ids = [b["id"] for b in e["bullets"]]
    assert ids[0] == "experience-1.b2" and ids[1] != ids[0] and "source" not in e["bullets"][1]
    assert resumes.migrate(v1) == v1


def test_migrate_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match="schema_version"):
        resumes.migrate({"schema_version": 99})
