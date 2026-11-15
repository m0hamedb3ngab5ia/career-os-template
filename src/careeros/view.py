"""`careeros view`: data/views/status.html, a self-contained local snapshot from data already on disk (no AI, no
network): onboarding checklist (readiness items), pipeline counts + last run, applied history (newest first, 50)."""
from __future__ import annotations

import html
from collections import Counter
from pathlib import Path

from careeros import readiness
from careeros.config import get_settings
from careeros.runs.atomic import write_text
from careeros.store import Store

CAP = 50
CSS = """:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#ddd;--ok:#1a7f37;--todo:#b54708}
@media(prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mut:#999;--line:#333;--ok:#4ac26b;--todo:#f0a050}}
body{margin:0 auto;max-width:56rem;padding:1rem 16px;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
h2{margin-top:2rem;font-size:1.1rem}table{width:100%;border-collapse:collapse;display:block;overflow-x:auto}
td,th{text-align:left;padding:.3rem .6rem;border-bottom:1px solid var(--line)}.mut{color:var(--mut)}
.ok{color:var(--ok)}.todo{color:var(--todo)}"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _table(head: list[str], rows: list[list]) -> str:
    th = "".join(f"<th>{_e(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{th}</tr>{body}</table>"


def _applied_at(store: Store, jid: str, submitted: str | None) -> str:
    if submitted:
        return submitted[:10]
    hist = (store._read(jid, "status.json") or {}).get("history") or []
    return next((h["at"][:10] for h in reversed(hist) if h.get("status") == "applied" and h.get("at")), "")


def render(root: Path) -> str:
    s = get_settings(Path(root))
    store = Store(s)
    jobs = store.list_jobs()
    items = readiness.items(root)
    checklist = "<ul>" + "".join(
        f'<li class="{"ok" if i["done"] else "todo"}">{"done" if i["done"] else "todo"}: {_e(i["label"])}'
        f'{"" if i["must"] else " (optional)"}</li>' for i in items) + "</ul>"
    counts = Counter(j["status"] for j in jobs)
    try:
        from careeros.runs.status import status_data
        last = {k: v for k, v in status_data(s)["last"].items() if v}
    except Exception:  # a snapshot must render even with broken run state
        last = {}
    last_html = "".join(f'<p class="mut">last {_e(k)} run: {_e(v["id"])} {_e(v["state"])}, {_e(v.get("started_at"))}</p>'
                        for k, v in last.items()) or '<p class="mut">no runs yet</p>'
    applied = sorted(((_applied_at(store, j["job_id"], j.get("submitted_at")), j) for j in jobs
                      if j["status"] == "applied" or j.get("submitted_at")), key=lambda t: t[0], reverse=True)[:CAP]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>career-os status</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body>
<h1>career-os status</h1>
<h2>Onboarding checklist</h2>{checklist}
<h2>Pipeline</h2>{_table(["Status", "Jobs"], [[k, v] for k, v in sorted(counts.items())]) if counts else '<p class="mut">no jobs yet</p>'}{last_html}
<h2>Applied (newest first, max {CAP})</h2>{_table(["Company", "Title", "Applied", "Status"], [[j["company"], j["title"], d, j["status"]] for d, j in applied]) if applied else '<p class="mut">nothing applied yet</p>'}
</body></html>"""


def write(root: Path) -> Path:
    out = Path(root) / "data" / "views" / "status.html"
    write_text(out, render(root))
    return out
