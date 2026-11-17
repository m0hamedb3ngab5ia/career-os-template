"""Why jobs were skipped and what would unlock the most of them. Read-only, suggest-only (no config writes)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

NEAR_MISS = 10  # fit within this many points under the prepare threshold
FLEX = {"location": ("location_nonpreferred", "location_blocked"), "years": ("yoe_gt_",), "salary": ("salary_below_min",)}


def _reason(s: dict[str, Any]) -> str:
    fails = s.get("hard_filter_fails") or []
    return fails[0] if fails else str(s.get("skip_reason") or "unknown")


def skip_insights(scores: list[dict[str, Any]], min_fit: float, credit: Callable[[list[str]], dict[str, str]],
                  top: int = 8) -> dict[str, Any]:
    """`credit(skills)` returns the skills master.yaml already evidences (synonyms/implications)."""
    skipped = [s for s in scores if s.get("decision") == "skip"]
    reasons = Counter(_reason(s) for s in skipped)
    near, tot, miss = Counter(), Counter(), Counter()
    for s in skipped:
        if s.get("skip_reason") != "below_min_fit" or s.get("fit") is None or not (min_fit - NEAR_MISS <= s["fit"] < min_fit):
            continue
        sk = list(set(s.get("missing_skills") or []))
        done = credit(sk)
        for k in sk:
            (miss if k in done else near)[k] += 1
    learnable = sorted(near, key=lambda k: (-near[k], k))[:top]
    flex = []
    for name, prefixes in FLEX.items():
        def in_f(r: str, prefixes=prefixes) -> bool:
            return any(r.startswith(p) for p in prefixes)
        hit = [s for s in skipped if any(in_f(r) for r in s.get("hard_filter_fails") or [])]
        if hit:
            flex.append({"filter": name, "blocked": len(hit),
                         "rescored": sum(1 for s in hit if all(in_f(r) for r in s["hard_filter_fails"]))})
    return {"skipped": len(skipped), "min_fit": min_fit,
            "reasons": [{"reason": r, "count": n} for r, n in reasons.most_common()],
            "skills": {"learnable": [{"skill": k, "near_miss": near[k]} for k in learnable],
                       "scorer_misses": [{"skill": k, "count": n} for k, n in miss.most_common(top)]},
            "flex": flex}


def load_scores(jobs_dir: Path) -> list[dict[str, Any]]:
    out = []
    for f in sorted(Path(jobs_dir).glob("*/score.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            continue
    return out
