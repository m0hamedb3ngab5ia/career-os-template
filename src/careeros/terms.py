"""Shared term matching (QA keyword coverage, résumé match, ATS view)."""
from __future__ import annotations

import re


def term_in_text(term: str, text: str) -> bool:
    """Whole-term, case-insensitive match. "go" must not hit "governance"; "C++" / "Next.js" are
    matched literally with lookarounds on non-word characters instead of \\b (which fails after '+')."""
    pat = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    return re.search(pat, text, re.IGNORECASE) is not None


def term_variants(term: str) -> set[str]:
    """Spellings counted as the same term: "CI-CD" ~ "ci cd" ~ "cicd", "Node.js" ~ "nodejs"."""
    t = term.lower().strip()
    return {v for v in (t, t.replace("-", " "), t.replace(" ", ""), t.replace(".", "")) if v}


def term_hit(term: str, text: str) -> bool:
    return any(term_in_text(v, text) for v in term_variants(term))
