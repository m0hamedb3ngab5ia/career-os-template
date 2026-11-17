"""SimplifyJobs New-Grad-Positions listings: one public JSON file, many employers (an aggregator, like Handshake).

Board (companies.yaml):
  - {company: SimplifyJobs, ats: simplify, slug: simplify, window_days: 14, categories: [Software, AI/ML/Data]}

`url`        override the listings.json URL (default below, the repo's `dev` branch)
`window_days` keep listings posted within this many days (default 14)
`categories`  keep only these Simplify categories (default: all; the scout title filter does the rest)

A listing whose apply URL is a Greenhouse/Ashby/Lever job is stored with that ats and board slug, so the existing
apply adapters work; anything else is stored as ats "other" (apply by hand). Listings carry no description:
enrich() fetches it per job from the ATS API (a failed fetch drops the listing); ats "other" is stored with
raw.needs_description=true and the score run skips it.
All listing text is untrusted data: nothing here interprets it, and Store.save_posting runs the injection scan.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

from careeros.config import normalize_company
from careeros.models import Posting
from careeros.safety.ghost import history_key
from careeros.scout.base import Adapter, get_json

LISTINGS_URL = ("https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json")
WINDOW_DAYS = 14

_GH_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io", "job-boards.eu.greenhouse.io")
_ASHBY_HOST = "jobs.ashbyhq.com"
_LEVER_HOSTS = ("jobs.lever.co", "jobs.eu.lever.co")


def family_of(url: str) -> tuple[str, str, str, str]:
    """(ats, board slug, job id, clean url) for a Greenhouse/Ashby/Lever job URL; ("other", "", "", url) otherwise."""
    other = ("other", "", "", url or "")
    try:
        u = urlsplit(url or "")
    except ValueError:
        return other
    host, parts = (u.hostname or "").lower(), [x for x in u.path.split("/") if x]
    if u.scheme not in ("http", "https"):
        return other
    if host in _GH_HOSTS:
        if len(parts) >= 3 and parts[1] == "jobs" and parts[2].isdigit():
            return "greenhouse", parts[0], parts[2], f"https://{host}/{parts[0]}/jobs/{parts[2]}"
        q = parse_qs(u.query)
        if parts[:2] == ["embed", "job_app"] and q.get("for") and (q.get("token") or [""])[0].isdigit():
            return "greenhouse", q["for"][0], q["token"][0], f"https://job-boards.greenhouse.io/{q['for'][0]}/jobs/{q['token'][0]}"
    elif host == _ASHBY_HOST and len(parts) >= 2 and re.fullmatch(r"[0-9a-f-]{36}", parts[1], re.I):
        return "ashby", parts[0], parts[1], f"https://{host}/{parts[0]}/{parts[1]}"
    elif host in _LEVER_HOSTS and len(parts) >= 2 and re.fullmatch(r"[0-9a-f-]{36}", parts[1], re.I):
        return "lever", parts[0], parts[1], f"https://{host}/{parts[0]}/{parts[1]}"
    return other


def _iso(epoch: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


class SimplifyAdapter(Adapter):
    ats = "simplify"

    def fetch(self, board: dict[str, Any]) -> list[Posting]:
        return self.parse(get_json(board.get("url") or LISTINGS_URL), board)

    def parse(self, data: Any, board: dict[str, Any]) -> list[Posting]:
        window = int(board.get("window_days") or WINDOW_DAYS)
        cats = {str(c).lower() for c in board.get("categories") or []}
        cutoff = datetime.now(timezone.utc).timestamp() - window * 86400
        out: list[Posting] = []
        seen: set[str] = set()
        for j in data if isinstance(data, list) else []:
            if not isinstance(j, dict) or not j.get("active") or not j.get("is_visible"):
                continue
            sid = str(j.get("id") or "")
            title, company = str(j.get("title") or "").strip(), str(j.get("company_name") or "").strip()
            posted = j.get("date_posted")
            if not (sid and title and company) or sid in seen or not isinstance(posted, (int, float)) or posted < cutoff:
                continue
            if cats and str(j.get("category") or "").lower() not in cats:
                continue
            seen.add(sid)
            fam, slug, jid, url = family_of(str(j.get("url") or ""))
            locs = [str(x).strip() for x in j.get("locations") or [] if str(x).strip()]
            location = "; ".join(locs)
            out.append(Posting(
                company=company, title=title, location=location,
                remote=any("remote" in x.lower() for x in locs) or None,
                url=url, apply_url=url, ats=fam, ats_job_id=jid or sid,
                posted_at=_iso(posted), first_published=_iso(posted), last_updated=_iso(j.get("date_updated")),
                source_slug=slug or board.get("slug") or "simplify",
                raw={"simplify_id": sid, "category": j.get("category"), "sponsorship": j.get("sponsorship"),
                     "degrees": j.get("degrees") or [], "source_url": j.get("url"), "via": "simplify",
                     **({} if fam != "other" else {"needs_description": True})},
            ))
        return out


def drop_known(postings: list[Posting], history: dict[str, dict[str, Any]]) -> list[Posting]:
    """Drop listings the other adapters already found (same ATS job id, or same company + title in any location)
    and repeats inside the batch. `history` is Store.load_history(), read before this batch is recorded."""
    ids = {str(i) for e in history.values() for i in e.get("ats_job_ids") or []}
    roles = {k.rsplit("|", 1)[0] for k in history}
    out: list[Posting] = []
    for p in postings:
        role = history_key(p.company, p.title).rsplit("|", 1)[0]
        if p.ats != "other" and p.ats_job_id in ids or role in roles:
            continue
        roles.add(role)
        out.append(p)
    return out


def enrich(postings: list[Posting], log=print) -> list[Posting]:
    """Fill description (and close date, salary) for Greenhouse/Ashby/Lever listings from the ATS API, reusing the
    native adapters' parsers. A failed fetch drops the listing (it is retried next run) rather than storing an empty
    description score-job would refuse. ats "other" passes through, marked raw.needs_description."""
    from careeros.scout.ashby import API as ASHBY_API, AshbyAdapter
    from careeros.scout.greenhouse import API as GH_API, GreenhouseAdapter
    from careeros.scout.lever import API as LEVER_API, LeverAdapter

    ashby_boards: dict[str, dict[str, Posting] | None] = {}
    out: list[Posting] = []
    for p in postings:
        if p.ats == "other":
            out.append(p)
            continue
        board = {"company": p.company, "slug": p.source_slug}
        try:
            if p.ats == "greenhouse":
                j = get_json(f"{GH_API.format(slug=p.source_slug)}/{p.ats_job_id}", params={"content": "true"})
                full = GreenhouseAdapter().parse({"jobs": [j]}, board)[0]
            elif p.ats == "lever":
                j = get_json(f"{LEVER_API.format(slug=p.source_slug)}/{p.ats_job_id}", params={"mode": "json"})
                full = LeverAdapter().parse([j], board)[0]
            else:
                if p.source_slug not in ashby_boards:
                    data = get_json(ASHBY_API.format(slug=p.source_slug), params={"includeCompensation": "true"})
                    ashby_boards[p.source_slug] = {x.ats_job_id: x for x in AshbyAdapter().parse(data, board)}
                full = (ashby_boards[p.source_slug] or {})[p.ats_job_id]
        except Exception as e:  # noqa: BLE001 - one dead listing must not fail the board
            log(f"[scout] simplify: no description for {p.ats}/{p.source_slug}/{p.ats_job_id}, skipped: {type(e).__name__}")
            continue
        if not (full.description_text or "").strip():
            continue
        for f in ("description_html", "description_text", "closes_at", "departments", "salary_min", "salary_max", "salary_currency"):
            setattr(p, f, getattr(full, f))
        out.append(p)
    return out
