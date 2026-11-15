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
| `salary_below_min` | posted salary_max (USD or no currency) < candidate.min_base_usd |
| `location_nonpreferred` | thresholds.min_fit_nonpreferred_location > 100 (never wanted) and every posting location is a US state outside `location.preferred` / `preferred_regions`; not remote when remote_ok, not pay-exempt; unparseable = no fail |

Not a fail: `pay_exempts_location` (see `pay_exempts_location`), reported by `job filters`.
"""
from __future__ import annotations

import re
from typing import Any

from careeros.config import Settings

# "6+ years", "at least 5 years", "5-7 years", "4 years'" followed by "experience" in the same clause
_YEARS = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?)?\s*years?\b'?"
                    r"(?P<tail>[^.;\n]{0,60})", re.I)
_COMPANY = re.compile(r"\b(we|we've|our|us|has|founded|for|more than|over|building on)\b", re.I)  # company history, not a requirement
_HISTORY = re.compile(r"\bof (investing|history)\b|\bin business\b", re.I)  # "30 years of investing experience"
_OPT_HEAD = re.compile(r"\b(preferred|nice[- ]to[- ]haves?|bonus|plus)\b", re.I)
_REQ_HEAD = re.compile(r"\b(required|requirements?|minimum|must|basic|qualifications|what you need|you have|you bring)\b",
                       re.I)
_OPTIONAL = re.compile(r"\b(prefer\w*|nice to have|bonus|ideally|a plus)\b", re.I)


def min_years_required(text: str) -> int | None:
    """Largest required minimum years of experience stated in `text`, or None. Clauses that say preferred / nice to
    have / bonus, internship-only experience and years without "experience" never count."""
    found, optional = [], False
    for line in re.split(r"(?<=[.;])\s+|\n", text or ""):
        head = line.strip()
        if head and not _YEARS.search(head) and (len(head) <= 50 or head.endswith(":")):  # section header
            if _OPT_HEAD.search(head):
                optional = True
            elif _REQ_HEAD.search(head):
                optional = False
            continue
        for m in _YEARS.finditer(line):
            tail = m.group("tail").lower().split(",")[0]  # this clause only: "5+ required, 7 preferred"
            if optional or _HISTORY.search(m.group("tail")):
                continue
            if _OPTIONAL.search(tail) or _OPTIONAL.search(line[max(0, m.start() - 25):m.start()]):
                continue
            if _COMPANY.search(line[max(0, m.start() - 30):m.start()]):  # "Acme has 20 years", "for 10 years we"
                continue
            if re.search(r"\bexperience\b", tail) and "intern" not in tail:
                found.append(int(m.group(1)))
    return max(found) if found else None


def max_years(settings: Settings) -> int:
    return int((settings.targets.get("seniority") or {}).get("max_years_required", 3))


_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california", "CO": "colorado",
    "CT": "connecticut", "DE": "delaware", "DC": "district of columbia", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland", "MA": "massachusetts",
    "MI": "michigan", "MN": "minnesota", "MS": "mississippi", "MO": "missouri", "MT": "montana",
    "NE": "nebraska", "NV": "nevada", "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico",
    "NY": "new york", "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina", "SD": "south dakota",
    "TN": "tennessee", "TX": "texas", "UT": "utah", "VT": "vermont", "VA": "virginia", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming"}  # no "washington" name: state or D.C.? "Seattle, WA" still parses by code
# `location.preferred_regions` entries that name US states. "US" itself = every state; any other entry
# (ISO country code, unknown name) makes the check undecidable.
REGION_STATES = {
    "northeast us": "ME NH VT MA RI CT NY NJ PA".split(),
    "midwest us": "OH MI IN IL WI MN IA MO ND SD NE KS".split(),
    "southeast us": "DE MD DC VA WV NC SC GA FL KY TN AL MS AR LA".split(),
    "southwest us": "TX OK NM AZ".split(),
    "west us": "WA OR CA NV ID MT WY UT CO AK HI".split(),
}
_STATE_CODE = re.compile(r"(?:,|\s)\s*([A-Z]{2})\b(?!\.)")


def _states_in(text: str) -> set[str]:
    """Every US state named in `text` by 2-letter code or full name."""
    found = {c for c in _STATE_CODE.findall(text) if c in _STATES}
    low = text.lower()
    return found | {c for c, n in _STATES.items() if re.search(rf"(?<![a-z]){n}(?![a-z])", low)}


_COUNTRY = re.compile(r"\s*(united states( of america)?|usa|u\.s\.a?\.?|us)\s*", re.I)


_NAME_TO_CODE = {n: c for c, n in _STATES.items()}


def _strict_states(segment: str) -> set[str]:
    """States of a segment that is exactly `City, ST[, City, ST ...]` (state code or full name; parentheticals and
    country words ignored). Anything else in it (an extra city, free text) returns set(): unparsed."""
    toks = [t.strip() for t in re.sub(r"\([^)]*\)", "", segment).split(",") if t.strip()]
    toks = [t for t in toks if not _COUNTRY.fullmatch(t)]
    out: set[str] = set()
    if not toks or len(toks) % 2:
        return set()
    for city, st in zip(toks[::2], toks[1::2]):
        code = st.upper() if st.upper() in _STATES else _NAME_TO_CODE.get(st.lower())
        if not code or city.upper() in _STATES:
            return set()
        out.add(code)
    return out


def posting_states(posting: dict[str, Any]) -> list[str]:
    """Union of the US states in every listed location, [] when any part is not a clean `City, ST` (a bare city,
    "Northeast", extra words). A segment that is only the country ("United States") is ignored."""
    parts = [x for x in re.split(r"[;|\n•/&]| or ", str(posting.get("location") or ""))
             if x.strip() and not _COUNTRY.fullmatch(x)]
    sets = [_strict_states(x) for x in parts]
    return sorted(set().union(*sets)) if parts and all(sets) else []


def location_nonpreferred(settings: Settings, posting: dict[str, Any]) -> bool:
    """True only when the non-preferred-location rule is decisive (min fit above 100 = never wanted) and the
    posting is clearly outside the candidate's places. Anything unclear returns False: the skill decides."""
    t, loc = settings.targets.get("thresholds") or {}, settings.targets.get("location") or {}
    if (t.get("min_fit_nonpreferred_location") or 0) <= 100 or pay_exempts_location(settings, posting):
        return False
    text = str(posting.get("location") or "")
    if re.search(r"\bhybrid\b", text, re.I) or (loc.get("remote_ok", True) and (
            posting.get("remote") is True or re.search(r"\bremote\b", text, re.I))):
        return False  # hybrid / remote: the skill decides
    ok: set[str] = set()
    for city in loc.get("preferred") or []:  # "Boston MA": the whole state counts, "Cambridge, MA" is close enough
        ok |= _states_in(str(city))
    for region in loc.get("preferred_regions") or []:
        key = str(region).strip().lower()
        if key in ("us", "usa", "united states") or key not in REGION_STATES:
            return False
        ok.update(REGION_STATES[key])
    states = posting_states(posting)
    return bool(states) and not ok.intersection(states)


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
    usd = str(p.salary_currency or "USD").upper() == "USD"  # explicit other currency: not comparable, leave to the skill
    if usd and isinstance(p.salary_max, (int, float)) and floor and p.salary_max < floor:
        fails.append("salary_below_min")
    if location_nonpreferred(settings, posting):
        fails.append("location_nonpreferred")
    return fails


