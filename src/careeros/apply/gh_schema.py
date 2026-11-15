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

from careeros.apply.questions import _label_matches, answer_for, answer_prefer, classify_question, load_eeo_answers, select_eeo_option
from careeros.scout.base import get_json

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
_TYPES = {"input_text": "text", "textarea": "textarea", "input_file": "file", "input_hidden": "hidden",
          "multi_value_single_select": "select", "multi_value_multi_select": "multiselect"}
# Greenhouse compliance field name -> key in the standard_answers.yaml `eeo:` block
_EEO = {"gender": "gender", "hispanic_ethnicity": "hispanic_latino", "race": "race_ethnicity",
        "veteran_status": "veteran", "disability_status": "disability"}
_SELECTS = ("select", "multiselect", "checkbox_group", "boolean")
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


def _strict(options: list[str], answer: str) -> str | None:
    kinds = [(o, _label_matches(o, answer)) for o in options]
    prefix = [o for o, k in kinds if k == "prefix"]
    return next((o for o, k in kinds if k == "exact"), None) or (prefix[0] if len(prefix) == 1 else None)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


_NEGATIONS = {"no", "not", "never", "don", "doesn", "didn", "won", "cannot", "without", "non", "neither", "nor"}


def _subset(options: list[str], answer: str) -> str | None:
    """The only option holding every whole word of `answer` ("Career Site" -> "Acme's Career Site")."""
    w = _words(answer)  # an option adding "not"/"never" says the opposite: "I do not require sponsorship"
    hits = [o for o in options if w and w <= _words(o) and not (_words(o) - w) & _NEGATIONS]
    return hits[0] if len(hits) == 1 else None


def pick_option(options: list[str], answer: Any, prefer: list[str] | tuple[str, ...] = ()) -> str | None:
    """Exact label (case-insensitive), else the only whole-word prefix match, else each `prefer` keyword in order
    (same rules), else the only option containing all the answer's whole words; else None (ambiguous = review)."""
    if isinstance(answer, bool):
        answer = "Yes" if answer else "No"
    hit = _strict(options, str(answer))
    for kw in prefer:
        hit = hit or _strict(options, kw) or _subset(options, kw)
    return hit or _subset(options, str(answer))


_DEGREES = {"bachelor": "Bachelor's Degree", "master": "Master's Degree", "associate": "Associate's Degree",
            "phd": "Doctor of Philosophy (Ph.D.)", "doctor of philosophy": "Doctor of Philosophy (Ph.D.)"}
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]


def _degree_label(degree: str) -> str | None:
    v = degree.strip().lower().replace(".", "")
    return next((lab for k, lab in _DEGREES.items() if v.startswith(k)), None)


def _month(ym: Any) -> str | None:
    m = re.fullmatch(r"\d{4}-(\d{2})", str(ym or ""))
    return _MONTHS[int(m[1]) - 1] if m and 1 <= int(m[1]) <= 12 else None


def _phone_country(phone: Any) -> str | None:
    p = str(phone or "").strip()
    digits = re.sub(r"\D", "", p)
    return "United States" if p.startswith("+1") or (not p.startswith("+") and len(digits) == 10) else None


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
    end = str(edu.get("end") or "")[:4] or None
    raw_degree = str(edu.get("degree") or "")
    degree = _degree_label(raw_degree) or raw_degree or None
    disc = edu.get("discipline") or edu.get("major")  # a list = ordered fallback, first one offered wins
    if not disc and "," in raw_degree and _degree_label(raw_degree):  # "Bachelor of Engineering, Software Engineering"
        disc = raw_degree.split(",", 1)[1].strip() or None
    combined = bool(edu.get("degree")) and not disc  # e.g. "BS Computer Science": never split it by guessing
    country = i.get("country") or _phone_country(i.get("phone"))
    rows = [("country", "Country", "select", country, bool(i.get("phone")) and not country),
            ("candidate-location", "Location (City)", "select_async", city, False),
            ("school--0", "School", "select_async", edu.get("school"), False),
            ("degree--0", "Degree", "select_async", degree, combined),
            ("discipline--0", "Discipline", "select_async", disc, combined),
            ("start-month--0", "Start date month", "select", _month(edu.get("start")), False),
            ("start-year--0", "Start date year", "text", start, False),
            ("end-month--0", "End date month", "select", _month(edu.get("end")), False),
            ("end-year--0", "End date year", "text", end, False)]
    job = (profile.get("experience") or [{}])[0] or {}  # employment section (only some jobs show it)
    current = str(job.get("end") or "present").lower() in ("present", "current", "now")
    rows += [("company-name-0", "Company name", "text", job.get("company"), False),
             ("title-0", "Title", "text", job.get("title_form") or job.get("title"), False),
             ("start-date-month-0", "Start date month", "select", _month(job.get("start")), False),
             ("start-date-year-0", "Start date year", "text", str(job.get("start") or "")[:4] or None, False)]
    rows += ([("current-role-0_1", "Current role", "checkbox", True, False)] if current and job.get("company") else
             [("end-date-month-0", "End date month", "select", _month(job.get("end")), False),
              ("end-date-year-0", "End date year", "text", str(job.get("end") or "")[:4] or None, False)])
    return [{"field_id": fid, "label": label, "type": t, "value": v, "source": "profile" if v else None,
             "needs_review": rev} for fid, label, t, v, rev in rows if v or rev]


def _fill(f: dict[str, Any], ident: dict[str, Any], eeo: dict[str, Any], answers_path: Path, company: str,
          files: dict[str, Any]) -> tuple[Any, str | None]:
    fid, t = f["field_id"], f["type"]
    if t == "hidden":
        return None, None
    if t == "file":
        key = "transcript" if "transcript" in str(f.get("label")).lower() else fid
        return files.get(key), "file" if files.get(key) else None
    if fid in ident:
        return ident[fid], "profile" if ident[fid] else None
    if fid in _EEO:
        return select_eeo_option(_EEO[fid], f["options"], eeo), "eeo"
    hit = answer_for(f["label"], answers_path, required=f["required"], company=company)
    if not hit or hit[1] is None:
        return None, None
    value = pick_option(f["options"], hit[1], answer_prefer(f["label"], answers_path, company)) if t in _SELECTS else hit[1]
    if value is not None and t in ("multiselect", "checkbox_group"):
        value = [value]
    return value, f"standard:{hit[0]}"


def build_plan(fields: list[dict[str, Any]], *, profile: dict[str, Any], answers_path: str | Path,
               company: str = "", files: dict[str, Any], drafts: list[Any] | None = None,
               ident: dict[str, Any] | None = None, extras: bool = True) -> dict[str, Any]:
    """`ident` (field_id -> profile value) and `extras` (GH-only fields outside the schema) let other ATSs reuse this."""
    ident, eeo, rows = _identity(profile) if ident is None else ident, load_eeo_answers(answers_path), []
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
    return {"fields": rows + (_extras(profile) if extras else []), "files": files}


def _draft_for(label: str, drafts: list[Any]) -> str | None:
    """The answers.json answer whose question is this label (whitespace/case-insensitive), else None."""
    return next((d["answer"].strip() for d in drafts if isinstance(d, dict) and isinstance(d.get("answer"), str)
                 and d["answer"].strip() and d.get("class") not in ("sensitive", "salary_freeform", "unknown")
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
