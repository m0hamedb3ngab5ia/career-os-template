"""resume.pdf fidelity checks: what a recruiter clicks and what an ATS parses must match the reviewed résumé.

`Checker.check_pdf` (careeros.qa) already covers page count and contact extraction; this module adds:

  pdf_links_clickable      hard  identity links (email -> mailto:, linkedin, github, website) exist as URI link
                                 annotations pointing at the profile's targets
  pdf_text_matches_resume  hard  token recall of resume.txt in the PDF's extracted text >= text_recall_hard;
                                 soft (warning) when in [text_recall_soft, text_recall_hard); hard below that
  pdf_text_split_words     soft  words the PDF extracts as fragments ("A WS", "EDUCA TION"): not lost, but an
                                 ATS may read two words (only reported when any exist)
  pdf_hidden_text          soft  words in the PDF text that resume.txt does not contain (hidden/white text)
  pdf_fonts_embedded       soft  every font carries an embedded font program
  pdf_metadata             soft  /Title set and not a placeholder; /Author == profile identity.name

Config (config/qa.yaml, all optional):
  pdf:
    links_required: [email, linkedin, github, website]   # identity fields that must be clickable (if set)
    text_recall_hard: 0.97
    text_recall_soft: 0.9
    extra_tokens_max: 0          # PDF-only words tolerated before pdf_hidden_text warns
    missing_sample: 15           # cap on missing/extra/split token samples in details and extras
    metadata_placeholders: [...] # case-insensitive /Title or /Author values treated as placeholders

Result: ck.extras["pdf_fidelity"] = {text_recall, missing_tokens, split_tokens, extra_tokens, links_found,
links_missing, fonts_not_embedded, metadata: {title, author}, file_name} or {"skipped": reason}.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

CHECKS = ("pdf_links_clickable", "pdf_text_matches_resume", "pdf_fonts_embedded", "pdf_metadata")
LINK_FIELDS = ("email", "linkedin", "github", "website")
DEFAULT_PLACEHOLDERS = ("latex", "untitled", "anonymous", "author", "title", "document", "name", "your name",
                        "microsoft word", "resume.tex", "main.tex")
# The renderer (templates/resume/render.py) always writes <job_dir>/resume.pdf; there is no per-candidate
# file-name convention to enforce, only this fixed name.
EXPECTED_FILE_NAME = "resume.pdf"

_BULLETS = "•·▪◦‣∙●■⁃➢"
_DASHES = "‐‑‒–—―−"
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#]*(?:[.'][a-z0-9+#]+)*")
_HYPHEN_WRAP_RE = re.compile(r"(\w)-[ \t]*\n\s*([a-z])")


# --------------------------------------------------------------------------- #
# text normalization
# --------------------------------------------------------------------------- #

def normalize_text(text: str) -> str:
    """Lower-case text with ligatures, smart quotes, bullets, dashes, soft hyphens and line-wrap hyphens
    normalized, so resume.txt and extracted PDF text compare word for word."""
    t = unicodedata.normalize("NFKC", text or "")  # ﬁ ﬂ ﬀ ﬃ -> fi fl ff ffi, NBSP -> space
    t = t.replace("­", "")
    t = t.translate({ord(c): "'" for c in "‘’‚‛′"})
    t = t.translate({ord(c): '"' for c in "“”„‟″"})
    t = t.translate({ord(c): "-" for c in _DASHES})
    t = t.translate({ord(c): " " for c in _BULLETS})
    t = _HYPHEN_WRAP_RE.sub(r"\1\2", t)
    return t.lower()


def text_tokens(text: str) -> list[str]:
    """Word/number tokens of normalized text ("3.6", "c++", "node.js" stay whole; "/" and "-" split)."""
    return _TOKEN_RE.findall(normalize_text(text))


def _split_recoveries(missing: Counter, pdf_toks: list[str]) -> tuple[Counter, set[int]]:
    """Missing words the PDF extracts as 2-4 adjacent fragments ("a ws" -> "aws").
    Returns (recovered counts, indices of the fragment tokens)."""
    recovered: Counter = Counter()
    used: set[int] = set()
    for i in range(len(pdf_toks)):
        for n in (2, 3, 4):
            window = range(i, i + n)
            if i + n > len(pdf_toks) or used.intersection(window):
                continue
            joined = "".join(pdf_toks[j] for j in window)
            if len(joined) >= 3 and recovered[joined] < missing.get(joined, 0):
                recovered[joined] += 1
                used.update(window)
                break
    return recovered, used


# --------------------------------------------------------------------------- #
# PDF inspection
# --------------------------------------------------------------------------- #

def _obj(x: Any) -> Any:
    return x.get_object() if hasattr(x, "get_object") else x


def _link_uris(reader: Any) -> list[str]:
    uris = []
    for page in reader.pages:
        for a in _obj(page.get("/Annots")) or []:
            a = _obj(a)
            if a.get("/Subtype") != "/Link":
                continue
            act = _obj(a.get("/A")) or {}
            if act.get("/S") == "/URI" and act.get("/URI"):
                uri = act["/URI"]
                uris.append(uri.decode("latin-1") if isinstance(uri, bytes) else str(uri))
    return uris


def _norm_url(u: str) -> str:
    u = u.strip().lower()
    u = re.sub(r"^[a-z][a-z0-9+.-]*://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("?")[0].split("#")[0].rstrip("/")


def _domain(u: str) -> str:
    return _norm_url(u).split("/")[0]


def _font_embedded(font: Any) -> bool:
    if font.get("/Subtype") == "/Type3":
        return True  # glyphs are content-stream procedures inside the PDF
    if font.get("/Subtype") == "/Type0":
        desc = _obj(font.get("/DescendantFonts")) or []
        return all(_font_embedded(_obj(d)) for d in desc) if desc else False
    fd = _obj(font.get("/FontDescriptor")) or {}
    return any(k in fd for k in ("/FontFile", "/FontFile2", "/FontFile3"))


def _fonts(reader: Any) -> dict[str, bool]:
    out: dict[str, bool] = {}
    seen: set[int] = set()

    def walk(res: Any) -> None:
        res = _obj(res) or {}
        if id(res) in seen:
            return
        seen.add(id(res))
        for f in (_obj(res.get("/Font")) or {}).values():
            f = _obj(f)
            name = re.sub(r"^[A-Z]{6}\+", "", str(f.get("/BaseFont", "?")).lstrip("/"))
            out[name] = out.get(name, True) and _font_embedded(f)
        for x in (_obj(res.get("/XObject")) or {}).values():
            x = _obj(x)
            if x.get("/Subtype") == "/Form" and "/Resources" in x:
                walk(x["/Resources"])

    for page in reader.pages:
        walk(page.get("/Resources"))
    return out


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #

def _cfg(ck: Any) -> dict[str, Any]:
    qa = ck.qa_cfg if isinstance(ck.qa_cfg, dict) else {}
    pdf = qa.get("pdf")
    return pdf if isinstance(pdf, dict) else {}


def _identity(ck: Any) -> dict[str, Any]:
    prof = getattr(ck.profile, "profile", {}) or {}
    ident = prof.get("identity") if isinstance(prof, dict) else None
    return ident if isinstance(ident, dict) else {}


def _check_links(ck: Any, reader: Any, cfg: dict[str, Any], ex: dict[str, Any]) -> None:
    ident = _identity(ck)
    fields = [f for f in (cfg.get("links_required") or LINK_FIELDS) if ident.get(f)]
    uris = _link_uris(reader)
    ex["links_found"] = uris
    mailto = {_norm_url(u[len("mailto:"):]) for u in uris if u.lower().startswith("mailto:")}
    web = {_norm_url(u) for u in uris if not u.lower().startswith("mailto:")}
    missing, notes = [], []
    for f in fields:
        want = str(ident[f])
        if f == "email":
            if _norm_url(want) not in mailto:
                missing.append(f)
                notes.append(f"email: no mailto:{want} link")
            continue
        if _norm_url(want) in web:
            continue
        missing.append(f)
        wrong = [u for u in uris if _domain(u) == _domain(want)]
        notes.append(f"{f} link points at {', '.join(wrong)} (want {want})" if wrong else f"{f}: no {want} link")
    ex["links_missing"] = missing
    if not fields:
        ck.add("pdf_links_clickable", "hard", True, "no identity links in profile to check")
        return
    ck.add("pdf_links_clickable", "hard", not missing,
           f"clickable: {', '.join(fields)}" if not missing else "; ".join(notes))


def _check_text(ck: Any, pdf_text: str, cfg: dict[str, Any], ex: dict[str, Any]) -> None:
    if ck.resume_txt is None:
        ck.skip("pdf_text_matches_resume", "hard", "resume.txt missing")
        return
    hard_min = float(cfg.get("text_recall_hard", 0.97))
    soft_min = float(cfg.get("text_recall_soft", 0.9))
    sample = int(cfg.get("missing_sample", 15))
    max_extra = int(cfg.get("extra_tokens_max", 0))

    txt_toks, pdf_toks = text_tokens(ck.resume_txt), text_tokens(pdf_text)
    cr, cp = Counter(txt_toks), Counter(pdf_toks)
    missing = Counter({t: n - cp.get(t, 0) for t, n in cr.items() if n > cp.get(t, 0)})
    recovered, fragment_idx = _split_recoveries(missing, pdf_toks)
    total = sum(cr.values())
    matched = sum(min(n, cp.get(t, 0)) for t, n in cr.items()) + sum(recovered.values())
    recall = round(matched / total, 4) if total else 1.0
    still = missing - recovered
    missing_list = [t for t, _ in still.most_common()][:sample]
    extra = sorted({t for i, t in enumerate(pdf_toks) if t not in cr and i not in fragment_idx})
    ex.update(text_recall=recall, missing_tokens=missing_list, split_tokens=sorted(recovered)[:sample],
              extra_tokens=extra[:sample])

    detail = f"token recall {recall:.3f} of resume.txt in PDF text"
    if missing_list:
        detail += f"; missing: {', '.join(missing_list)}"
    if recall >= hard_min:
        ck.add("pdf_text_matches_resume", "hard", True, detail)
    elif recall >= soft_min:
        ck.add("pdf_text_matches_resume", "soft", False, detail + f" (below {hard_min})")
    else:
        ck.add("pdf_text_matches_resume", "hard", False, detail + f" (below {soft_min})")

    if recovered:
        ck.add("pdf_text_split_words", "soft", False,
               "PDF text splits words (an ATS may miss the keyword): " + ", ".join(sorted(recovered)[:sample]))
    if len(extra) > max_extra:
        ck.add("pdf_hidden_text", "soft", False,
               f"{len(extra)} word(s) in PDF text not in resume.txt (hidden/white text?): {', '.join(extra[:sample])}")


def _check_fonts(ck: Any, reader: Any, ex: dict[str, Any]) -> None:
    fonts = _fonts(reader)
    bad = sorted(n for n, ok in fonts.items() if not ok)
    ex["fonts_not_embedded"] = bad
    ck.add("pdf_fonts_embedded", "soft", not bad,
           f"{len(fonts)} font(s), all embedded" if not bad else f"not embedded: {', '.join(bad)}")


def _example_name(ck: Any) -> str | None:
    """The shipped example candidate's name, unless QA is running against the example repo itself."""
    try:
        from careeros.doctor import example_identity, find_examples

        examples = find_examples(ck.root)
        if examples is None or ck.prof_path.resolve().is_relative_to(examples.resolve()):
            return None
        return example_identity(examples).get("name")
    except Exception:  # noqa: BLE001 - optional refinement only
        return None


