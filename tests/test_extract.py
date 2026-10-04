"""careeros.extract: pdf/docx/txt text extraction + deterministic ATS view (REQ-098, DEC-001, E2E-003-01)."""
import zipfile
from pathlib import Path

import pytest
from test_qa_pdf_fidelity import make_pdf

from careeros.extract import ats_view, extract_text

RESUME = """Alex Example
alex@example.com | 555-010-0199 | https://github.com/alex-example
EXPERIENCE
Software Engineer, Acme | Jun 2024 - Present
Built a Python service
Intern, Example Labs | 2022 - 2023
EDUCATION
State University | 2018 - 2022
SKILLS
Python, SQL, Docker; AWS
"""

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(path: Path, lines: list[str], table: bool = False, cols: int = 1, image: bool = False) -> Path:
    body = "".join(f'<w:p><w:r><w:t>{t}</w:t></w:r></w:p>' for t in lines)
    if table:
        body += '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    body += f'<w:sectPr><w:cols w:num="{cols}"/></w:sectPr>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')
        if image:
            z.writestr("word/media/image1.png", b"png")
    return path


@pytest.mark.unit
def test_txt_fields(tmp_path):
    (tmp_path / "r.txt").write_text(RESUME)
    v = ats_view(tmp_path / "r.txt")
    f = v["fields"]
    assert f["contact"] == {"email": "alex@example.com", "phone": "555-010-0199",
                            "links": ["https://github.com/alex-example"]}
    assert f["sections"] == ["EXPERIENCE", "EDUCATION", "SKILLS"]
    assert {"line": "Software Engineer, Acme", "dates": "Jun 2024 - Present"} in f["roles"]
    assert {"line": "Intern, Example Labs", "dates": "2022 - 2023"} in f["roles"]
    assert f["skills"] == ["Python", "SQL", "Docker", "AWS"]
    assert v["warnings"] == []
    assert v["text"] == RESUME.strip()


@pytest.mark.unit
def test_warnings_missing_contact_and_bad_dates(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("Alex\nEXPERIENCE\nEngineer, Acme | 03/21 - '23\n")
    w = ats_view(p)["warnings"]
    assert "missing contact (no email or phone)" in w
    assert any(x.startswith("unreadable dates") for x in w)


@pytest.mark.unit
def test_docx_text_and_layout_warnings(tmp_path):
    p = make_docx(tmp_path / "r.docx", RESUME.strip().splitlines(), table=True, cols=2, image=True)
    assert extract_text(p).splitlines()[0] == "Alex Example"
    w = ats_view(p)["warnings"]
    assert "images (ATS cannot read them)" in w
    assert "tables" in w
    assert "multi-column layout" in w


@pytest.mark.unit
def test_pdf_same_input_same_output(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", RESUME.strip(), embedded=False)
    b = make_pdf(tmp_path / "b.pdf", RESUME.strip(), embedded=False)
    va, vb = ats_view(a), ats_view(b)
    assert va == vb
    assert va["fields"]["contact"]["email"] == "alex@example.com"
    assert "EXPERIENCE" in va["fields"]["sections"]


@pytest.mark.unit
def test_empty_pdf_no_text(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    w.add_blank_page(width=612, height=792)
    p = tmp_path / "blank.pdf"
    with p.open("wb") as fh:
        w.write(fh)
    v = ats_view(p)
    assert v["text"] == "" and "no text found" in v["warnings"]


@pytest.mark.unit
def test_unsupported_suffix(tmp_path):
    with pytest.raises(ValueError):
        extract_text(tmp_path / "r.rtf")
