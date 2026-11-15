"""`careeros view`: data/views/<tab>.html (Setup until done, then Documents; Jobs; Applications), self-contained local pages from data already on disk (no AI, no
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
CSS = """:root{--bg:#fff;--fg:#1a1a1a;--mut:#6b6b6b;--line:#e3e3e3;--ok:#1a7f37}
@media(prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mut:#9a9a9a;--line:#333;--ok:#4ac26b}}
body{margin:0 auto;max-width:44rem;padding:1rem 16px;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
h1{font-size:1.4rem}h2{margin-top:2rem;font-size:1.1rem}.mut{color:var(--mut)}
progress{width:100%;height:.5rem;accent-color:var(--ok)}
ul.check{list-style:none;padding:0;margin:.5rem 0;border:1px solid var(--line);border-radius:10px}
ul.check li{display:flex;gap:.7rem;padding:.65rem .9rem;border-top:1px solid var(--line)}ul.check li:first-child{border-top:0}
.box{flex:none;width:1.1rem;height:1.1rem;margin-top:.15rem;border:2px solid var(--mut);border-radius:50%;
display:grid;place-items:center;font-size:.7rem;color:#fff}
.done .box{background:var(--ok);border-color:var(--ok)}.done .what{color:var(--mut);text-decoration:line-through}
.hint{display:block;font-size:.88rem;color:var(--mut)}
table{width:100%;border-collapse:collapse;display:block;overflow-x:auto}
nav{display:flex;gap:.25rem;border-bottom:1px solid var(--line);margin-bottom:1rem}
nav a{padding:.5rem .8rem;color:var(--mut);text-decoration:none;border-bottom:2px solid transparent}
nav a[aria-current]{color:var(--fg);border-color:var(--fg);font-weight:600}
td,th{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--line)}th{font-weight:600;font-size:.85rem;color:var(--mut)}
.dot{display:inline-block;width:.5rem;height:.5rem;border-radius:50%;background:var(--mut);margin-right:.4rem}
.dot.ok{background:var(--ok)}.dot.need{background:#d1242f}.dot.off{opacity:.4}"""

# Plain words for the readiness items (doctor keeps its own labels): (what, how to do it in chat)
PLAIN = {
    "master_resume": ("Add your résumé", "Send Claude your résumé file."),
    "setup_clean": ("Replace the example profile with yours", "Tell Claude \"set me up\"."),
    "legal_answers": ("Answer the work authorization questions", "Claude asks once and saves your answers."),
    "salary_answer": ("Set your minimum salary", "Tell Claude the lowest base salary you'd take."),
    "claude": ("Install Claude Code", "Needed to tailor résumés and letters."),
    "resume_look_approved": ("Approve how your résumé looks", "Ask Claude to show it, then say \"looks good\"."),
    "master_synced": ("Confirm your résumé details", "Claude shows what it read from your résumé; say approve."),
    "writing_sample": ("Add a writing sample", "Makes cover letters sound like you."),
    "credentials": ("Save your job-site logins", "Lets forms be filled without signing in each time."),
    "eeo_answers": ("Answer the diversity questions", "Or tell Claude to always decline."),
}
STATUS = {"found": "Found", "scored": "Checked for fit", "queued": "Ready to apply", "needs_review": "Waiting for you",
          "applied": "Applied", "skipped": "Skipped", "rejected": "Rejected", "interview": "Interviewing",
          "screening": "Screening", "offer": "Offer", "confirmed": "Confirmed"}


RUN = {"scout": "job search", "score": "fit check", "prepare": "résumé prep", "apply": "apply run"}


def _plain(status: str) -> str:
    return STATUS.get(status, status.replace("_", " ").capitalize())


def _item(i: dict) -> str:
    what, hint = PLAIN.get(i["id"], (i["label"], ""))
    opt = "" if i["must"] else " (optional)"
    return (f'<li class="{"done" if i["done"] else "todo"}"><span class="box" aria-hidden="true">'
            f'{"✓" if i["done"] else ""}</span><span><span class="what">{_e(what)}{opt}</span>'
            f'{"" if i["done"] or not hint else f"<span class=hint>{_e(hint)}</span>"}</span></li>')


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _table(head: list[str], rows: list[list], raw: tuple[int, ...] = ()) -> str:
    """Cells are escaped, except column indexes in `raw` (already-built, escaped HTML)."""
    th = "".join(f"<th>{_e(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c if i in raw else _e(c)}</td>" for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    return f"<table><tr>{th}</tr>{body}</table>"


def _date(iso: object) -> str:
    """"2026-11-14..." -> "Nov 14, 2026" (absolute, easy to read)."""
    from datetime import date
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return ""
    return f"{d:%b} {d.day}, {d.year}"


def _dot(word: str, tone: str = "") -> str:
    """Status = dot + word. Colour only for "needs you" (red) and "done" (green), like Handshake."""
    return f'<span class="dot {tone}"></span>{_e(word)}'


TONE = {"needs_review": "need", "offer": "ok", "rejected": "off", "skipped": "off"}


def _applied_at(store: Store, jid: str, submitted: str | None) -> str:
    if submitted:
        return submitted[:10]
    hist = (store._read(jid, "status.json") or {}).get("history") or []
    return next((h["at"][:10] for h in reversed(hist) if h.get("status") == "applied" and h.get("at")), "")


NAMES = {"setup": "Setup", "documents": "Documents", "jobs": "Jobs", "applications": "Applications"}
KIND = {"master": "Master", "variant": "Variant", "tailored": "Tailored"}


def _page(active: str, tabs: list[str], body: str) -> str:
    nav = "".join(f'<a href="{k}.html"{" aria-current=page" if k == active else ""}>{NAMES[k]}</a>' for k in tabs)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{NAMES[active]} · job search</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body>
<nav>{nav}</nav>{body}</body></html>"""


def _documents(root: Path, jobs: list[dict]) -> str:
    """Handshake-style: one plain table, Name · Kind · Used for · Status · Date."""
    from careeros import master_sync, resumes

    rows = []
    for r in sorted(resumes.list_resumes(root), key=lambda r: (r["type"] != "master", r["name"].lower())):
        master = r["type"] == "master"
        ok = not master or master_sync.look_approved(root)
        rows.append((r["at"], [r["name"], KIND.get(r["type"], r["type"]),
                               "Every job" if master else (r.get("category") or "").replace("_", " ") or "",
                               _dot("Ready", "ok") if ok else _dot("Needs your OK", "need"), _date(r["at"])]))
    for j in jobs:
        jd = root / "data" / "jobs" / j["job_id"]
        f = next((jd / n for n in ("cover_letter.pdf", "cover_letter.md") if (jd / n).is_file()), None)
        if f:
            from datetime import datetime
            at = datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            rows.append((at, ["Cover letter", "Cover letter", f"{j['company']} – {j['title']}", _dot("Ready", "ok"),
                              _date(at)]))
    for p in sorted((root / "profile" / "voice" / "samples").glob("*")):
        if p.is_file() and not p.name.startswith("."):
            rows.append(("", [p.name, "Writing sample", "Cover letters", _dot("Ready", "ok"), ""]))
    try:
        from careeros.apply.questions import load_standard_answers
        n_ans = len(load_standard_answers(root / "profile" / "standard_answers.yaml"))
    except Exception:
        n_ans = 0
    if n_ans:
        rows.append(("", [f"Saved form answers ({n_ans})", "Answers", "Every application", _dot("Ready", "ok"), ""]))
    if not rows:
        return '<h1>Documents</h1><p class="mut">No documents yet. Send Claude your résumé file.</p>'
    table = _table(["Name", "Kind", "Used for", "Status", "Date"], [r for _, r in rows], raw=(3,))
    return f'<h1>Documents</h1>{table}<p class="mut">{len(rows)} documents</p>'


def _needs_you(s) -> str:
    try:
        from careeros.tracker import Tracker
        items = Tracker(settings=s).list_action_items(open_only=True)
    except Exception:  # no tracker yet: nothing to show
        return ""
    if not items:
        return '<p class="mut">Nothing needs you right now.</p>'
    li = "".join("<li><span>" + _e(it.get("What to do")) + (f' <span class="mut">({_e(it["Company"])})</span>'
                 if it.get("Company") else "") + "</span></li>" for it in items[:5])
    more = f'<p class="mut">And {len(items) - 5} more. Ask Claude "what needs me?"</p>' if len(items) > 5 else ""
    return f'<h2>Needs you ({len(items)})</h2><ul class="check">{li}</ul>{more}'


def render(root: Path) -> dict[str, str]:
    """{page: html} for the three tabs."""
    s = get_settings(Path(root))
    store = Store(s)
    jobs = store.list_jobs()
    items = readiness.items(root)
    n_done = sum(i["done"] for i in items)
    setup = (f'<h1>Getting set up</h1><p class="mut">{n_done} of {len(items)} done</p>'
             f'<progress value="{n_done}" max="{len(items)}"></progress>'
             f'<ul class="check">' + "".join(_item(i) for i in items) + "</ul>")
    counts = Counter(j["status"] for j in jobs)
    try:
        from careeros.runs.status import status_data
        last = {k: v for k, v in status_data(s)["last"].items() if v}
    except Exception:  # a snapshot must render even with broken run state
        last = {}
    last_html = "".join(f'<p class="mut">Last {_e(RUN.get(k, k))}: {_e(_date(v.get("started_at")))}, '
                        f'{_e(str(v["state"]).replace("_", " "))}</p>' for k, v in last.items())
    stages = (_table(["Stage", "Jobs"], [[_dot(_plain(k), TONE.get(k, '')), v] for k, v in sorted(counts.items())], raw=(0,)) if counts
              else '<p class="mut">No jobs yet. Ask Claude to find some.</p>')
    sent = ((_applied_at(store, j["job_id"], j.get("submitted_at")), j) for j in jobs)  # applied at some point
    applied = sorted(((d, j) for d, j in sent if d or j["status"] == "applied"), key=lambda t: t[0], reverse=True)[:CAP]
    apps = (_table(["Company", "Role", "Applied", "Status"],
                   [[j["company"], j["title"], _date(d), _dot(_plain(j["status"]), TONE.get(j["status"], ""))]
                    for d, j in applied], raw=(3,)) if applied
            else '<p class="mut">Nothing sent yet.</p>')
    first = "setup" if any(i["must"] and not i["done"] for i in items) else "documents"  # Setup shows until done
    tabs = [first, "jobs", "applications"]
    return {first: _page(first, tabs, setup if first == "setup" else _documents(Path(root), jobs)),
            "jobs": _page("jobs", tabs, f"<h1>Your jobs</h1>{_needs_you(s)}<h2>By stage</h2>{stages}{last_html}"),
            "applications": _page("applications", tabs,
                                  f'<h1>Applications</h1><p class="mut">Newest first, up to {CAP}.</p>{apps}')}


def write(root: Path) -> Path:
    """Write data/views/<tab>.html (Setup until its must-items are done, then Documents; Jobs; Applications) and
    return the first tab's page."""
    out = Path(root) / "data" / "views"
    pages = render(root)
    for name in NAMES:
        if name not in pages:
            (out / f"{name}.html").unlink(missing_ok=True)  # Setup goes away once done
    for name, page in pages.items():
        write_text(out / f"{name}.html", page)
    return out / f"{next(iter(pages))}.html"