def _check_metadata(ck: Any, reader: Any, cfg: dict[str, Any], ex: dict[str, Any]) -> None:
    meta = reader.metadata or {}
    title = str(meta.get("/Title") or "").strip()
    author = str(meta.get("/Author") or "").strip()
    ex["metadata"] = {"title": title, "author": author}
    ex["file_name"] = ck.pdf_path.name

    def squash(s: str) -> str:
        return " ".join(s.split()).lower()

    placeholders = {squash(str(p)) for p in (cfg.get("metadata_placeholders") or DEFAULT_PLACEHOLDERS)}
    example = _example_name(ck)
    cand = str(_identity(ck).get("name") or "").strip()

    def placeholder(v: str) -> bool:
        s = squash(v)
        return s in placeholders or s.endswith((".tex", ".docx", ".doc")) or bool(example and squash(example) in s)

    problems = []
    if not title:
        problems.append("Title missing")
    elif placeholder(title):
        problems.append(f"Title is a placeholder: '{title}'")
    if not author:
        problems.append("Author missing" + (f" (want '{cand}')" if cand else ""))
    elif placeholder(author):
        problems.append(f"Author is a placeholder: '{author}'")
    elif cand and squash(author) != squash(cand):
        problems.append(f"Author '{author}' != candidate '{cand}'")
    if ck.pdf_path.name != EXPECTED_FILE_NAME:
        problems.append(f"file name '{ck.pdf_path.name}' (renderer writes {EXPECTED_FILE_NAME})")
    ck.add("pdf_metadata", "soft", not problems,
           f"Title '{title}', Author '{author}'" if not problems else "; ".join(problems))


