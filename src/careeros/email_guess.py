"""Email finding for outreach drafts, and which jobs are worth the outreach effort.

Method: company domain (configured `company_domains`, else the posting URL when it is not an ATS/aggregator, else the
contacts.json domain find-contacts researched (high|medium), else `<squashedname>.com`, low confidence) -> address guesses from common patterns -> optional Hunter.io domain search
with the candidate's own key (`careeros creds set hunter --password-stdin`) for the company's
real pattern and any exact addresses. Never probes, verifies or sends to an address: checking one (Gmail compose
shows a profile photo for a real Google account) is a manual tip for the candidate.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from careeros.config import Settings, normalize_company
from careeros.safety.scam import AGGREGATOR_DOMAINS, KNOWN_ATS_DOMAINS, company_domains, registrable_domain

APOLLO_API = "https://api.apollo.io/api/v1"
APOLLO_TITLES = ["recruiter", "technical recruiter", "talent acquisition", "university recruiter",
                 "engineering manager", "head of engineering"]
PATTERNS = ("{first}.{last}", "{f}{last}", "{first}", "{first}{l}", "{first}{last}", "{first}_{last}", "{last}")
HUNTER_URL = "https://api.hunter.io/v2/domain-search"
RECRUITER_RE = re.compile(r"recruit|talent|sourc", re.I)
VERIFY_TIP = ("Manual check before sending: paste the address into a Gmail compose 'To' field; a profile photo or "
              "name card usually means a real Google Workspace account. Or search the exact address in quotes.")


def _ascii_words(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z]+", s)


def email_candidates(name: str, domain: str, pattern: str | None = None) -> list[str]:
    """Known pattern first, then the common ones. First word = first name, last word = last name."""
    w = _ascii_words(name)
    if not w or not domain:
        return []
    if len(w) == 1:
        return [f"{w[0]}@{domain}"]
    v = {"first": w[0], "last": w[-1], "f": w[0][0], "l": w[-1][0]}
    out: list[str] = []
    for p in ([pattern] if pattern else []) + list(PATTERNS):
        try:
            addr = p.format(**v) + "@" + domain
        except (KeyError, IndexError, ValueError):  # a Hunter pattern we don't know: skip it
            continue
        if addr not in out:
            out.append(addr)
    return out


def pattern_of(addr: str, name: str) -> str | None:
    """Which PATTERNS entry produced this address for this person; None for a shared inbox or an unknown shape."""
    local, _, domain = addr.lower().partition("@")
    if len(_ascii_words(name)) < 2:
        return None
    return next((p for p in PATTERNS if email_candidates(name, domain, p)[0].split("@")[0] == local), None)


def learned_pattern(path: Path, domain: str) -> dict[str, Any] | None:
    """{"works": pattern or None, "failed": [patterns]} learned from earlier deliveries and bounces at this domain."""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get(domain.lower())
    except (OSError, ValueError):
        return None


def record_email_result(path: Path, addr: str, name: str, *, ok: bool) -> None:
    """User 2026-11-19: learn from every bounce and delivery so the next person at that company gets the right format."""
    p = pattern_of(addr, name)
    if not p:
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    e = data.setdefault(addr.lower().partition("@")[2], {"works": None, "failed": []})
    if ok:
        e["works"] = p
        e["failed"] = [x for x in e["failed"] if x != p]
    else:  # a late bounce overrides an earlier "delivered" (bounces can land minutes after the send)
        if e["works"] == p:
            e["works"] = None
        if p not in e["failed"]:
            e["failed"].append(p)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def company_domain(s: Settings, company: str, posting_url: str = "") -> tuple[str, str]:
    """(domain, confidence high|low)."""
    configured = sorted(company_domains(s, company))
    if configured:
        return configured[0], "high"
    host = urllib.parse.urlparse(posting_url or "").hostname or ""
    d = registrable_domain(host) if host else ""
    if d and d not in KNOWN_ATS_DOMAINS and d not in AGGREGATOR_DOMAINS:
        return d, "high"
    return normalize_company(company).replace(" ", "") + ".com", "low"


def _http(url: str, headers: dict[str, str], body: str | None) -> str:
    """Keys travel in headers, never in a URL or log. Raises urllib errors (HTTPError carries the status)."""
    req = urllib.request.Request(url, headers=headers, data=body.encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed https hosts
        return r.read().decode("utf-8")


def _fetch(url: str, key: str) -> str:
    return _http(url, {"X-API-KEY": key}, None)


def hunter_domain_search(key: str, *, domain: str = "", company: str = "",
                         fetch: Callable[[str, str], str] | None = None) -> dict[str, Any] | None:
    """Hunter.io `data` ({domain, pattern, emails[]}) or None on any error (quota, network, bad key)."""
    q = {"limit": 10, **({"domain": domain} if domain else {"company": company})}
    try:
        return json.loads((fetch or _fetch)(f"{HUNTER_URL}?{urllib.parse.urlencode(q)}", key))["data"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def apollo_search_url(company: str, role: str) -> str:
    """Manual Apollo web search for the candidate to open (never scraped).
    ponytail: Apollo's web-app hash params are undocumented; if this stops filtering, search by hand."""
    return "https://app.apollo.io/#/people?qKeywords=" + urllib.parse.quote(f"{company} {role}")


