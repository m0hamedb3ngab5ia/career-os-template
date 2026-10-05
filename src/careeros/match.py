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


# --- résumé pick before prepare-job (REQ-112, REQ-113, UC-011; DEC-007, DEC-008) -------------------------
DEFAULT_MIN_TWEAK_GAIN = 5
MAX_TWEAK_BULLETS = 3


def _master_bullets(settings: Any) -> dict[str, str]:
    from careeros.qa import ProfileIndex, _load_yaml

    idx = ProfileIndex(_load_yaml(settings.root / "profile" / "master.yaml"))
    return {bid: str(b.get("text") or "") for bid, b in idx.bullets.items() if not idx.is_placeholder(bid)}


def tweak_estimate(text: str, required: list[str], preferred: list[str], title: str,
                   synonyms: dict[str, list[str]], bullets: dict[str, str]) -> tuple[int, list[str]]:
    """Best score reachable by adding <= 3 master bullets (by id) to the résumé text, greedy.
    ponytail: counts additions only (a swap also drops a weaker bullet, which rarely costs coverage)."""
    cur, ids = text, []
    best = score(text, required, preferred, title, synonyms)["score"]
    for _ in range(MAX_TWEAK_BULLETS):
        cand = max(((score(cur + "\n" + t, required, preferred, title, synonyms)["score"], bid)
                    for bid, t in sorted(bullets.items()) if bid not in ids), default=None)
        if cand is None or cand[0] <= best:
            break
        best, cur = cand[0], cur + "\n" + bullets[cand[1]]
        ids.append(cand[1])
    return best, ids


def _vdir(settings: Any, rid: str, n: int) -> Path:
    return resumes._dir(settings.root, rid) / f"v{n}"


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _link(settings: Any, job_dir: Path, rid: str, v: dict[str, Any]) -> str:
    """Reuse: the chosen version becomes the job's résumé (resume.txt + resume.json, resume.pdf when known).
    Copies only from the version's own dir (ARCHITECTURE: tailored versions snapshot resume.json/pdf). A stale job
    resume.pdf/tex is removed when the version has no PDF. Returns sha256 of the written resume.txt (DEC-007)."""
    import shutil

    text = v["text"].rstrip() + "\n"
    (job_dir / "resume.txt").write_text(text, encoding="utf-8")
    for f in ("resume.pdf", "resume.tex"):
        (job_dir / f).unlink(missing_ok=True)
    vd = _vdir(settings, rid, v["n"])
    if (vd / "resume.json").exists():  # AI-tailored earlier: full QA needs its bullet ids
        shutil.copyfile(vd / "resume.json", job_dir / "resume.json")
    else:
        (job_dir / "resume.json").write_text(json.dumps(
            {"reused": {"rid": rid, "version": v["n"], "author": v.get("author")}}, indent=2) + "\n", encoding="utf-8")
    pdf = next((p for p in (vd / "resume.pdf", vd / "original.pdf") if p.exists()), None)
    if pdf:
        shutil.copyfile(pdf, job_dir / "resume.pdf")
    return _sha(text)


def pick(settings: Any, job_dir: Path, threshold: int | None = None) -> dict[str, Any]:
    """reuse (best >= threshold) | tweak (<= 3 master bullets gain >= min_tweak_gain and reach it) | tailor.
    Writes resume_choice.json; prepare-job obeys it. Unscored job -> tailor (the existing flow)."""
    m = matches(settings, job_dir, threshold)
    thr = m["threshold"]
    c: dict[str, Any] = {"job_id": job_dir.name, "threshold": thr, "scored": m["scored"]}
    if not m["scored"]:
        c.update(action="tailor", reason="job not scored: full tailor from master (existing flow)")
    elif not m["resumes"]:
        c.update(action="tailor", reason="no résumés stored: full tailor from master")
    else:
        b = m["resumes"][0]
        v = resumes.version(settings.root, b["rid"], b["version"])
        c.update(rid=b["rid"], version=b["version"], name=b["name"], author=v.get("author"), score=b["score"])
        if b["score"] >= thr:
            c.update(action="reuse", reason=f"best résumé {b['name']!r} scores {b['score']} >= {thr}")
            c["text_sha256"] = _link(settings, job_dir, b["rid"], v)
        else:
            sc, posting = _json(job_dir / "score.json"), _json(job_dir / "posting.json")
            gain_min = int((settings.targets.get("thresholds") or {}).get("min_tweak_gain", DEFAULT_MIN_TWEAK_GAIN))
            est, ids = tweak_estimate(v["text"], sc.get("required_skills") or [],
                                      sc.get("preferred_skills") or sc.get("nice_to_have_skills") or [],
                                      str(posting.get("title") or ""),
                                      (settings.pipeline.get("match") or {}).get("synonyms") or {},
                                      _master_bullets(settings))
            c["estimate"] = est
            has_ids = (_vdir(settings, b["rid"], b["version"]) / "resume.json").exists()  # user-authored: no ids
            if not has_ids:
                c.update(action="tailor", reason=f"best {b['score']} < {thr}; {b['name']!r} has no bullet ids "
                                                 "(user-authored), so no tweak base: full tailor")
            elif ids and est - b["score"] >= gain_min and est >= thr:
                c.update(action="tweak", add_bullet_ids=ids,
                         reason=f"best {b['score']} < {thr}; adding {len(ids)} master bullet(s) reaches {est}")
            else:
                c.update(action="tailor", reason=f"best {b['score']} < {thr}; tweak estimate {est} "
                                                 f"(gain {est - b['score']}, min {gain_min}) not enough: full tailor")
    (job_dir / "resume_choice.json").write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return c


def save_tailored(settings: Any, job_dir: Path, below_threshold: bool = False) -> dict[str, Any] | None:
    """After a tweak/tailor prepare: keep resume.txt as a `tailored` résumé of the job's category (DEC-008)."""
    c, txt = _json(job_dir / "resume_choice.json"), job_dir / "resume.txt"
    if c.get("action") not in ("tweak", "tailor") or not txt.exists():
        return None
    return resumes.add_tailored(settings.root, txt.read_text(encoding="utf-8"),
                                category=_json(job_dir / "score.json").get("category"), source=f"job:{job_dir.name}",
                                files={f: job_dir / f for f in ("resume.json", "resume.pdf")},
                                below_threshold=below_threshold)
