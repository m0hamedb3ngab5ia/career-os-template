"""Ashby application form (jobs.ashbyhq.com non-user GraphQL `ApiJobPosting`) -> normalized fields -> fill_plan.json.

Same contract as gh_schema (it reuses its plan builder): field_id is the Ashby field path, which is also the
`data-field-path` of the field's wrapper on the page. Booleans are Yes/No buttons, so they take options
["Yes", "No"] and go through the shared standard-answer matching. The EEO survey is not in this schema: planned
as `eeo` rows (value = the standard_answers eeo key); the filler picks the matching radio on the page.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import requests

from careeros.apply import gh_schema
from careeros.apply.questions import load_eeo_answers

GRAPHQL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting"
_QUERY = ("query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) { "
          "jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: $jobPostingId) "
          "{ id title applicationForm { sections { title fieldEntries { ... on FormFieldEntry { isRequired field } } } } } }")
_TYPES = {"String": "text", "Email": "text", "Phone": "text", "Number": "text", "LongText": "textarea",
          "File": "file", "Boolean": "boolean", "Date": "date", "Location": "location",
          "ValueSelect": "select", "MultiValueSelect": "checkbox_group"}

_EEO = [("_systemfield_eeoc_gender", "Gender", "gender"), ("_systemfield_eeoc_race", "Race", "race_ethnicity"),
        ("_systemfield_eeoc_veteran_status", "Veteran Status", "veteran"),
        ("_systemfield_eeoc_disability_status", "Disability Status", "disability")]


def fetch_form(board: str, job_id: str) -> dict[str, Any]:
    r = requests.post(GRAPHQL, json={"operationName": "ApiJobPosting", "query": _QUERY,
                                     "variables": {"organizationHostedJobsPageName": board, "jobPostingId": job_id}},
                      timeout=30)
    r.raise_for_status()
    return r.json()


def normalize(data: dict[str, Any]) -> list[dict[str, Any]]:
    post = ((data.get("data") or {}).get("jobPosting"))
    if not post:
        raise ValueError("Ashby returned no jobPosting (closed or wrong board/job id)")
    out = []
    for sec in post["applicationForm"]["sections"]:
        for e in sec.get("fieldEntries") or []:
            f = e.get("field") or {}
            t = _TYPES.get(f.get("type"), "text")
            opts = ["Yes", "No"] if t == "boolean" else [str(v["label"]) for v in f.get("selectableValues") or []]
            out.append({"field_id": f["path"], "label": re.sub(r"\s+", " ", f.get("title") or "").strip(), "type": t,
                        "required": bool(e.get("isRequired")), "options": opts, "ashby_type": f.get("type")})
    return out


def _ident(fields: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    i = profile.get("identity") or {}
    by_path = {"_systemfield_name": i.get("name"), "_systemfield_email": i.get("email"),
               "_systemfield_location": i.get("location")}
    return {f["field_id"]: (i.get("phone") if f["ashby_type"] == "Phone" else by_path[f["field_id"]])
            for f in fields if f["ashby_type"] == "Phone" or f["field_id"] in by_path}


def build_plan(fields: list[dict[str, Any]], *, profile: dict[str, Any], answers_path: str | Path, company: str = "",
               files: dict[str, Any], drafts: list[Any] | None = None) -> dict[str, Any]:
    """gh_schema.build_plan with Ashby identity paths; the resume field takes files["resume"], a file field
    labelled "cover letter" takes files["cover_letter"]."""
    mapped = {}
    for f in fields:
        if f["type"] == "file":
            mapped[f["field_id"]] = files.get("cover_letter" if re.search(r"cover", f["label"], re.I) else "resume")
    plan = gh_schema.build_plan(fields, profile=profile, answers_path=answers_path, company=company, files=mapped,
                                drafts=drafts, ident=_ident(fields, profile), extras=False)
    eeo = load_eeo_answers(answers_path)
    plan["fields"] += [{"field_id": fid, "label": label, "type": "eeo", "value": key, "source": "eeo",
                        "needs_review": False, "required": False, "eeo": {key: eeo[key]}}
                       for fid, label, key in _EEO if key in eeo]
    plan["files"] = files
    return plan
