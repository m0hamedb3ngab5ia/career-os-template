"""Handshake job search, read-only, through the signed-in apply browser (no stored cookies).

Board (companies.yaml):
  - {company: Handshake, ats: handshake, slug: handshake, queries: [software engineer, new grad software], pages: 3}

The candidate signs in to Handshake once in the apply browser (paths.apply_cdp, default 127.0.0.1:9223);
this adapter runs Handshake's own job-search GraphQL query from a page on that origin, so the session never
leaves the browser. It only searches: it never applies, saves, hides or messages.
"""
from __future__ import annotations

import time
from typing import Any

from careeros.models import Posting
from careeros.scout.base import Adapter, FetchError, html_to_text

ORIGIN = "https://app.joinhandshake.com"
JOB_URL = ORIGIN + "/job-search/{id}"
PAGE_SIZE = 25
PAUSE_S = 2.0  # between requests: a person-paced read, not a crawl

QUERY = """query JobSearchQuery($first: Int, $after: String, $input: JobSearchInput) {
  jobSearch(first: $first, after: $after, input: $input) {
    totalCount
    edges { node { job {
      id title createdAt expirationDate remote onSite hybrid description
      jobType { behaviorIdentifier }
      employmentType { behaviorIdentifier }
      locations { name country }
      salaryRange { min max currency paySchedule { behaviorIdentifier } }
      employer { id name }
    } } }
  }
}"""

_FETCH_JS = """async (body) => {
  const csrf = document.querySelector('meta[name=csrf-token]')?.content;
  const r = await fetch('/hs/graphql', {method: 'POST', credentials: 'include',
    headers: {'content-type': 'application/json', ...(csrf ? {'x-csrf-token': csrf} : {})}, body: JSON.stringify(body)});
  return {status: r.status, text: await r.text()};
}"""


def _salary(rng: dict[str, Any] | None) -> tuple[float | None, float | None, str | None]:
    """Handshake sends cents; only an annual salary counts as base pay."""
    if not rng or (rng.get("paySchedule") or {}).get("behaviorIdentifier") != "ANNUAL_SALARY":
        return None, None, None
    cents = lambda v: v / 100 if v else None  # noqa: E731
    return cents(rng.get("min")), cents(rng.get("max")), rng.get("currency")


class HandshakeAdapter(Adapter):
    ats = "handshake"

    def fetch(self, board: dict[str, Any]) -> list[Posting]:
        from careeros.apply.browser import cdp_url
        from careeros.config import get_settings

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise FetchError("handshake needs Playwright (the [fast-apply] extra)") from e
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(board.get("cdp") or cdp_url(get_settings()))
                page = browser.contexts[0].new_page()
                try:
                    edges = search(page, board.get("queries") or ["software engineer"], int(board.get("pages") or 3))
                finally:
                    page.close()
        except FetchError:
            raise
        except Exception as e:  # noqa: BLE001 - browser down, timeout, bad JSON
            raise FetchError(f"handshake: {type(e).__name__}: {e} (is the apply browser running?)") from e
        return self.parse({"data": {"jobSearch": {"edges": edges}}}, board)

    def parse(self, data: Any, board: dict[str, Any]) -> list[Posting]:
        out: list[Posting] = []
        seen: set[str] = set()
        for e in ((data or {}).get("data") or {}).get("jobSearch", {}).get("edges") or []:
            j = (e.get("node") or {}).get("job") or {}
            jid = str(j.get("id") or "")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            # Full-time jobs only: internships, co-ops, part-time and on-campus roles are out of scope.
            if (j.get("jobType") or {}).get("behaviorIdentifier") != "JOB":
                continue
            if (j.get("employmentType") or {}).get("behaviorIdentifier") != "FULL_TIME":
                continue
            locs = [loc.get("name") for loc in j.get("locations") or [] if loc.get("name")]
            mode = "remote" if j.get("remote") else "hybrid" if j.get("hybrid") else "onsite" if j.get("onSite") else ""
            smin, smax, cur = _salary(j.get("salaryRange"))
            desc = j.get("description") or ""
            url = JOB_URL.format(id=jid)
            out.append(Posting(
                company=((j.get("employer") or {}).get("name") or "").strip() or "Unknown employer",
                title=(j.get("title") or "").strip(),
                location="; ".join(locs),
                remote=bool(j.get("remote")),
                url=url,
                apply_url=url,
                ats=self.ats,
                ats_job_id=jid,
                posted_at=j.get("createdAt"),
                first_published=j.get("createdAt"),
                description_html=desc,
                description_text=html_to_text(desc),
                salary_min=smin,
                salary_max=smax,
                salary_currency=cur,
                closes_at=(j.get("expirationDate") or "")[:10] or None,  # Handshake's "Apply by" date
                source_slug=board.get("slug") or "handshake",
                raw={"workplaceType": mode, "expirationDate": j.get("expirationDate"),
                     "employer_id": (j.get("employer") or {}).get("id"),
                     "country": next((loc.get("country") for loc in j.get("locations") or [] if loc.get("country")), None)},
            ))
        return self.with_close_date(out)


SIGNED_OUT = "not signed in: sign in to Handshake in the apply browser, then rerun scout"


def search(page: Any, queries: list[str], pages: int) -> list[Any]:
    """Run each query for up to `pages` pages on a Playwright page in the signed-in browser; return raw edges."""
    import json

    page.goto(ORIGIN + "/explore", wait_until="domcontentloaded", timeout=60000)
    if "/login" in page.url or "/access" in page.url:
        raise FetchError(SIGNED_OUT)
    edges: list[Any] = []
    for q in queries:
        for n in range(pages):
            time.sleep(PAUSE_S)
            body = {"operationName": "JobSearchQuery", "query": QUERY, "variables": {
                "first": PAGE_SIZE, "after": _cursor(n * PAGE_SIZE),  # Handshake's own UI sends offset cursors
                "input": {"filter": {"query": q}, "sort": {"direction": "ASC", "field": "RELEVANCE"},
                          "channel": "NL_SEARCH_CHANNEL"}}}
            r = page.evaluate(_FETCH_JS, body)
            if r["status"] in (401, 403):
                raise FetchError(SIGNED_OUT)
            d = json.loads(r["text"])
            if d.get("errors"):
                raise FetchError(f"handshake graphql: {str(d['errors'])[:160]}")
            got = ((d.get("data") or {}).get("jobSearch") or {}).get("edges") or []
            edges += got
            if len(got) < PAGE_SIZE:
                break
    return edges


def _cursor(offset: int) -> str:
    import base64

    return base64.b64encode(str(offset).encode()).decode()