def check_pdf_fidelity(ck: Any) -> None:
    """Run the resume.pdf fidelity checks against a careeros.qa.Checker (records into ck.checks/ck.extras)."""
    def skip_all(why: str, level_soft: bool = False) -> None:
        for name in CHECKS:
            ck.skip(name, "soft" if level_soft or name in ("pdf_fonts_embedded", "pdf_metadata") else "hard", why)
        ck.extras["pdf_fidelity"] = {"skipped": why}

    if not ck.pdf_path.exists():
        skip_all("resume.pdf not built")
        return
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:  # pragma: no cover
        skip_all("pypdf not installed; cannot inspect resume.pdf", level_soft=True)
        return
    try:
        reader = PdfReader(str(ck.pdf_path))
        pdf_text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:  # noqa: BLE001 - Checker.check_pdf already hard-fails `pdf` on this
        skip_all(f"resume.pdf unreadable (see check `pdf`): {type(e).__name__}")
        return

    cfg = _cfg(ck)
    ex: dict[str, Any] = {}
    ck.extras["pdf_fidelity"] = ex
    steps = (("pdf_links_clickable", lambda: _check_links(ck, reader, cfg, ex)),
             ("pdf_text_matches_resume", lambda: _check_text(ck, pdf_text, cfg, ex)),
             ("pdf_fonts_embedded", lambda: _check_fonts(ck, reader, ex)),
             ("pdf_metadata", lambda: _check_metadata(ck, reader, cfg, ex)))
    for name, step in steps:
        try:
            step()
        except Exception as e:  # noqa: BLE001 - a malformed object must not crash the whole gate
            ck.add(name, "soft", False, f"could not inspect resume.pdf: {type(e).__name__}: {e}")
