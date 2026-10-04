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


def make_layout_pdf(path: Path, rows: list[list[tuple[int, str]]]) -> Path:
    """One page; each row is [(x, text), ...] drawn on the same baseline."""
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    w = pypdf.PdfWriter()
    page = w.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(font)})})
    ops = [f"BT /F1 9 Tf 1 0 0 1 {x} {760 - 14 * i} Tm ({t}) Tj ET" for i, row in enumerate(rows) for x, t in row]
    cs = DecodedStreamObject()
    cs.set_data("\n".join(ops).encode("latin-1"))
    page[NameObject("/Contents")] = w._add_object(cs)
    with path.open("wb") as fh:
        w.write(fh)
    return path


@pytest.mark.unit
def test_pdf_two_columns_and_table_warn(tmp_path):
    two = make_layout_pdf(tmp_path / "two.pdf", [[(40, f"left line {i}"), (330, f"right line {i}")] for i in range(8)])
    assert "multi-column layout" in ats_view(two)["warnings"]
    table = make_layout_pdf(tmp_path / "t.pdf", [[(40, f"a{i}"), (220, f"b{i}"), (400, f"c{i}")] for i in range(4)])
    assert "tables" in ats_view(table)["warnings"]


@pytest.mark.unit
def test_pdf_single_column_with_right_aligned_dates_no_layout_warning(tmp_path):
    rows = [[(40, "alex@example.com")], [(40, "EXPERIENCE")], [(40, "Engineer, Acme"), (480, "2022 - 2024")]]
    rows += [[(40, f"Built thing number {i} with Python")] for i in range(6)]
    w = ats_view(make_layout_pdf(tmp_path / "one.pdf", rows))["warnings"]
    assert "multi-column layout" not in w and "tables" not in w


@pytest.mark.unit
@pytest.mark.parametrize("name,data", [("bad.pdf", b"%PDF-1.4 garbage"), ("bad.docx", b"not a zip")])
def test_corrupt_file_no_text_found(tmp_path, name, data):
    (tmp_path / name).write_bytes(data)
    v = ats_view(tmp_path / name)
    assert v["text"] == "" and "no text found" in v["warnings"]


@pytest.mark.unit
def test_docx_oversized_document_not_read(tmp_path, monkeypatch):
    import careeros.extract as ex
    p = make_docx(tmp_path / "r.docx", ["x" * 2000])
    monkeypatch.setattr(ex, "DOCX_XML_CAP", 1000)
    assert "no text found" in ats_view(p)["warnings"]


@pytest.mark.unit
def test_docx_header_footer_text(tmp_path):
    p = make_docx(tmp_path / "r.docx", ["EXPERIENCE"])
    with zipfile.ZipFile(p, "a") as z:
        z.writestr("word/header1.xml", f'<w:hdr xmlns:w="{W}"><w:p><w:r><w:t>alex@example.com</w:t></w:r></w:p></w:hdr>')
    assert ats_view(p)["fields"]["contact"]["email"] == "alex@example.com"


@pytest.mark.unit
def test_roles_only_in_experience_and_named(tmp_path):
    p = tmp_path / "r.txt"
    p.write_text("a@example.com\nEXPERIENCE\nEngineer, Acme | 2022 - 2024\n2019 - 2020\nEDUCATION\n"
                 "State University | 2018 - 2022\n")
    assert ats_view(p)["fields"]["roles"] == [{"line": "Engineer, Acme", "dates": "2022 - 2024"}]


@pytest.mark.unit
def test_bad_dates_ignore_ratios(tmp_path):
    p = tmp_path / "r.txt"
    p.write_text("a@example.com\nOn call 24/7, 50/50 split\n")
    assert not any(x.startswith("unreadable dates") for x in ats_view(p)["warnings"])


@pytest.mark.unit
def test_main_missing_or_unsupported_file_clean_exit(tmp_path, capsys):
    from careeros.extract import main
    assert main([str(tmp_path / "nope.pdf")]) == 2
    assert main([str(tmp_path / "r.rtf")]) == 2
    assert "Traceback" not in capsys.readouterr().err
