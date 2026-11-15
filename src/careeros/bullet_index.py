"""Deterministic bullet shortlist for tailor-resume: which master bullets evidence which posting keywords.

`pick` = greedy weighted set cover over non-placeholder master bullets (by id, never new text), inside the
one-page budget of tailor-resume step 2. Computed on the fly (milliseconds); no cache. Matchers are the QA ones:
`match._hit` (keyword_coverage terms + `pipeline.yaml: match.synonyms`) for posting keywords, `qa._skill_hit`
(exact edges, C != C++) for listed skills (skills_evidenced).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from careeros.markup import strip_bold
from careeros.match import _hit, _json
from careeros.qa import PLACEHOLDER_RE, _skill_hit

W_REQUIRED, W_PREFERRED, W_MENTIONED = 3.0, 1.0, 0.5  # mentioned = listed skill the posting names, not in score.json
W_STACK = 0.1  # entry stack names the keyword but the bullet does not: tie-break only, never coverage
MAX_EXPERIENCE, MAX_PROJECTS = 4, 3
MAX_BULLETS, MAX_WORDS = 14, 550  # tailor-resume "safe target" (default.tex, 0.5in margins, 10pt)
TAGGED_TARGET, TAGGED_CAP, OTHER_CAP, PROJECT_CAP = 3, 4, 2, 2
MIN_EXPERIENCE, MIN_PROJECT = 2, 1


def _variants(b: dict[str, Any]) -> dict[str, str]:
    v = b.get("variants") or {}
    vals = v if isinstance(v, dict) else {"v%d" % i: x for i, x in enumerate(v)}
    return {k: strip_bold(str(x)) for k, x in vals.items()}


def eligible(b: Any) -> bool:
    """Usable bullet: has an id, no placeholder marker, not `resume_default: false`."""
    return (isinstance(b, dict) and bool(b.get("id")) and not b.get("placeholder")
            and PLACEHOLDER_RE.search(str(b.get("text", ""))) is None and b.get("resume_default") is not False)


def skill_items(profile: dict[str, Any]) -> list[str]:
    """Listed skills a résumé may show (concept lists are not tools; skills_evidenced skips them too)."""
    sk = profile.get("skills") or {}
    out = [str(x) for k, v in sk.items() if not str(k).lower().startswith("concept") and isinstance(v, list) for x in v]
    for g in profile.get("skill_groups") or []:
        if isinstance(g, dict) and not str(g.get("label") or "").lower().startswith("concept"):
            out += [str(x) for x in g.get("items") or []]
    return list(dict.fromkeys(out))


def _parts(item: str) -> list[str]:
    return [p.strip() for p in re.split(r"[/(),]", item) if p.strip()] or [item.strip()]


def index(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """bullet id -> {section, entry, text, short, terms}: `terms` = profile skill/stack vocabulary the bullet's own
    text (text + variants) names. An entry `stack` is kept apart (`stack_terms`), it is not evidence of a bullet."""
    vocab = skill_items(profile)
    out: dict[str, dict[str, Any]] = {}
    for section in ("experience", "projects", "leadership"):
        for e in profile.get(section) or []:
            if not isinstance(e, dict):
                continue
            stack = [str(x) for x in e.get("stack") or []]
            for b in e.get("bullets") or []:
                if not eligible(b):
                    continue
                var = _variants(b)
                text = strip_bold(str(b.get("text", "")))
                blob = " ".join([text, *var.values()])
                names = dict.fromkeys(vocab + stack)
                out[b["id"]] = {"section": section, "entry": e.get("id"), "text": text, "short": var.get("short"),
                                "blob": blob, "terms": sorted(t for t in names if any(_skill_hit(p, blob) for p in _parts(t))),
                                "stack_terms": stack, "bullet": b}
    return out


def _words(s: str) -> int:
    return len(s.split())


def _posting_text(posting: dict[str, Any]) -> str:
    return f"{posting.get('title') or ''}\n{posting.get('description_text') or ''}".strip()


def _sort_start(e: dict[str, Any]) -> str:
    return str(e.get("start") or "")


def pick(settings: Any, job_dir: Path, max_bullets: int = MAX_BULLETS, max_words: int = MAX_WORDS) -> dict[str, Any]:
    profile = settings.profile or {}
    syn = (getattr(settings, "pipeline", None) or {}).get("match", {}).get("synonyms") or {}
    sc, posting = _json(job_dir / "score.json"), _json(job_dir / "posting.json")
    category = sc.get("category")
    req = list(dict.fromkeys(str(x).strip() for x in sc.get("required_skills") or [] if str(x).strip()))
    pref = [x for x in dict.fromkeys(str(x).strip() for x in (sc.get("preferred_skills") or sc.get("nice_to_have_skills")
            or []) if str(x).strip()) if x not in req]
    post = _posting_text(posting)
    low = {k.lower() for k in req + pref}
    mentioned = [s for s in skill_items(profile) if s.lower() not in low and any(_skill_hit(p, post) for p in _parts(s))]
    kws = {**{k: ("required", W_REQUIRED) for k in req}, **{k: ("preferred", W_PREFERRED) for k in pref},
           **{k: ("mentioned", W_MENTIONED) for k in mentioned}}

    def hits(kw: str, blob: str) -> bool:
        return _hit(kw, blob, syn) if kws[kw][0] != "mentioned" else any(_skill_hit(p, blob) for p in _parts(kw))

    idx = index(profile)
    cover = {bid: {k for k in kws if hits(k, r["blob"])} for bid, r in idx.items()}
    via_stack = {bid: {k for k in kws if k not in cover[bid] and any(_hit(k, s, syn) for s in r["stack_terms"])}
                 for bid, r in idx.items()}

    # --- entries: experience newest first (>=2 eligible bullets, max 4), projects by relevance (max 3) ---
    skipped, exp, projs = [], [], []
    for e in profile.get("experience") or []:
        if not isinstance(e, dict):
            continue
        n = sum(1 for b in e.get("bullets") or [] if b.get("id") in idx)
        (exp if n >= MIN_EXPERIENCE else skipped).append(e) if n else skipped.append(e)
    skipped = [{"id": e.get("id"), "reason": "fewer than 2 eligible bullets"} for e in skipped]
    exp.sort(key=_sort_start, reverse=True)
    exp = exp[:MAX_EXPERIENCE]
    newest = {}
    for e in exp:  # same-company roles stay adjacent, placed by the group's newest role
        newest.setdefault(str(e.get("company") or "").lower(), _sort_start(e))
    exp.sort(key=lambda e: (newest[str(e.get("company") or "").lower()], str(e.get("company") or "").lower(),
                            _sort_start(e)), reverse=True)

    def tagged(e: dict[str, Any]) -> bool:
        stack = [str(x) for x in e.get("stack") or []]
        return category in (e.get("tags") or []) or sum(any(_hit(k, s, syn) for s in stack) for k in req) >= 2

    def pin(e: dict[str, Any]) -> bool:
        return any(b.get("resume_pin") and b.get("id") in idx for b in e.get("bullets") or [])

    cand = [p for p in profile.get("projects") or [] if isinstance(p, dict) and any(b.get("id") in idx for b in p.get("bullets") or [])]
    def proj_cover(p: dict[str, Any]) -> float:  # weighted posting keywords any of the project's bullets names
        return -sum(kws[k][1] for k in set().union(*(cover[b["id"]] for b in p["bullets"] if b.get("id") in idx)))

    cand.sort(key=lambda p: (not pin(p), proj_cover(p), category not in (p.get("tags") or []), str(p.get("date") or "")[::-1]))
    projs = cand[:max(MAX_PROJECTS, sum(1 for p in cand if pin(p)))]

    entries = [(("experience"), e) for e in exp] + [("projects", p) for p in projs]
    chosen: dict[str, list[str]] = {e["id"]: [] for _, e in entries}
    covered: dict[str, str] = {}  # keyword -> first bullet id covering it

    def gain(bid: str) -> float:
        b = idx[bid]["bullet"]
        g = sum(kws[k][1] for k in cover[bid] if k not in covered)
        g += W_STACK * sum(kws[k][1] for k in via_stack[bid] if k not in covered)
        return g * (0.5 if b.get("weak") else 1.0)

    def rank(bid: str) -> tuple:
        b = idx[bid]["bullet"]
        return (gain(bid), bool(b.get("resume_default")), bool(b.get("metrics")), -list(idx).index(bid))

    def take(e: dict[str, Any], bid: str) -> None:
        chosen[e["id"]].append(bid)
        for k in cover[bid]:
            covered.setdefault(k, bid)

    def left(e: dict[str, Any]) -> list[str]:
        return [b["id"] for b in e.get("bullets") or [] if b.get("id") in idx and b["id"] not in chosen[e["id"]]]

    # pass 1: pins, a project's lead (first eligible) bullet, then minimums by best gain
    for sec, e in entries:
        for b in e.get("bullets") or []:
            if b.get("resume_pin") and b.get("id") in idx:
                take(e, b["id"])
        if sec == "projects" and not chosen[e["id"]]:
            take(e, left(e)[0])
    for sec, e in entries:
        minimum = MIN_EXPERIENCE if sec == "experience" else MIN_PROJECT
        while len(chosen[e["id"]]) < minimum and left(e):
            take(e, max(left(e), key=rank))
    # pass 2: global greedy while a bullet adds coverage; pass 3: pad tagged entries to their target (tie-break order)
    def cap(sec: str, e: dict[str, Any]) -> int:
        return max(PROJECT_CAP if sec == "projects" else TAGGED_CAP if tagged(e) else OTHER_CAP,
                   sum(1 for b in e.get("bullets") or [] if b.get("resume_pin") and b.get("id") in idx))

    def used() -> tuple[int, int]:
        ids = [b for v in chosen.values() for b in v]
        return len(ids), sum(_words(idx[b]["text"]) for b in ids)

    def fits(bid: str) -> bool:
        n, w = used()
        return n + 1 <= max_bullets and w + _words(idx[bid]["text"]) <= max_words

    for phase in (2, 3):
        while True:
            opts = [(sec, e, b) for sec, e in entries for b in left(e)
                    if len(chosen[e["id"]]) < (cap(sec, e) if phase == 2 else (TAGGED_TARGET if sec == "experience" and tagged(e) else 0))
                    and (phase == 3 or gain(b) > 0) and fits(b)]
            if not opts:
                break
            sec, e, b = max(opts, key=lambda o: rank(o[2]))
            take(e, b)

    # --- output; a variant.short stands in for text when the page budget is already over ---
    n, w = used()
    out_entries = []
    for sec, e in entries:
        rows = []
        for bid in chosen[e["id"]]:
            r = idx[bid]
            rows.append({"id": bid, "variant": "text", "words": _words(r["text"]), "covers": sorted(cover[bid], key=list(kws).index),
                         "short": r["short"]})
        out_entries.append({"section": sec, "id": e["id"], "name": e.get("company") or e.get("name") or e["id"], "bullets": rows})
    shown = " \n".join(idx[b]["blob"] for v in chosen.values() for b in v)
    unev = [s for s in skill_items(profile)
            if (asked := [p for p in _parts(s) if _skill_hit(p, post)]) and not any(_skill_hit(p, shown) for p in asked)]
    mn = sum(MIN_EXPERIENCE if s == "experience" else MIN_PROJECT for s, _ in entries)
    got = {g: [k for k, (grp, _) in kws.items() if grp == g and k in covered] for g in ("required", "preferred")}
    return {
        "job_id": job_dir.name, "category": category,
        "budget": {"max_bullets": max_bullets, "max_words": max_words, "min_overrun": max(0, n - max_bullets),
                   "min_overrun_words": max(0, w - max_words), "minimum_bullets": mn},
        "totals": {"bullets": n, "words": w, "experience_entries": len(exp), "projects": len(projs)},
        "entries": out_entries,
        "bullet_ids": [b["id"] for e in out_entries for b in e["bullets"]],
        "covered": got,
        "uncovered": {g: [k for k, (grp, _) in kws.items() if grp == g and k not in covered] for g in ("required", "preferred")},
        "required_coverage": round(len(got["required"]) / len(req), 3) if req else None,
        "skills_without_evidence": unev,
        "skipped_entries": skipped,
    }


def write(settings: Any, job_dir: Path, **kw: Any) -> dict[str, Any]:
    out = pick(settings, job_dir, **kw)
    (job_dir / "bullet_shortlist.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _txt_bullets(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if ln.lstrip().startswith(("-", "•")))


def compare(settings: Any, jobs_dir: Path) -> dict[str, Any]:
    """Required-keyword coverage by bullets: shortlist vs the existing résumé, for every job with a QA-passed résumé."""
    syn = (getattr(settings, "pipeline", None) or {}).get("match", {}).get("synonyms") or {}
    rows = []
    for d in sorted(p for p in jobs_dir.iterdir() if p.is_dir()):
        if not (_json(d / "qa.json").get("pass") and (d / "resume.txt").is_file() and (d / "score.json").is_file()):
            continue
        req = [str(x) for x in _json(d / "score.json").get("required_skills") or []]
        if not req:
            continue
        sl = pick(settings, d)
        text = _txt_bullets((d / "resume.txt").read_text(encoding="utf-8"))
        have = sum(_hit(k, text, syn) for k in req) / len(req)
        rows.append({"job_id": d.name, "required": len(req), "shortlist": sl["required_coverage"], "resume": round(have, 3),
                     "shortlist_bullets": sl["totals"]["bullets"], "resume_bullets": len(_txt_bullets(text).splitlines()),
                     "shortlist_only": [k for k in sl["covered"]["required"] if not _hit(k, text, syn)],
                     "resume_only": [k for k in req if _hit(k, text, syn) and k not in sl["covered"]["required"]]})
    avg = lambda k: round(sum(r[k] for r in rows) / len(rows), 3) if rows else None  # noqa: E731
    return {"jobs": rows, "mean_shortlist": avg("shortlist"), "mean_resume": avg("resume"),
            "shortlist_worse": [r["job_id"] for r in rows if r["shortlist"] < r["resume"]]}
