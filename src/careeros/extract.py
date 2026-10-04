"""Résumé text extraction + deterministic ATS view (REQ-098, DEC-001). No LLM, no OCR.

`python -m careeros.extract SRC [OUT]` prints the ATS view, or writes it to OUT (ats.json).
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
HEADINGS = {"summary", "profile", "objective", "experience", "work experience", "professional experience",
            "employment", "employment history", "education", "skills", "technical skills", "projects",
            "certifications", "publications", "awards", "languages", "volunteering", "interests"}
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:{_MONTH}\s+)?(?:19|20)\d{{2}}"
RANGE_RE = re.compile(rf"{_DATE}\s*(?:-|–|—|to)\s*(?:{_DATE}|present|current|now)", re.I)
BAD_DATE_RE = re.compile(r"(?<![\d/])\d{1,2}/\d{2,4}(?![\d/])|'\d{2}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
LINK_RE = re.compile(r"(?:https?://|www\.|(?:linkedin|github)\.com/)[^\s|,;]+", re.I)


def _pdf(path: Path) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n".join(p.extract_text() or "" for p in reader.pages)
    images = False
    for p in reader.pages:
        try:
            images = images or bool(p.images)
        except Exception:  # malformed image objects still mean "there is an image"
            images = True
    # ponytail: no table / multi-column detection for PDF (needs layout analysis); DOCX only.
    return text, ["images (ATS cannot read them)"] if images else []


def _docx(path: Path) -> tuple[str, list[str]]:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        images = any(n.startswith("word/media/") for n in z.namelist())
    text = "\n".join("".join(t.text or "" for t in p.iter(f"{W}t")) for p in root.iter(f"{W}p"))
    warnings = []
    if images or next(root.iter(f"{W}drawing"), None) is not None:
        warnings.append("images (ATS cannot read them)")
    if next(root.iter(f"{W}tbl"), None) is not None:
        warnings.append("tables")
    if any(int(c.get(f"{W}num") or 1) > 1 for c in root.iter(f"{W}cols")):
        warnings.append("multi-column layout")
    return text, warnings


def _read(path: str | Path) -> tuple[str, list[str]]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, warnings = _pdf(path)
    elif suffix == ".docx":
        text, warnings = _docx(path)
    elif suffix in (".txt", ".md"):
        text, warnings = path.read_text(encoding="utf-8", errors="replace"), []
    else:
        raise ValueError(f"unsupported résumé file type: {suffix or path.name} (pdf, docx, txt, md)")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip(), warnings


def extract_text(path: str | Path) -> str:
    """Plain text of a pdf/docx/txt/md résumé ('' when a PDF has no text layer)."""
    return _read(path)[0]


def _fields(text: str) -> tuple[dict[str, Any], list[str]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    email, phone = EMAIL_RE.search(text), PHONE_RE.search(text)
    contact = {"email": email.group(0) if email else None, "phone": phone.group(0) if phone else None,
               "links": [m.group(0).rstrip(".") for m in LINK_RE.finditer(EMAIL_RE.sub("", text))]}
    sections, roles, skills, bad_dates, section = [], [], [], [], ""
    for ln in lines:
        if ln.strip(" :").lower() in HEADINGS:
            section = ln.strip(" :")
            sections.append(section)
            continue
        m = RANGE_RE.search(ln)
        if m:
            roles.append({"line": (ln[:m.start()] + ln[m.end():]).strip(" |,-–—\t"), "dates": m.group(0)})
        elif BAD_DATE_RE.search(ln):
            bad_dates.append(ln)
        if "skill" in section.lower():
            body = re.sub(r"^[^:]{1,30}:", "", ln)
            skills += [s.strip() for s in re.split(r"[,;|•·]", body) if s.strip()]
    warnings = []
    if not (contact["email"] or contact["phone"]):
        warnings.append("missing contact (no email or phone)")
    if bad_dates:
        warnings.append("unreadable dates: " + "; ".join(bad_dates))
    return {"contact": contact, "sections": sections, "roles": roles, "skills": skills}, warnings


def ats_view(path: str | Path) -> dict[str, Any]:
    """What an ATS reads: plain text, parsed fields, warnings. Same input -> same output."""
    text, warnings = _read(path)
    if not text:
        return {"text": "", "fields": {"contact": {"email": None, "phone": None, "links": []}, "sections": [],
                                       "roles": [], "skills": []}, "warnings": ["no text found", *warnings]}
    fields, field_warnings = _fields(text)
    return {"text": text, "fields": fields, "warnings": warnings + field_warnings}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2):
        print("usage: python -m careeros.extract SRC [OUT]", file=sys.stderr)
        return 2
    out = json.dumps(ats_view(args[0]), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if len(args) == 1:
        sys.stdout.write(out)
    else:
        dest = Path(args[1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
