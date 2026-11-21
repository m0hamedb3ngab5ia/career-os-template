"""Import one posting by hand (REQ-153): `careeros job add <url>` and job-alert email items.

ATS links (Greenhouse, Lever, Ashby) reuse the scout adapters; any other page is stored as `ats: manual`.
Alert items (LinkedIn, Indeed) are stored from the email's own title, company and link: this module never
fetches those sites. Job ids come from `make_job_id`, the same as scout, so a posting scout already stored
(or a link added twice) is reported as `exists` and not stored again.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from careeros.config import Settings
from careeros.models import Posting
from careeros.scout import ADAPTERS
from careeros.scout.simplify import family_of
from careeros.scout.base import USER_AGENT, TIMEOUT, BoardNotFound, FetchError, html_to_text
from careeros.store import Store


class ImportError_(Exception):
    pass


def parse_url(url: str) -> tuple[str, str, str]:
    """(ats, slug, ats_job_id) for a known ATS link; ("manual", "", "") otherwise. Uses scout's `family_of`
    (Greenhouse board/embed/EU, Ashby, Lever incl. EU), plus Greenhouse custom-domain `?gh_jid=` links."""
    fam, slug, jid, _ = family_of(url)
    if fam != "other":
        return fam, slug, jid
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if host.endswith("joinhandshake.com"):
        return "handshake", "", ""
    gh = parse_qs(u.query).get("gh_jid")
    if gh and gh[0].isdigit():
        return "greenhouse", u.path.strip("/").split("/")[0], gh[0]
    return "manual", "", ""


def _get_html(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        raise ImportError_(f"could not fetch {url}: {e}") from e


def _store(settings: Settings, p: Posting) -> dict[str, Any]:
    st = Store(settings)
    row = {"job_id": p.job_id, "company": p.company, "title": p.title, "url": p.url}
    if st.exists(p.job_id):
        return {**row, "status": "exists"}
    st.save_posting(p)
    return {**row, "status": "added"}


def add_url(settings: Settings, url: str) -> dict[str, Any]:
    ats, slug, ats_id = parse_url(url)
    if ats == "handshake":
        raise ImportError_("Handshake pages need the signed-in browser: open it in the apply browser, "
                           "not here (nothing was fetched)")
    if ats == "manual":
        return _add_manual(settings, url)
    board = next((b for b in settings.boards if str(b.get("ats")).lower() == ats and b.get("slug") == slug), None)
    board = board or {"company": slug.replace("-", " ").title(), "ats": ats, "slug": slug}
    try:
        found = ADAPTERS[ats]().fetch(board)
    except BoardNotFound as e:
        raise ImportError_(f"{ats} board '{slug}' not found") from e
    except FetchError as e:
        raise ImportError_(str(e)) from e
    p = next((x for x in found if x.ats_job_id == ats_id), None)
    if not p:
        raise ImportError_(f"job {ats_id} not found on the {ats} board '{slug}' (closed or wrong link)")
    p.raw = {**p.raw, "source": "manual_add"}
    return _store(settings, p)


def _meta(html: str, prop: str) -> str:
    m = re.search(rf"<meta[^>]+(?:property|name)=['\"]{prop}['\"][^>]+content=['\"]([^'\"]*)['\"]", html, re.I)
    return m.group(1).strip() if m else ""


def _add_manual(settings: Settings, url: str) -> dict[str, Any]:
    html = _get_html(url)
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    page_title = html_to_text(m.group(1)) if m else ""
    title = _meta(html, "og:title") or re.split(r"\s[|\-–—]\s", page_title)[0] or url
    company = _meta(html, "og:site_name") or ((urlparse(url).hostname or "").removeprefix("www.").split(".")[0].title())
    p = Posting(company=company, title=title, url=url, apply_url=url, ats="manual",
                description_html=html, description_text=html_to_text(html), raw={"source": "manual_add"})
    return _store(settings, p)


def _alert_ref(url: str) -> tuple[str, str] | None:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if host.endswith("linkedin.com"):
        m = re.search(r"/jobs/view/(?:[^/?]*-)?(\d+)", u.path)
        return ("linkedin", m[1]) if m else None
    if host.endswith("indeed.com"):
        jk = parse_qs(u.query).get("jk") or parse_qs(u.query).get("vjk")
        return ("indeed", jk[0]) if jk else None
    if host.endswith("joinhandshake.com"):
        m = re.search(r"/(?:jobs|job-search)/(\d+)", u.path)
        return ("handshake", m[1]) if m else None
    return None


def add_alerts(settings: Settings, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Import [{title, company, url}] taken from LinkedIn/Indeed/Handshake alert emails. Nothing is fetched."""
    out: list[dict[str, Any]] = []
    for it in items:
        title, company, url = (str(it.get(k) or "").strip() for k in ("title", "company", "url"))
        if not (title and company and url):
            out.append({"status": "skipped", "reason": "needs title, company and url", "url": url})
            continue
        ref = _alert_ref(url)
        if ref:
            ats, ref_id = ref
            from careeros.scout.handshake import JOB_URL

            clean = {"linkedin": f"https://www.linkedin.com/jobs/view/{ref_id}",
                     "indeed": f"https://www.indeed.com/viewjob?jk={ref_id}",
                     "handshake": JOB_URL.format(id=ref_id)}[ats]
        else:
            ats, ref_id, clean = "manual", None, url
        p = Posting(company=company, title=title, url=clean, apply_url=clean, ats=ats, ats_job_id=ref_id,
                    raw={"source": "job_alert", "needs_description": True})
        out.append(_store(settings, p))
    return out


def describe(settings: Settings, job_id: str, text: str) -> dict[str, Any]:
    """Attach pasted posting text to a job (e.g. from an alert email) and clear `needs_description`.
    Saved through Store, so the injection scan runs on the new text."""
    st = Store(settings)
    p = st.load_posting(job_id)
    if not p:
        raise ImportError_(f"job {job_id} not found")
    text = text.strip()
    if not text:
        raise ImportError_("empty text: paste the posting text")
    p.description_text = text
    p.description_html = ""
    p.raw = {k: v for k, v in p.raw.items() if k != "needs_description"}
    st.save_posting(p)
    return {"job_id": job_id, "company": p.company, "title": p.title, "status": "described"}
