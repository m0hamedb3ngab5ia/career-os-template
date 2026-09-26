from __future__ import annotations

from typing import Any

from careeros.models import Posting
from careeros.scout.base import Adapter, get_json, guess_remote, html_to_text

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def _comp(j: dict[str, Any]) -> tuple[float | None, float | None, str | None]:
    comp = j.get("compensation") or {}
    summary = comp.get("summaryComponents") or []
    for c in summary:
        if (c.get("compensationType") or "").lower() == "salary":
            return c.get("minValue"), c.get("maxValue"), c.get("currencyCode")
    tiers = comp.get("compensationTiers") or []
    for t in tiers:
        for c in t.get("components") or []:
            if (c.get("compensationType") or "").lower() == "salary":
                return c.get("minValue"), c.get("maxValue"), c.get("currencyCode")
    return None, None, None


class AshbyAdapter(Adapter):
    ats = "ashby"

    def fetch(self, board: dict[str, Any]) -> list[Posting]:
        data = get_json(API.format(slug=board["slug"]), params={"includeCompensation": "true"})
        return self.parse(data, board)

    def parse(self, data: Any, board: dict[str, Any]) -> list[Posting]:
        out: list[Posting] = []
        for j in (data or {}).get("jobs") or []:
            loc = (j.get("location") or "").strip()
            secondary = [s.get("location") for s in j.get("secondaryLocations") or [] if s.get("location")]
            is_remote = j.get("isRemote")
            remote = bool(is_remote) if is_remote is not None else guess_remote(loc, j.get("workplaceType"))
            content_html = j.get("descriptionHtml") or ""
            smin, smax, cur = _comp(j)
            depts = [d for d in [j.get("department"), j.get("team")] if d]
            out.append(
                Posting(
                    company=board["company"],
                    title=(j.get("title") or "").strip(),
                    location=", ".join([loc, *secondary]) if secondary else loc,
                    remote=remote,
                    url=j.get("jobUrl") or "",
                    apply_url=j.get("applyUrl") or j.get("jobUrl") or "",
                    ats=self.ats,
                    ats_job_id=j.get("id"),
                    posted_at=j.get("publishedAt"),
                    first_published=j.get("publishedAt"),
                    last_updated=j.get("updatedAt"),
                    description_html=content_html,
                    description_text=j.get("descriptionPlain") or html_to_text(content_html),
                    departments=depts,
                    salary_min=smin,
                    salary_max=smax,
                    salary_currency=cur,
                    source_slug=board["slug"],
                    raw={
                        "employmentType": j.get("employmentType"),
                        "workplaceType": j.get("workplaceType"),
                        "address": j.get("address"),
                        "compensationTierSummary": (j.get("compensation") or {}).get("compensationTierSummary"),
                    },
                )
            )
        return out
