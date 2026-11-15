"""score-job's deterministic hard filters, in code instead of the LLM (`careeros job filters <id>`).

A fail ends scoring like a dealbreaker: score.json gets decision `skip`, fit 0, no tier. Rules reuse the scout
Prefilter and existing config keys; the skill keeps only the judgment calls (sponsorship, clearance, industry,
already applied, safety, prestige).

| fail | rule |
|---|---|
| `company_blocked`  | companies.yaml blocklist (scout filter `blocklist`) |
| `title_senior`     | targets.yaml seniority.exclude_title_keywords in the title (scout filter `seniority`) |
| `location_blocked` | targets.yaml location.blocked_countries (scout filter `location`) |
| `yoe_gt_<n>`       | a required (not preferred) minimum years of experience > seniority.max_years_required (default 3) |
| `salary_below_min` | posted salary_max < candidate.min_base_usd |
"""
from __future__ import annotations

import re
from typing import Any

from careeros.config import Settings

# "6+ years", "at least 5 years", "5-7 years", "4 years'" followed by "experience" in the same clause
_YEARS = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?)?\s*years?\b'?"
                    r"(?P<tail>[^.;\n]{0,60})", re.I)
_OPTIONAL = re.compile(r"\b(prefer\w*|nice to have|bonus|ideally|a plus)\b", re.I)


def min_years_required(text: str) -> int | None:
    """Largest required minimum years of experience stated in `text`, or None. Clauses that say preferred / nice to
    have / bonus, internship-only experience and years without "experience" never count."""
    found = []
    for line in re.split(r"(?<=[.;])\s+|\n", text or ""):
        if _OPTIONAL.search(line):
            continue
        for m in _YEARS.finditer(line):
            tail = m.group("tail").lower()
            if "experience" in tail and "intern" not in tail:
                found.append(int(m.group(1)))
    return max(found) if found else None


def max_years(settings: Settings) -> int:
    return int((settings.targets.get("seniority") or {}).get("max_years_required", 3))


def hard_filters(settings: Settings, posting: dict[str, Any]) -> list[str]:
    from careeros.models import Posting
    from careeros.scout import Prefilter, scout_config

    p = Posting.model_validate(posting)
    on = scout_config(settings)["filters"]
    pf = Prefilter(settings, filters=on)
    fails = []
    if on["blocklist"] and settings.is_blocklisted(p.company):
        fails.append("company_blocked")
    if on["seniority"] and pf.title_senior(p.title):
        fails.append("title_senior")
    if on["location"] and pf.location_blocked(p):
        fails.append("location_blocked")
    yrs, cap = min_years_required(p.description_text), max_years(settings)
    if yrs is not None and yrs > cap:
        fails.append(f"yoe_gt_{cap}")
    floor = (settings.targets.get("candidate") or {}).get("min_base_usd")
    if isinstance(p.salary_max, (int, float)) and floor and p.salary_max < floor:
        fails.append("salary_below_min")
    return fails


def reasons(settings: Settings, posting: dict[str, Any], fails: list[str]) -> list[str]:
    """One sentence per fail for score.json `fit_reasons` (the UI's "Why" list)."""
    yrs = min_years_required(posting.get("description_text") or "")
    text = {"company_blocked": "Company: on the blocklist.",
            "title_senior": "Seniority: the title names a level above the target (seniority.exclude_title_keywords).",
            "location_blocked": "Location: in a blocked country.",
            "salary_below_min": f"Salary: posted maximum {posting.get('salary_max')} is below the minimum base."}
    return [text.get(f) or f"Experience: requires {yrs}+ years, above the {max_years(settings)}-year limit; "
            "a dealbreaker, so fit is not scored." for f in fails]
