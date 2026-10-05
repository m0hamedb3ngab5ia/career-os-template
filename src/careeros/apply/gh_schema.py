"""Greenhouse application schema (boards API `?questions=true`) -> normalized fields -> fill_plan.json.

    data = fetch_questions("acme", "123")                   # or a recorded JSON (tests, --schema-json)
    plan = build_plan(normalize(data), profile=master_yaml, answers_path=..., company="Acme", files={...})

API field names are the DOM ids on job-boards.greenhouse.io, and field order is kept (the race select only
appears after hispanic_ethnicity is answered). Answers come only from profile identity/education,
standard_answers.yaml (`answer_for`) and its `eeo:` block (`select_eeo_option`). A select value is always an
exact option label from the schema; anything unanswered is `needs_review` with value null (legal/salary/EEO
are never guessed: source `pause:<kind>`, the caller raises an Action Item; essays go to the prepare skill).
A freetext field still empty takes the job's `answers.json` draft (`drafts`) as source `ai_draft`, `reviewed: false`
(REQ-105, DEC-010): fill refuses it until the user approves or edits it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from careeros.apply.questions import _label_matches, answer_for, classify_question, load_eeo_answers, select_eeo_option
from careeros.scout.base import get_json

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
_TYPES = {"input_text": "text", "textarea": "textarea", "input_file": "file", "input_hidden": "hidden",
          "multi_value_single_select": "select", "multi_value_multi_select": "multiselect"}
# Greenhouse compliance field name -> key in the standard_answers.yaml `eeo:` block
_EEO = {"gender": "gender", "hispanic_ethnicity": "hispanic_latino", "race": "race_ethnicity",
        "veteran_status": "veteran", "disability_status": "disability"}
_SELECTS = ("select", "multiselect", "checkbox_group")
_HISPANIC = {"field_id": "hispanic_ethnicity", "label": "Are you Hispanic/Latino?", "type": "select", "required": False,
             "options": ["Yes", "No", "Decline To Self Identify"]}


def fetch_questions(board: str, job_id: str) -> dict[str, Any]:
    return get_json(API.format(board=board, job_id=job_id), params={"questions": "true"})


def normalize(data: dict[str, Any]) -> list[dict[str, Any]]:
    qs = (list(data.get("questions") or [])
          + [q for c in data.get("compliance") or [] for q in c.get("questions") or []]
          + list(data.get("location_questions") or []))
    out: list[dict[str, Any]] = []
    for q in qs:
        fields = q.get("fields") or []
        if any(f.get("type") == "input_file" for f in fields):  # drop the "paste text instead" alternative
            fields = [f for f in fields if f.get("type") == "input_file"]
        for f in fields:
            if f["name"] == "location" and q in (data.get("location_questions") or []):
                continue  # job-boards renders it as the candidate-location autocomplete (_extras)
            if f["name"] == "race" and not any(x["field_id"] == "hispanic_ethnicity" for x in out):
                out.append(dict(_HISPANIC))  # the API folds it into race; job-boards asks it first
            t = _TYPES.get(f.get("type"), "text")
            if t == "multiselect" and f["name"].endswith("[]"):
                t = "checkbox_group"
            out.append({"field_id": f["name"], "label": re.sub(r"\s+", " ", q.get("label") or "").strip(),
                        "type": t, "required": bool(q.get("required")),
                        "options": [str(v.get("label")) for v in f.get("values") or []]})
    return out


def pick_option(options: list[str], answer: Any) -> str | None:
    """Exact label (case-insensitive), else the only whole-word prefix match; else None (ambiguous = review)."""
    if isinstance(answer, bool):
        answer = "Yes" if answer else "No"
    kinds = [(o, _label_matches(o, str(answer))) for o in options]
    prefix = [o for o, k in kinds if k == "prefix"]
    return next((o for o, k in kinds if k == "exact"), None) or (prefix[0] if len(prefix) == 1 else None)


def _identity(profile: dict[str, Any]) -> dict[str, Any]:
    i = profile.get("identity") or {}
    parts = str(i.get("name") or "").split()
    return {"first_name": parts[0] if parts else None, "last_name": parts[-1] if len(parts) > 1 else None,
            "email": i.get("email"), "phone": i.get("phone"), "location": i.get("location")}


def _extras(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Fields job-boards.greenhouse.io renders outside the API schema; only those the profile can fill."""
    i = profile.get("identity") or {}
    edu = (profile.get("education") or [{}])[0] or {}
    city = str(i.get("location") or "").split(",")[0].strip() or None
    start = str(edu.get("start") or "")[:4] or None
    disc = edu.get("discipline") or edu.get("major")
    combined = bool(edu.get("degree")) and not disc  # e.g. "BS Computer Science": never split it by guessing
    rows = [("country", "Country", "select", i.get("country"), False),
            ("candidate-location", "Location (City)", "select_async", city, False),
            ("school--0", "School", "select_async", edu.get("school"), False),
            ("degree--0", "Degree", "select_async", edu.get("degree"), combined),
            ("discipline--0", "Discipline", "select_async", disc, combined),
            ("start-year--0", "Start date year", "text", start, False)]
    return [{"field_id": fid, "label": label, "type": t, "value": v, "source": "profile" if v else None,
             "needs_review": rev} for fid, label, t, v, rev in rows if v or rev]


