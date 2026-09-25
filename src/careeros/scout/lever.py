from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from careeros.models import Posting
from careeros.scout.base import Adapter, get_json, guess_remote, html_to_text

API = "https://api.lever.co/v0/postings/{slug}"


def _ms_to_iso(ms: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError):
        return None


class LeverAdapter(Adapter):
    ats = "lever"

    def fetch(self, board: dict[str, Any]) -> list[Posting]:
        data = get_json(API.format(slug=board["slug"]), params={"mode": "json"})
        return self.parse(data, board)

    def parse(self, data: Any, board: dict[str, Any]) -> list[Posting]:
        out: list[Posting] = []
        for j in data or []:
            cats = j.get("categories") or {}
            loc = (cats.get("location") or "").strip()
            all_locs = cats.get("allLocations") or j.get("allLocations") or ([loc] if loc else [])
            workplace = (j.get("workplaceType") or "").lower()
            remote: bool | None = True if workplace == "remote" else (False if workplace in {"onsite", "on-site"} else guess_remote(*all_locs, loc))
            html_parts = [j.get("descriptionBody") or j.get("description") or ""]
            for lst in j.get("lists") or []:
                html_parts.append(f"<h3>{lst.get('text', '')}</h3>{lst.get('content', '')}")
            html_parts.append(j.get("additional") or "")
            content_html = "\n".join(p for p in html_parts if p)
            text_parts = [j.get("descriptionPlain") or html_to_text(j.get("description"))]
            for lst in j.get("lists") or []:
                text_parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}")
            text_parts.append(j.get("additionalPlain") or "")
            sal = j.get("salaryRange") or {}
            out.append(
                Posting(
                    company=board["company"],
                    title=(j.get("text") or "").strip(),
                    location=", ".join(all_locs) if len(all_locs) > 1 else loc,
                    remote=remote,
                    url=j.get("hostedUrl") or "",
                    apply_url=j.get("applyUrl") or j.get("hostedUrl") or "",
                    ats=self.ats,
                    ats_job_id=j.get("id"),
                    posted_at=_ms_to_iso(j.get("createdAt")),
                    description_html=content_html,
                    description_text="\n\n".join(p.strip() for p in text_parts if p and p.strip()),
                    departments=[d for d in [cats.get("department"), cats.get("team")] if d],
                    salary_min=sal.get("min"),
                    salary_max=sal.get("max"),
                    salary_currency=sal.get("currency"),
                    source_slug=board["slug"],
                    raw={"commitment": cats.get("commitment"), "workplaceType": workplace, "country": j.get("country")},
                )
            )
        return out
