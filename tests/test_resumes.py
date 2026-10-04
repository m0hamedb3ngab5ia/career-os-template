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
