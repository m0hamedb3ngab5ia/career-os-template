"""Résumé match score (REQ-111, REQ-115; DEC-003).

match = 100 * (0.7*req_cov + 0.2*pref_cov + 0.1*title_cov), weights renormalised over non-empty groups.
Skills come from the job's score.json (one LLM score per job); everything after that is deterministic, so every
résumé can be compared cheaply. Term hits use careeros.terms (same as QA) plus `pipeline.yaml: match.synonyms`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from careeros import resumes
from careeros.terms import term_hit

WEIGHTS = {"required": 0.7, "preferred": 0.2, "title": 0.1}
DEFAULT_MIN_MATCH = 70  # Q-015
_STOP = {"a", "an", "and", "at", "for", "in", "of", "on", "or", "the", "to", "with", "ii", "iii", "iv"}


def title_terms(title: str) -> list[str]:
    toks = (t.strip(".").lower() for t in re.findall(r"[A-Za-z0-9+#.]+", title or ""))
    return list(dict.fromkeys(t for t in toks if t and t not in _STOP))


def _hit(term: str, text: str, synonyms: dict[str, list[str]]) -> bool:
    t = term.lower().strip()
    alts = {t}
    for canon, syns in synonyms.items():
        group = {str(canon).lower(), *(str(s).lower() for s in syns or [])}
        if t in group:
            alts |= group
    return any(term_hit(a, text) for a in alts)


def score(text: str, required: list[str], preferred: list[str], title: str,
          synonyms: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """{score 0-100, groups: {required|preferred|title: {hit, missing}}, missing: skills not in the text}."""
    syn = synonyms or {}
    groups: dict[str, dict[str, list[str]]] = {}
    for name, terms in (("required", required), ("preferred", preferred), ("title", title_terms(title))):
        terms = list(dict.fromkeys(str(x).strip() for x in terms or [] if str(x).strip()))
        if name == "preferred":  # a skill in both lists counts (and is missing) once, as required
            req_l = {x.lower() for x in groups["required"]["hit"] + groups["required"]["missing"]}
            terms = [x for x in terms if x.lower() not in req_l]
        hits = [x for x in terms if _hit(x, text, syn)]
        groups[name] = {"hit": hits, "missing": [x for x in terms if x not in hits]}
    used = {k: w for k, w in WEIGHTS.items() if groups[k]["hit"] or groups[k]["missing"]}
    total = sum(used.values())
    s = sum(w * len(groups[k]["hit"]) / (len(groups[k]["hit"]) + len(groups[k]["missing"]))
            for k, w in used.items())
    return {"score": round(100 * s / total) if total else 0, "groups": groups,
            "missing": groups["required"]["missing"] + groups["preferred"]["missing"]}


def _json(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def matches(settings: Any, job_dir: Path, threshold: int | None = None) -> dict[str, Any]:
    """Every résumé (latest version) scored against the job, best first (REQ-115)."""
    sc, posting = _json(job_dir / "score.json"), _json(job_dir / "posting.json")
    req = sc.get("required_skills") or []
    pref = sc.get("preferred_skills") or sc.get("nice_to_have_skills") or []
    if threshold is None:
        threshold = int((settings.targets.get("thresholds") or {}).get("min_match", DEFAULT_MIN_MATCH))
    if not (req or pref):  # unscored job: a title-only score would be meaningless (PR #130)
        return {"job_id": job_dir.name, "threshold": threshold, "scored": False, "best": None, "resumes": [],
                "hint": f"job not scored yet: run `careeros run score --job {job_dir.name}`"}
    syn = (settings.pipeline.get("match") or {}).get("synonyms") or {}
    rows = []
    for r in resumes.list_resumes(settings.root):
        text = resumes.version(settings.root, r["rid"], r["latest"])["text"]
        m = score(text, req, pref, str(posting.get("title") or ""), syn)
        rows.append({"rid": r["rid"], "name": r["name"], "type": r["type"], "version": r["latest"], **m})
    rows.sort(key=lambda x: -x["score"])
    return {"job_id": job_dir.name, "threshold": threshold, "scored": True,
            "best": rows[0]["rid"] if rows else None, "resumes": rows, "hint": None}
