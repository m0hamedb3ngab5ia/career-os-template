"""Find a company's public job board (Greenhouse, Ashby, Lever) from its name.

Used to turn job-alert emails (company names only) into scout `boards:` entries.
A hit is a board API that answers with at least one job.
"""
from __future__ import annotations

import re

from careeros.scout.base import BoardNotFound, FetchError, get_json

APIS = (
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}"),
    ("lever", "https://api.lever.co/v0/postings/{slug}"),
)
_SUFFIX = re.compile(r"\s+(inc|llc|ltd|co|corp|corporation|company|plc|p\.a)\.?$", re.I)


def slug_candidates(name: str) -> list[str]:
    """Lowercased slug guesses: legal suffix dropped first, then joined and hyphenated forms."""
    out: list[str] = []
    base = re.sub(r"\(.*?\)", "", name).strip()
    for n in (_SUFFIX.sub("", base), base, base.split(".")[0]):
        words = re.findall(r"[a-z0-9]+", n.lower())
        for s in ("".join(words), "-".join(words)):
            if s and s not in out:
                out.append(s)
    return out


def find_board(name: str) -> dict | None:
    for slug in slug_candidates(name):
        for ats, url in APIS:
            try:
                data = get_json(url.format(slug=slug), retries=0)
            except (BoardNotFound, FetchError):
                continue
            jobs = data if ats == "lever" else (data.get("jobs") if isinstance(data, dict) else None)
            if isinstance(jobs, list) and jobs:
                return {"company": name, "ats": ats, "slug": slug, "jobs": len(jobs)}
    return None
