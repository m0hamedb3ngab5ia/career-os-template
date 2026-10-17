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
BAD_DATE_RE = re.compile(r"(?<![\d/])(?:0?[1-9]|1[0-2])/(?:\d{2}|\d{4})(?![\d/])|'\d{2}\b")
GAP_RE = re.compile(r"\S {4,}(?=\S)")
DOCX_XML_CAP = 20 * 1024 * 1024  # uncompressed bytes per part; zip-bomb guard (threat model)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
LINK_RE = re.compile(r"(?:https?://|www\.|(?:linkedin|github)\.com/)[^\s|,;]+", re.I)
KERN_RE = re.compile(rb"(?<=[>)])\s*\+?\d*\.?\d+\s*(?=[<(])")  # positive kern between TJ strings
LIGATURES = str.maketrans({"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
                           "\ufb05": "st", "\ufb06": "st"})


def pdf_page_text(page: Any) -> str:
    """Text of one pypdf page; every PDF text read goes through here.

    pypdf turns any TJ kern >= a space width into a space, so tight kerns (positive: A-W, T-a) split
    words ("A WS", "T ableau"); only negative kerns open a gap, so drop the positive ones first.
    Ligature glyphs (U+FB00-FB06) are expanded to letters.
    """
    from pypdf.generic import DecodedStreamObject, NameObject

    contents = page.get_contents()
    if contents is not None:
        # ponytail: byte regex, not a content parser (pypdf's ContentStream re-encodes Identity-H strings
        # wrongly); misses Form XObjects; strips a number between unescaped parens in a literal string, e.g. ((1) 2 (3)).
        # Parse properly if those bite.
        fixed = DecodedStreamObject()
        fixed.set_data(KERN_RE.sub(b"", contents.get_data()))
        page[NameObject("/Contents")] = fixed
    runs: list[str] = []
    page.extract_text(visitor_text=lambda t, *_: runs.append(t))
    return join_runs(runs).translate(LIGATURES)


_TIGHT_RE = re.compile(r" +(?=[,.;:!?](?:\s|$)|[)\]])")  # gap before closing punctuation (".NET" keeps its space)


def join_runs(runs: list[str]) -> str:
    """Join pypdf text runs; a run boundary (font switch, e.g. bold) is where pypdf opens a gap it measured wrong.

    At a boundary only, drop the run's leading spaces when they precede , . ; : ! ? ) ] or follow ( [ or an
    existing space ("microservices , Kafka", "( React", "Libraries :"), and collapse a doubled leading gap to one
    space. Spaces inside a run are the source's.
    """
    out, pending = "", ""
    for run in runs:
        run, pending = pending + run, ""
        if run and not run.strip(" "):  # a gap-only run: decide once the next run shows what follows
            pending = run
            continue
        if run.startswith(" ") and (_TIGHT_RE.match(run) or out.endswith(("(", "[", " "))):
            run = run.lstrip(" ")
        elif run.startswith("  "):  # pypdf's gap on top of the run's own space
            run = " " + run.lstrip(" ")
        out += run
    return out + pending


def _pdf(path: Path) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n".join(pdf_page_text(p) for p in reader.pages)
    images = False
    for p in reader.pages:
        try:
            images = images or bool(p.images)
        except Exception:  # malformed image objects still mean "there is an image"
            images = True
    warnings = ["images (ATS cannot read them)"] if images else []
    # ponytail: whitespace-gap heuristic on layout text, not real layout analysis.
    lines = [ln for p in reader.pages for ln in (p.extract_text(extraction_mode="layout") or "").splitlines() if ln.strip()]
    gaps = [len(GAP_RE.findall(ln)) for ln in lines]
    if sum(g >= 2 for g in gaps) >= 3:
        warnings.append("tables")
    if sum(g >= 1 for g in gaps) >= max(3, len(lines) / 2 + 1):
        warnings.append("multi-column layout")
    return text, warnings


def _docx(path: Path) -> tuple[str, list[str]]:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        parts = [n for n in names if re.fullmatch(r"word/header\d*\.xml", n)] + ["word/document.xml"]
        parts += [n for n in names if re.fullmatch(r"word/footer\d*\.xml", n)]
        if sum(z.getinfo(n).file_size for n in parts) > DOCX_XML_CAP:
            raise ValueError("docx too large")
        roots = [ET.fromstring(z.read(n)) for n in parts]
        root = roots[parts.index("word/document.xml")]
        images = any(n.startswith("word/media/") for n in names)
    text = "\n".join("".join(t.text or "" for t in p.iter(f"{W}t")) for r in roots for p in r.iter(f"{W}p"))
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
    if suffix in (".pdf", ".docx"):
        try:
            text, warnings = (_pdf if suffix == ".pdf" else _docx)(path)
        except (ImportError, OSError):
            raise
        except Exception:  # corrupt / oversized file -> "no text found" (09_ARCHITECTURE failure + recovery)
            text, warnings = "", []
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
            name = (ln[:m.start()] + ln[m.end():]).strip(" |,-–—\t")
            if name and re.search("experience|employment", section, re.I):
                roles.append({"line": name, "dates": m.group(0)})
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
    try:
        view = ats_view(args[0])
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = json.dumps(view, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if len(args) == 1:
        sys.stdout.write(out)
    else:
        dest = Path(args[1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
