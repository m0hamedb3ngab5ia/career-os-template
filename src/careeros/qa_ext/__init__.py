"""Extended per-job QA checks; each module exposes check_<name>(ck: careeros.qa.Checker) -> None.

Shared helpers for reading outreach.json the same way in every check:

    outreach_data(ck)   -> {"drafts": [...], "followups": [...], ...} | None  (a bare JSON list is `drafts`)
    outreach_items(ck)  -> [(section, index, item)] for drafts[] then top-level followups[] (dict items only)
    outreach_texts(item) -> [(field, text)] for every text field the candidate sends
"""
from __future__ import annotations

from typing import Any

# outreach.json item fields that hold text the candidate sends (plus email.subject / email.body)
OUTREACH_TEXT_KEYS = ("linkedin_note", "linkedin_message", "followup_7d", "followup_14d", "message", "note",
                      "text", "body", "subject")
OUTREACH_SECTIONS = ("drafts", "followups")


def outreach_data(ck: Any) -> dict[str, Any] | None:
    """Parsed outreach.json normalized to an object (a bare list is read as `drafts`); None when missing,
    unparseable or neither an object nor a list."""
    data = ck.outreach
    if isinstance(data, list):
        return {"drafts": data}
    return data if isinstance(data, dict) else None


def outreach_items(ck: Any) -> list[tuple[str, int, dict[str, Any]]]:
    """(section, index, item) for every dict in `drafts[]` and the top-level `followups[]`."""
    data = outreach_data(ck) or {}
    out = []
    for section in OUTREACH_SECTIONS:
        items = data.get(section)
        for i, d in enumerate(items if isinstance(items, list) else []):
            if isinstance(d, dict):
                out.append((section, i, d))
    return out


def outreach_texts(item: dict[str, Any]) -> list[tuple[str, str]]:
    """(field, text) for each non-empty text field of one outreach item (`email.subject`, `email.body`, or
    `email` when it is a plain string)."""
    out = [(k, item[k]) for k in OUTREACH_TEXT_KEYS if isinstance(item.get(k), str) and item[k].strip()]
    email = item.get("email")
    if isinstance(email, dict):
        out += [(f"email.{k}", email[k]) for k in ("subject", "body")
                if isinstance(email.get(k), str) and email[k].strip()]
    elif isinstance(email, str) and email.strip():
        out.append(("email", email))
    # a draft's own follow-ups (`drafts[i].followups[j]`) are prose that goes out too
    nested = item.get("followups")
    for j, f in enumerate(nested if isinstance(nested, list) else []):
        if isinstance(f, dict):
            out += [(f"followups[{j}].{k}", t) for k, t in outreach_texts(f)]
        elif isinstance(f, str) and f.strip():
            out.append((f"followups[{j}]", f))
    return out
