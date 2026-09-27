#!/usr/bin/env python3
"""One-off performance baseline for the browser UI (`careeros ui`). Not a CI suite: run it by hand.

  python scripts/ui_perf.py --synth 5000 --out /tmp/cos-perf        # fictional repo root with 5,000 jobs
  python scripts/ui_perf.py --root /tmp/cos-perf [--index X.db]      # time reindex, screens, watcher burst

--synth writes a fictional repo root in the real on-disk shape: config/ + profile/ copied from examples/, job
folders under data/jobs (posting/status/score/safety/qa, some contacts.json + outreach.json), run records under
the runs dir, and the tracker workbook via careeros.tracker. Companies are "Acme <n>", addresses example.com.

--root times: a full reindex into a fresh index file, the median of 5 GETs of each screen's first page through
FastAPI's TestClient, and (unless --no-burst) a 200-job-file burst through the real watcher (watchfiles ->
Watcher.handle -> Index.update_jobs) until the index reflects every change, plus the handler alone. The index goes
to --index (default: a temp file), never the root's data/. Without --no-burst the root is written to (the burst
rewrites 200 status.json files), so use --no-burst on any real data.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SCREENS = ("/api/jobs", "/api/pipeline", "/api/today", "/api/contacts", "/api/inbox", "/api/runs")
LIMITS_MS = {"screen": 1000, "reindex": 30_000, "burst": 5000}
FLOW = ["found", "scored", "queued", "prepared", "needs_review", "applied", "screening", "interview"]
# status -> weight: most jobs sit early in the funnel, a long tail reaches interviews
MIX = {"found": 30, "scored": 20, "skipped": 18, "queued": 8, "prepared": 3, "needs_review": 3, "applied": 9,
       "screening": 2, "interview": 1, "rejected": 4, "ghosted": 2}
TITLES = ("Backend Engineer", "Software Engineer I", "Platform Engineer", "New Grad Engineer", "Data Engineer",
          "Infrastructure Engineer", "Full Stack Engineer", "Site Reliability Engineer")


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _history(status: str, found: datetime) -> list[dict[str, Any]]:
    if status in ("skipped",):
        flow = ["found", "skipped"]
    elif status in ("rejected", "ghosted"):
        flow = FLOW[:FLOW.index("applied") + 1] + [status]
    else:
        flow = FLOW[:FLOW.index(status) + 1]
    return [{"status": st, "at": _iso(found + timedelta(hours=6 * i)), "note": None} for i, st in enumerate(flow)]


def _make_root(out: Path) -> Path:
    import yaml

    out.mkdir(parents=True, exist_ok=False)
    for name in ("config", "profile"):
        shutil.copytree(REPO / "examples" / name, out / name)
    pipeline = yaml.safe_load((out / "config" / "pipeline.yaml").read_text())
    pipeline.setdefault("paths", {})["tracker_xlsx"] = "data/JobTracker.xlsx"
    (out / "config" / "pipeline.yaml").write_text(yaml.safe_dump(pipeline, sort_keys=False))
    return out


def synth(n: int, out: Path, *, seed: int = 7, now: datetime | None = None) -> dict[str, Any]:
    """Write a fictional repo root with `n` jobs; returns {"root", "jobs", "statuses", "contacts", "outreach",
    "runs", "tracker_rows"}."""
    from careeros.config import Settings
    from careeros.models import Posting, Score
    from careeros.runs.store import RunStore
    from careeros.store import Store
    from careeros.tracker import Tracker, sync_all

    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    root = _make_root(Path(out))
    s = Settings.load(root)
    store = Store(s)
    statuses, n_contacts, n_outreach, ids = {}, 0, 0, []
    for i in range(n):
        company, title = f"Acme {i // 3}", TITLES[i % len(TITLES)]
        status = rng.choices(list(MIX), weights=list(MIX.values()))[0]
        found = now - timedelta(days=rng.randint(0, 120), hours=rng.randint(0, 23))
        p = Posting(company=company, title=title, location="New York, NY", ats="greenhouse", ats_job_id=f"synth-{i}",
                    url=f"https://boards.example.com/acme-{i}", fetched_at=_iso(found),
                    description_text=f"{title} at {company}. " + "Build and run services. " * 40)
        jid = p.job_id
        ids.append(jid)
        statuses[jid] = status
        store._write(jid, "posting.json", p.model_dump())
        hist = _history(status, found)
        store._write(jid, "status.json", {"status": status, "updated_at": hist[-1]["at"], "history": hist})
        store.append_log(jid, f"status -> {status}", component="synth")
        if status != "found":
            fit = rng.randint(30, 95)
            store.save_score(Score(job_id=jid, category="swe_backend", fit=fit,
                                   tier=rng.choice(["A", "B", "C"]), reasons=["synthetic"]))  # type: ignore[arg-type]
            store._write(jid, "safety.json", {"job_id": jid, "checked_at": _iso(found), "flags": [], "runs": [],
                                              "verdict": "skip" if status == "skipped" else "pass"})
        if status in ("prepared", "needs_review", "applied", "screening", "interview", "rejected", "ghosted"):
            store._write(jid, "qa.json", {"job_id": jid, "reviewed_at": _iso(found), "mean": 8.1, "pass": True,
                                          "deterministic": {"pass": True, "checks": []}, "fail_reasons": []})
            (store.job_dir(jid) / "resume.pdf").write_bytes(b"%PDF-1.4 synthetic\n")
            (store.job_dir(jid) / "cover_letter.md").write_text("Hi,\n\nSynthetic letter.\n", encoding="utf-8")
        if status in ("applied", "screening", "interview", "rejected", "ghosted") or i % 10 == 0:
            n_contacts += 1
            who = f"Contact {i}"
            email = f"contact{i}@example.com"
            (store.job_dir(jid) / "contacts.json").write_text(json.dumps({"job_id": jid, "company": company,
                "contacts": [{"name": who, "title": "Technical Recruiter", "role": "recruiter",
                              "linkedin": f"https://www.linkedin.com/in/example-{i}", "email": email,
                              "email_confidence": rng.choice(["verified", "low"]),
                              "linkedin_degree": rng.choice([None, 1, 2, 3]), "mutuals": rng.choice([None, 0, 2])}]}),
                encoding="utf-8")
            if status in ("applied", "screening", "interview"):
                n_outreach += 1
                (store.job_dir(jid) / "outreach.json").write_text(json.dumps({
                    "job_id": jid, "company": company, "drafted_at": hist[-1]["at"], "review_required": True,
                    "followups": [], "drafts": [{
                        "contact": who, "role": "recruiter", "to": email, "to_confidence": "verified",
                        "kind": "post_apply_outreach", "channel": "email", "sent": False, "auto_send": False,
                        "linkedin_note": f"Hi, I applied to the {title} role.", "linkedin_message": None,
                        "email": {"subject": f"{title} application",
                                  "body": "Hi,\n\nI applied this week. [SPECIFIC CONNECTION]\n\nThanks."}}]}),
                    encoding="utf-8")
    counts = sync_all(s)
    tr = Tracker(settings=s)
    for k in range(min(20, n)):
        tr.add_action_item(f"Synthetic task {k}", type="review", job_id=ids[k], company=f"Acme {k // 3}",
                           priority=rng.choice("HML"), needs="laptop")
    rs = RunStore(s)
    n_runs = max(1, min(40, n // 100))
    for r in range(n_runs):
        started = now - timedelta(hours=6 * (r + 1))
        run = rs.new_run(rng.choice(["score", "prepare"]), "schedule", {"preset": "small", "max_jobs": 5}, started)
        run.update({"status": "done", "stop_reason": "completed", "ended_at": _iso(started + timedelta(minutes=9)),
                    "duration_s": 540, "counters": {"attempted": 5, "ok": 4, "failed": 1}})
        rs.save_run(run)
        for a in range(5):
            rs.save_attempt(run["id"], {"n": a + 1, "job_id": rng.choice(ids), "outcome": "ok", "duration_s": 100,
                                        "session_id": f"sess-{r}-{a}", "detail": ""})
    return {"root": root, "jobs": len(ids), "statuses": statuses, "contacts": n_contacts, "outreach": n_outreach,
            "runs": n_runs, "tracker_rows": counts["synced"]}


# --- timings -------------------------------------------------------------------------------------------------

def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


def _screens(settings: Any, ix: Any, repeats: int = 5) -> dict[str, float]:
    from fastapi.testclient import TestClient

    from careeros.ui.app import create_app
    from careeros.ui.security import LOOPBACK

    app = create_app(settings, index=ix, allowed_hosts=LOOPBACK | {"testserver"},
                     static_dir=Path(tempfile.gettempdir()) / "careeros-perf-no-static")
    out = {}
    with TestClient(app) as c:
        for url in SCREENS:
            times = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                r = c.get(url)
                times.append(_ms(t0))
                if r.status_code != 200:
                    raise SystemExit(f"{url}: HTTP {r.status_code} {r.text[:200]}")
            out[url] = statistics.median(times)
    return out


def _bump(jobs_dir: Path, ids: list[str], status: str) -> list[Path]:
    paths = []
    for jid in ids:
        f = jobs_dir / jid / "status.json"
        d = json.loads(f.read_text())
        d["status"] = status
        d["updated_at"] = _iso(datetime.now(timezone.utc))
        f.write_text(json.dumps(d), encoding="utf-8")
        paths.append(f)
    return paths


def _reflected(ix: Any, ids: list[str], status: str) -> int:
    marks = ",".join("?" * len(ids))
    return ix.query(f"SELECT COUNT(*) AS n FROM jobs WHERE status = ? AND job_id IN ({marks})",
                    [status, *ids])[0]["n"]


def _burst(settings: Any, ix: Any, n: int = 200, timeout: float = 30.0) -> dict[str, float | None]:
    """Rewrite n status.json files; time (a) the real watcher until the index shows all n, (b) Watcher.handle."""
    from careeros.ui.events import Broker
    from careeros.ui.watch import Watcher

    jobs_dir = Path(settings.paths["jobs_dir"])
    ids = sorted(r["job_id"] for r in ix.query("SELECT job_id FROM jobs"))[:n]
    w = Watcher(settings, ix, Broker())
    w.start()
    time.sleep(1.0)                                  # let watchfiles arm before the burst
    try:
        t0 = time.perf_counter()
        _bump(jobs_dir, ids, "withdrawn")
        live = None
        while time.perf_counter() - t0 < timeout:
            if _reflected(ix, ids, "withdrawn") == len(ids):
                live = _ms(t0)
                break
            time.sleep(0.02)
    finally:
        w.stop()
    paths = _bump(jobs_dir, ids, "ghosted")
    t0 = time.perf_counter()
    w.handle(paths)
    handler = _ms(t0)
    assert _reflected(ix, ids, "ghosted") == len(ids)
    return {"watcher_ms": live, "handler_ms": handler, "files": float(len(ids))}


def measure(root: Path, index_path: Path | None = None, *, burst: bool = True) -> dict[str, Any]:
    from careeros.config import Settings
    from careeros.ui.index import Index

    settings = Settings.load(root)
    tmp = None
    if index_path is None:
        tmp = tempfile.TemporaryDirectory(prefix="careeros-perf-")
        index_path = Path(tmp.name) / "careeros.db"
    if Path(index_path).exists():
        Index.remove_files(Path(index_path))
    ix = Index(settings, path=Path(index_path))
    try:
        t0 = time.perf_counter()
        ix.rebuild()
        res: dict[str, Any] = {"jobs": ix.query("SELECT COUNT(*) AS n FROM jobs")[0]["n"], "reindex_ms": _ms(t0)}
        res["screens_ms"] = _screens(settings, ix)
        if burst:
            res["burst"] = _burst(settings, ix)
        return res
    finally:
        ix.close()
        if tmp:
            tmp.cleanup()


def table(res: dict[str, Any]) -> str:
    def row(name: str, ms: float | None, limit: int) -> str:
        v = "timeout" if ms is None else f"{ms:9.1f}"
        slow = "SLOW" if ms is None or ms > limit else "ok"
        return f"{name:<28}{v:>10} ms  {slow}"

    lines = [f"jobs indexed: {res['jobs']}", row("full reindex", res["reindex_ms"], LIMITS_MS["reindex"])]
    lines += [row(f"GET {u}", ms, LIMITS_MS["screen"]) for u, ms in res["screens_ms"].items()]
    if "burst" in res:
        b = res["burst"]
        lines.append(row(f"watcher, {int(b['files'])} changes", b["watcher_ms"], LIMITS_MS["burst"]))
        lines.append(row(f"handler, {int(b['files'])} changes", b["handler_ms"], LIMITS_MS["burst"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--synth", type=int, metavar="N", help="write a fictional root with N jobs to --out")
    ap.add_argument("--out", type=Path, help="where --synth writes (must not exist)")
    ap.add_argument("--root", type=Path, help="repo root to time")
    ap.add_argument("--index", type=Path, help="index file to build (default: a temp file)")
    ap.add_argument("--no-burst", action="store_true", help="skip the watcher burst (never writes to --root)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.synth is not None:
        if not a.out:
            ap.error("--synth needs --out")
        t0 = time.perf_counter()
        info = synth(a.synth, a.out)
        print(f"wrote {info['jobs']} jobs, {info['contacts']} contacts, {info['outreach']} outreach, "
              f"{info['runs']} runs to {info['root']} in {_ms(t0) / 1000:.1f} s")
    if a.root:
        if a.index and a.index.resolve().is_relative_to(a.root.resolve()):
            ap.error("--index must be outside --root")
        res = measure(a.root, a.index, burst=not a.no_burst)
        print(json.dumps(res, indent=2) if a.json else table(res))
    if a.synth is None and not a.root:
        ap.error("give --synth N --out DIR and/or --root DIR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