def apollo_contacts(key: str, domain: str, enrich: int = 2,
                    fetch: Callable[[str, dict[str, str], str], str] | None = None) -> list[dict[str, Any]]:
    """Apollo.io people search (0 credits) at `domain`, then enrich (1 credit each) the first `enrich` people Apollo
    has an email for, recruiters first. Returns [{name, title, email, linkedin_url}]. Raises on HTTP errors
    (403 = the key's plan has no API access)."""
    f = fetch or _http
    h = {"x-api-key": key, "Content-Type": "application/json"}
    found = json.loads(f(f"{APOLLO_API}/mixed_people/api_search", h, json.dumps(
        {"q_organization_domains_list": [domain], "person_titles": APOLLO_TITLES, "per_page": 25})))
    people = [p for p in found.get("people") or [] if p.get("has_email") and p.get("id")]
    people.sort(key=lambda p: not RECRUITER_RE.search(p.get("title") or ""))
    out = []
    for p in people[:max(enrich, 0)]:
        m = (json.loads(f(f"{APOLLO_API}/people/match", h, json.dumps({"id": p["id"]}))) or {}).get("person") or {}
        org = m.get("organization") or {}
        now_at = registrable_domain(org.get("primary_domain") or urllib.parse.urlparse(
            org.get("website_url") or "").hostname or "")
        if m.get("email") and m.get("name") and now_at == domain:  # domain search also returns former employees
            out.append({"name": m["name"], "title": m.get("title") or p.get("title") or "", "email": m["email"],
                        "linkedin_url": m.get("linkedin_url")})
    return out


def apply_to_contacts(data: dict[str, Any], domain: str, domain_conf: str,
                      hunter: dict[str, Any] | None, apollo: list[dict[str, Any]] | None = None,
                      learned: dict[str, Any] | None = None) -> dict[str, Any]:
    """contacts.json with email candidates filled in. Apollo people (who + email) are added first and their email
    wins; then Hunter: exact hits by name (medium, never verified), recruiters it knows are added, and its pattern
    orders every guess."""
    learned = learned or {}  # a delivered format beats any provider estimate; a bounced one is never guessed again
    pattern = learned.get("works") or (hunter or {}).get("pattern") or data.get("email_pattern") or None
    if hunter and hunter.get("domain"):
        domain, domain_conf = hunter["domain"], "high"
    hits = {" ".join(_ascii_words(f"{e.get('first_name') or ''} {e.get('last_name') or ''}")): e
            for e in (hunter or {}).get("emails") or [] if e.get("first_name") and e.get("last_name")}
    contacts = [dict(c) for c in data.get("contacts") or []]
    have = {" ".join(_ascii_words(c.get("name", ""))) for c in contacts}
    found: dict[str, dict[str, Any]] = {}
    for a in apollo or []:
        k = " ".join(_ascii_words(a["name"]))
        found[k] = {"value": a["email"], "source": "apollo.io"}
        if k not in have:
            have.add(k)
            contacts.append({"name": a["name"], "title": a.get("title") or "",
                             "role": "recruiter" if RECRUITER_RE.search(a.get("title") or "") else "hiring_manager",
                             "linkedin": a.get("linkedin_url"), "source": "apollo.io", "confidence": "medium",
                             "possible_referral": False, "linkedin_degree": None, "mutuals": None, "note": ""})
    for k, e in hits.items():
        found.setdefault(k, {"value": e["value"], "source": "hunter.io"})
    for k, e in hits.items():
        if k not in have and RECRUITER_RE.search(e.get("position") or ""):
            contacts.append({"name": f"{e['first_name']} {e['last_name']}", "title": e.get("position") or "",
                             "role": "recruiter", "linkedin": e.get("linkedin") or None, "source": "hunter.io",
                             "confidence": "medium", "possible_referral": False, "linkedin_degree": None,
                             "mutuals": None, "note": ""})
    for c in contacts:
        cands = [a for a in email_candidates(c.get("name", ""), domain, pattern)
                 if pattern_of(a, c.get("name", "")) not in (learned.get("failed") or [])]
        hit = found.get(" ".join(_ascii_words(c.get("name", ""))))
        if c.get("email_confidence") == "verified" and c.get("email"):
            hit = None  # an address seen on a public page beats any provider guess
        elif not hit and c.get("email"):  # earlier provider hit or a pasted address: a rerun never erases it
            hit = {"value": c["email"], "source": c.get("email_source"), "conf": c.get("email_confidence")}
        if hit:
            c["email"], c["email_confidence"] = hit["value"], hit.get("conf") or "medium"
            if hit["source"]:
                c["email_source"] = hit["source"]
            cands = [hit["value"]] + [a for a in cands if a != hit["value"]]
        elif c.get("email_confidence") != "verified":
            c["email"] = None
            c["email_confidence"] = "medium" if pattern else "low"
        c["email_candidates"] = cands
    return {**data, "contacts": contacts, "domain": domain, "domain_confidence": domain_conf,
            "email_pattern": pattern, "email_pattern_source": ((hunter and hunter.get("pattern") and "hunter.io")
                                     or data.get("email_pattern_source")) if pattern else None,
            "verify_tip": VERIFY_TIP}


def outreach_targets(jobs: Iterable[dict[str, Any]], tiers: dict[str, Any], min_fit: int,
                     statuses: Iterable[str], done: set[str]) -> list[dict[str, Any]]:
    """High-yield jobs: tier outreach `always` (any fit) or `if_contact_found` with fit >= min_fit; best fit first,
    one per company."""
    want = set(statuses)
    out = []
    for j in jobs:
        rule = (tiers.get(j.get("tier") or "") or {}).get("outreach", "never")
        fit = j.get("fit") or 0
        if j["status"] in want and j["job_id"] not in done and (
                rule == "always" or (rule == "if_contact_found" and fit >= min_fit)):
            out.append(j)
    seen: set[str] = set()   # one target per company: its recruiters would get the same email twice
    best = []
    for j in sorted(out, key=lambda j: -(j.get("fit") or 0)):
        if (k := normalize_company(j.get("company") or "")) not in seen:
            seen.add(k)
            best.append(j)
    return best