def pay_exempts_location(settings: Settings, posting: dict[str, Any]) -> bool:
    """True when the posted minimum base (USD) is at least thresholds.any_location_min_base_usd: score-job then
    skips the non-preferred-location fit rule. Unlisted minimum, other currency or key unset = False."""
    cap = (settings.targets.get("thresholds") or {}).get("any_location_min_base_usd")
    lo = posting.get("salary_min")
    usd = str(posting.get("salary_currency") or "USD").upper() == "USD"
    return bool(cap and usd and isinstance(lo, (int, float)) and lo >= cap)


def reasons(settings: Settings, posting: dict[str, Any], fails: list[str]) -> list[str]:
    """One sentence per fail for score.json `fit_reasons` (the UI's "Why" list)."""
    yrs = min_years_required(posting.get("description_text") or "")
    text = {"company_blocked": "Company: on the blocklist.",
            "title_senior": "Seniority: the title names a level above the target (seniority.exclude_title_keywords).",
            "location_blocked": "Location: in a blocked country.",
            "location_nonpreferred": f"prefilter: location_nonpreferred ({', '.join(posting_states(posting))}): "
                                     "outside the preferred places and non-preferred locations are never wanted "
                                     "(thresholds.min_fit_nonpreferred_location above 100).",
            "salary_below_min": f"Salary: posted maximum {posting.get('salary_max')} is below the minimum base."}
    return [text.get(f) or f"Experience: requires {yrs}+ years, above the {max_years(settings)}-year limit; "
            "a dealbreaker, so fit is not scored." for f in fails]


def write_skip(settings: Settings, job_id: str, posting: dict[str, Any], fails: list[str], store: Any = None) -> dict:
    """Write the skip score.json + log line for a hard-filter fail (shared by `job filters` and the score run);
    returns the result dict."""
    from careeros.models import now_iso
    from careeros.scout import Prefilter
    from careeros.store import Store

    store = store or Store(settings)
    cat = Prefilter(settings).title_category(str(posting.get("title") or "")) or "unknown"
    res = {"skill": "score-job", "job_id": job_id, "category": cat, "fit": 0, "tier": None, "decision": "skip",
           "skip_reason": fails[0], "hard_filter_fails": fails,
           "pay_exempts_location": pay_exempts_location(settings, posting)}
    why = reasons(settings, posting, fails)
    store._write(job_id, "score.json", {**res, "company": posting.get("company"), "title": posting.get("title"),
                                        "fit_breakdown": {}, "fit_reasons": why, "reasons": why,
                                        "scored_at": now_iso()})
    store.append_log(job_id, f"category={cat} fit=0 tier=None decision=skip {fails[0]}", component="score-job")
    return res


def compare_with_scores(settings: Settings, store: Any = None) -> list[str]:
    """Job ids Claude scored `prepare` that the hard filters would skip: each one is a prefilter bug."""
    from careeros.store import Store

    store = store or Store(settings)
    bad = []
    for d in sorted(p for p in store.jobs_dir.iterdir() if p.is_dir()):
        sc, post = store._read(d.name, "score.json"), store._read(d.name, "posting.json")
        if sc and post and sc.get("decision") == "prepare" and hard_filters(settings, post):
            bad.append(d.name)
    return bad
