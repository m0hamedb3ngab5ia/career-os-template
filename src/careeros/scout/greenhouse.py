from __future__ import annotations

from typing import Any

from careeros.models import Posting
from careeros.scout.base import Adapter, get_json, guess_remote, html_to_text

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


class GreenhouseAdapter(Adapter):
    ats = "greenhouse"

    def fetch(self, board: dict[str, Any]) -> list[Posting]:
        data = get_json(API.format(slug=board["slug"]), params={"content": "true"})
        return self.parse(data, board)

    def parse(self, data: Any, board: dict[str, Any]) -> list[Posting]:
        out: list[Posting] = []
        for j in data.get("jobs") or []:
            loc = ((j.get("location") or {}).get("name") or "").strip()
            content_html = j.get("content") or ""
            depts = [d.get("name") for d in j.get("departments") or [] if d.get("name")]
            offices = [o.get("name") for o in j.get("offices") or [] if o.get("name")]
            meta = {m.get("name"): m.get("value") for m in j.get("metadata") or [] if m.get("name")}
            out.append(
                Posting(
                    company=board["company"],
                    title=(j.get("title") or "").strip(),
                    location=loc,
                    remote=guess_remote(loc, j.get("title")),
                    url=j.get("absolute_url") or "",
                    apply_url=j.get("absolute_url") or "",
                    ats=self.ats,
                    ats_job_id=str(j.get("id")) if j.get("id") is not None else None,
                    posted_at=j.get("first_published") or j.get("updated_at"),  # updated_at resets on edit
                    first_published=j.get("first_published"),
                    last_updated=j.get("updated_at"),
                    description_html=content_html,
                    description_text=html_to_text(content_html),
                    departments=depts,
                    source_slug=board["slug"],
                    raw={"offices": offices, "metadata": meta, "internal_job_id": j.get("internal_job_id"),
                         "application_deadline": j.get("application_deadline")},
                )
            )
        return self.with_close_date(out)
