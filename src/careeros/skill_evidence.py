"""Deterministic skill-evidence post-pass for score.json (score-job §4).

A `missing_skills` entry moves to `matched_skills` only when the skill itself, a `match.synonyms` spelling or a
`match.implies` term hits real profile text; the evidence id (`skills.<key>`, `skill_groups.<label>`,
`<entry id>.stack` or a bullet id) goes in `skill_evidence`. No hit, no credit. Implications are one way:
Kafka evidences "distributed systems", never the reverse. Then `skills_overlap`, `fit` and a low-fit skip
decision are recomputed with the score-job rubric (§5, §7).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from careeros.markup import strip_bold
from careeros.match import _hit
from careeros.qa import PLACEHOLDER_RE

REDECIDE = ("below_min_fit", "location_nonpreferred_low_fit")  # skips that a higher fit can undo


def sources(profile: dict[str, Any]) -> list[tuple[str, str]]:
    """(evidence id, text) for every profile place a skill may be evidenced, listed skills first."""
    out = [(f"skills.{k}", "\n".join(map(str, v))) for k, v in (profile.get("skills") or {}).items() if isinstance(v, list)]
    out += [(f"skill_groups.{g.get('label')}", "\n".join(map(str, g.get("items") or [])))
            for g in profile.get("skill_groups") or [] if isinstance(g, dict)]
    entries = [e for sec in ("experience", "projects", "leadership") for e in profile.get(sec) or [] if isinstance(e, dict)]
    out += [(f"{e.get('id')}.stack", "\n".join(map(str, e.get("stack") or []))) for e in entries if e.get("stack")]
    for e in entries:
        for b in e.get("bullets") or []:
            if not isinstance(b, dict) or not b.get("id") or b.get("placeholder") \
                    or PLACEHOLDER_RE.search(str(b.get("text", ""))):
                continue
            var = b.get("variants") or {}
            var = var.values() if isinstance(var, dict) else var
            out.append((str(b["id"]), strip_bold("\n".join([str(b.get("text", "")), *map(str, var)]))))
    return out


def credit(missing: list[str], profile: dict[str, Any], synonyms: dict[str, list[str]],
           implies: dict[str, list[str]]) -> dict[str, str]:
    """{skill: evidence id} for each missing skill the profile evidences (via synonyms/implications)."""
    imp = {str(k).lower().strip(): [str(x) for x in v or []] for k, v in (implies or {}).items()}
    src = sources(profile)
    out: dict[str, str] = {}
    for skill in missing:
        alts = [skill, *imp.get(skill.lower().strip(), [])]
        eid = next((i for i, text in src if any(_hit(a, text, synonyms or {}) for a in alts)), None)
        if eid:
            out[skill] = eid
    return out


def tier_for(fit: int, dream: bool, rules: list[dict[str, Any]] | None) -> str | None:
    """score-job §6: first matching `targets.tier_rules` entry wins (`company_in dream_list`, `fit >= N`)."""
    for r in rules or []:
        cond = str(r.get("if", "")).strip()
        m = re.fullmatch(r"fit\s*(>=|>)\s*(\d+)", cond)
        if (cond == "company_in dream_list" and dream) or (m and (fit >= int(m[2]) if m[1] == ">=" else fit > int(m[2]))):
            return r.get("tier")
    return None


def _and(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def apply(s: dict[str, Any], profile: dict[str, Any], synonyms: dict[str, list[str]],
          implies: dict[str, list[str]], thresholds: dict[str, Any],
          tier_rules: list[dict[str, Any]] | None = None, dream: bool = False) -> dict[str, Any]:
    """Credit evidenced missing skills in score dict `s` in place; recompute overlap, fit and a low-fit skip.
    The skip is re-decided under the current thresholds even when nothing is credited (a lowered
    min_fit_to_prepare applies to existing skips)."""
    old = {"old_fit": s.get("fit"), "old_decision": s.get("decision")}
    got = credit(list(s.get("missing_skills") or []), profile, synonyms, implies)
    req = list(s.get("required_skills") or [])
    s["matched_skills"] = list(s.get("matched_skills") or []) + list(got)
    s["missing_skills"] = [x for x in s.get("missing_skills") or [] if x not in got]
    s["skill_evidence"] = {**(s.get("skill_evidence") or {}), **got}
    fb = s.setdefault("fit_breakdown", {})
    if got and len(req) >= 3:
        new = round(40 * len(s["matched_skills"]) / len(req))
        s["fit"] = min(100, max(0, int(s.get("fit") or 0) - int(fb.get("skills_overlap") or 0) + new))
        fb["skills_overlap"] = new
        miss = s["missing_skills"]
        sent = f"Skills: {len(s['matched_skills'])} of {len(req)} required matched" + (f"; missing {_and(miss)}." if miss else ".")
        rs = s.get("fit_reasons") or []
        s["fit_reasons"] = [sent if str(r).startswith("Skills:") else r for r in rs] if any(
            str(r).startswith("Skills:") for r in rs) else [sent, *rs]
    if tier_rules:
        s["tier"] = tier_for(int(s["fit"]), dream, tier_rules)
    if s.get("decision") == "skip" and s.get("skip_reason") in REDECIDE and not s.get("hard_filter_fails"):
        fit, th = s["fit"], thresholds or {}
        if s["skip_reason"] == "location_nonpreferred_low_fit" and fit < th.get("min_fit_nonpreferred_location", 101):
            pass
        elif (s.get("tier") == "A" and fit >= th.get("tier_a_min_fit", 101)) or fit >= th.get("min_fit_to_prepare", 101):
            s["decision"], s["skip_reason"] = "prepare", None
        else:
            s["skip_reason"] = "below_min_fit"
    return {"credited": got, **old, "fit": s["fit"], "decision": s["decision"]}


def recredit(settings: Any, min_fit: int = 0, write: bool = False,
             job_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Run `apply` on low-fit skipped jobs (fit >= min_fit, no hard-filter fail). Dry run unless `write`:
    then score.json is rewritten and a job that flips to prepare goes back to `scored` for /prepare-job
    (which runs the company gate)."""
    m = settings.pipeline.get("match") or {}
    th = (settings.targets.get("thresholds") or {})
    rows = []
    for p in sorted(Path(settings.paths["jobs_dir"]).glob("*/score.json")):
        jid = p.parent.name
        if job_ids and jid not in job_ids:
            continue
        try:
            s = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if s.get("decision") != "skip" or s.get("skip_reason") not in REDECIDE or s.get("hard_filter_fails") \
                or int(s.get("fit") or 0) < min_fit:
            continue
        ch = apply(s, settings.profile, m.get("synonyms") or {}, m.get("implies") or {}, th,
                   settings.targets.get("tier_rules"), settings.is_dream(str(s.get("company") or "")))
        if not ch["credited"] and ch["decision"] == ch["old_decision"]:
            continue
        rows.append({"job_id": jid, **ch})
        if write:
            p.write_text(json.dumps(s, indent=2))
            if ch["decision"] == "prepare":
                from careeros.tracker import set_status_both
                set_status_both(settings, jid, "scored", note="recredit: evidenced skills or current thresholds re-decided the skip")
    return rows
