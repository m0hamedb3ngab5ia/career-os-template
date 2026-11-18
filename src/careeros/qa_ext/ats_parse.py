"""Checks that keep résumé parsing clean in ATS parsers (Greenhouse: docs/work/yield-model/research/greenhouse.md s3).

  pdf_size            hard  resume.pdf <= max_pdf_mb (Greenhouse cannot parse files over 2.5 MB)
  abbreviated_titles  soft  experience/leadership titles with abbreviations ("Sr.", "SWE", "Eng.", "Mgr")

Header/footer text is not checked: templates/resume/default.tex sets \\pagestyle{empty} and keeps contact info in
the page body, so the template cannot produce header/footer text; a PDF-position heuristic would flag the name line.

Config (config/qa.yaml, optional):
  resume:
    parse:
      max_pdf_mb: 2.5
      abbreviations: [sr, jr, swe, eng, engr, mgr, dev, assoc, dir, asst]
"""
from __future__ import annotations

import re
from typing import Any

DEFAULT_MAX_MB = 2.5
DEFAULT_ABBREVIATIONS = ("sr", "jr", "swe", "sde", "eng", "engr", "mgr", "dev", "assoc", "dir", "asst", "snr")


def _cfg(ck: Any) -> dict[str, Any]:
    p = ((ck.qa_cfg or {}).get("resume") or {}).get("parse") or {}
    return p if isinstance(p, dict) else {}


def check_ats_parse(ck: Any) -> None:
    cfg = _cfg(ck)
    try:
        max_mb = float(cfg.get("max_pdf_mb", DEFAULT_MAX_MB))
    except (TypeError, ValueError):
        max_mb = DEFAULT_MAX_MB
    if not ck.pdf_path.exists():
        ck.skip("pdf_size", "hard", "resume.pdf not built")
    else:
        mb = ck.pdf_path.stat().st_size / (1024 * 1024)
        ck.add("pdf_size", "hard", mb <= max_mb, f"resume.pdf {mb:.2f} MB (max {max_mb:g} MB for ATS parsing)")

    rj = ck.resume_json if isinstance(ck.resume_json, dict) and "__parse_error__" not in ck.resume_json else None
    if rj is None:
        ck.skip("abbreviated_titles", "soft", "resume.json missing")
        return
    words = [str(w).lower().strip(".") for w in cfg.get("abbreviations") or DEFAULT_ABBREVIATIONS]
    pat = re.compile(r"(?<![\w])(" + "|".join(re.escape(w) for w in words) + r")(?![\w])\.?", re.I) if words else None
    titles = [str(e.get(k)) for sec, k in (("experience", "title"), ("leadership", "role")) for e in rj.get(sec) or []
              if isinstance(e, dict) and e.get(k)]
    bad = [t for t in titles if pat and pat.search(t)]
    ck.add("abbreviated_titles", "soft", not bad,
           "no abbreviated titles" if not bad else "spell out for ATS parsing: " + "; ".join(bad))