def _fill(f: dict[str, Any], ident: dict[str, Any], eeo: dict[str, Any], answers_path: Path, company: str,
          files: dict[str, Any]) -> tuple[Any, str | None]:
    fid, t = f["field_id"], f["type"]
    if t == "hidden":
        return None, None
    if t == "file":
        return files.get(fid), "file" if files.get(fid) else None
    if fid in ident:
        return ident[fid], "profile" if ident[fid] else None
    if fid in _EEO:
        return select_eeo_option(_EEO[fid], f["options"], eeo), "eeo"
    hit = answer_for(f["label"], answers_path, required=f["required"], company=company)
    if not hit or hit[1] is None:
        return None, None
    value = pick_option(f["options"], hit[1]) if t in _SELECTS else hit[1]
    if value is not None and t in ("multiselect", "checkbox_group"):
        value = [value]
    return value, f"standard:{hit[0]}"


def build_plan(fields: list[dict[str, Any]], *, profile: dict[str, Any], answers_path: str | Path,
               company: str = "", files: dict[str, Any], drafts: list[Any] | None = None) -> dict[str, Any]:
    ident, eeo, rows = _identity(profile), load_eeo_answers(answers_path), []
    for f in fields:
        value, source = _fill(f, ident, eeo, Path(answers_path), company, files)
        draft = None
        if value is None and f["type"] not in ("hidden", "file"):
            kind = classify_question(f["label"]) if f["field_id"] not in _EEO else "eeo"
            source = f"pause:{kind}" if kind in ("legal", "salary", "eeo", "sensitive") else "unanswered"
            if source == "unanswered" and f["type"] in ("text", "textarea"):  # never legal/salary/EEO/selects
                draft = _draft_for(f["label"], drafts or [])
        if draft:
            value, source = draft, "ai_draft"
        needs = (value is None or draft is not None) and f["type"] != "hidden" and (f["type"] != "file" or f["required"])
        row = {"field_id": f["field_id"], "label": f["label"], "type": f["type"], "value": value, "source": source,
               "needs_review": needs, "required": bool(f["required"])}
        if draft:
            row["reviewed"] = False
        if f["options"]:
            row["options"] = f["options"]
        rows.append(row)
    return {"fields": rows + _extras(profile), "files": files}


def _draft_for(label: str, drafts: list[Any]) -> str | None:
    """The answers.json answer whose question is this label (whitespace/case-insensitive), else None."""
    return next((str(d["answer"]).strip() for d in drafts if isinstance(d, dict) and str(d.get("answer") or "").strip()
                 and _label_matches(str(d.get("question") or ""), label) == "exact"), None)


def field_kind(f: dict[str, Any]) -> str:
    """What the field asks, from the field itself (never its current `source`, which an edit rewrites)."""
    return "eeo" if f["field_id"] in _EEO else classify_question(f["label"])


def carry_over(old: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    """Rebuild keeps this job's own edits and skips for fields that still exist (same field_id and type), and an
    approved AI draft's review while the draft text is unchanged."""
    mine = {f["field_id"]: f for f in (old or {}).get("fields", [])
            if f.get("source") == "user" or f.get("skipped") or (f.get("source") == "ai_draft" and f.get("reviewed"))}
    for f in new["fields"]:
        o = mine.get(f["field_id"])
        if not o or o.get("type") != f["type"] or f.get("source") == "pause:sensitive":
            continue
        if o.get("source") == "ai_draft" and not o.get("skipped"):
            if f.get("source") == "ai_draft" and f.get("value") == o.get("value"):
                f.update(reviewed=True, needs_review=False)
        else:
            f.update({k: o[k] for k in ("value", "source", "needs_review", "skipped") if k in o})
    return new
