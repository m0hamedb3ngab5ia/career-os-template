"""The candidate's 1st-degree LinkedIn network, matched against open jobs for referral asks.

Input is LinkedIn's own data export (Settings -> Data privacy -> Get a copy of your data -> Connections), which the
candidate downloads themselves: career-os never touches LinkedIn. Stored in gitignored `data/network.json`.
Companies match by `company_policy.Policy.company_key` (normalized name + `companies.yaml: company_caps` aliases).
"""
from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from careeros.config import Settings
from careeros.runs.atomic import write_json

_COLS = {"url": "URL", "email": "Email Address", "company": "Company", "position": "Position",
         "connected_on": "Connected On"}


def network_path(s: Settings) -> Path:
    return s.paths.get("network") or s.paths["jobs_dir"].parent / "network.json"


def parse_connections_csv(path: Path) -> list[dict[str, str]]:
    """Rows with a company. LinkedIn prefixes the header with a few notes lines; skip to `First Name,...`."""
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("First Name,")), None)
    if start is None:
        raise ValueError(f"{path.name}: no 'First Name,Last Name,...' header; is this LinkedIn's Connections.csv?")
    out = []
    for r in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        row = {k: (r.get(col) or "").strip() for k, col in _COLS.items()}
        if not row["company"]:
            continue
        name = f"{(r.get('First Name') or '').strip()} {(r.get('Last Name') or '').strip()}".strip()
        out.append({"name": name, **row})
    return out


def import_csv(s: Settings, path: Path) -> int:
    rows = parse_connections_csv(path)
    p = network_path(s)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, {"imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "source": path.name, "connections": rows})
    return len(rows)


def load_network(s: Settings) -> list[dict[str, str]]:
    p = network_path(s)
    return json.loads(p.read_text(encoding="utf-8"))["connections"] if p.exists() else []


def match_jobs(jobs: Iterable[dict[str, Any]], connections: Iterable[dict[str, str]],
               company_key: Callable[[str], str]) -> list[dict[str, Any]]:
    """Jobs with >= 1 connection at the same company, best fit first."""
    by_co: dict[str, list[dict[str, str]]] = {}
    for c in connections:
        by_co.setdefault(company_key(c["company"]), []).append(
            {"name": c["name"], "position": c.get("position", ""), "url": c.get("url", "")})
    out = [{**{k: j.get(k) for k in ("job_id", "company", "title", "status", "fit")},
            "connections": by_co[company_key(j["company"])]}
           for j in jobs if company_key(j.get("company") or "") in by_co]
    return sorted(out, key=lambda m: -(m["fit"] or 0))


def referral_action_text(m: dict[str, Any], cap: int = 3) -> str:
    people = [f"{c['name']} ({c['position']})" if c["position"] else c["name"] for c in m["connections"]]
    more = f" +{len(people) - cap} more" if len(people) > cap else ""
    return (f"referral: ask {', '.join(people[:cap])}{more} at {m['company']} for {m['title']}; "
            f"draft with /draft-outreach {m['job_id']}")
