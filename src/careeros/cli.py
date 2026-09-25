from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from careeros.bootstrap import EDIT_HINTS, InitError, copy_examples, link_private
from careeros.config import ConfigError, Settings, SetupError, find_repo_root, get_settings
from careeros.models import ACTION_NEEDS, ACTION_TYPES, STATUSES, TrackerRow
from careeros.scout import run_scout
from careeros.store import Store
from careeros.tracker import Tracker, parse_field_args


def _settings(args: argparse.Namespace) -> Settings:
    return get_settings(Path(args.root)) if getattr(args, "root", None) else get_settings()


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if getattr(args, "root", None) else find_repo_root()
    try:
        rep = link_private(root, Path(args.link)) if args.link else copy_examples(root)
    except InitError as e:
        print(f"init: {e}", file=sys.stderr)
        return 1
    for line in rep.lines():
        print(line)
    if args.link:
        print(f"\nprofile/ and config/ now live in {Path(args.link).expanduser().resolve()} (keep that repo private).")
        return 0
    if any(what == "copied" for _, what in rep.actions):
        print("\nExample candidate \"Alex Example\" copied. Replace it with your own data (lines marked # INSERT):")
        for path, what in EDIT_HINTS:
            print(f"  {path:<34} {what}")
        print("\nThen run `careeros doctor` until it shows no FAIL (walkthrough: docs/GETTING_STARTED.md).")
        print("Optional: personal notes for Claude in CLAUDE.local.md (gitignored). Then: careeros scout --sync")
    else:
        print("\nnothing copied; existing profile/ and config/ left untouched")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Setup checklist (see careeros.doctor). Exit 1 on any FAIL. Needs no setup itself."""
    from careeros.doctor import exit_code, format_report, run_doctor

    try:
        root = Path(args.root).resolve() if getattr(args, "root", None) else find_repo_root()
    except FileNotFoundError as e:
        print(f"  FAIL  setup                  {e}")
        return 1
    checks = run_doctor(root)
    out = format_report(checks, quiet=args.quiet, root=root)
    if out:
        print(out)
    return exit_code(checks)


def cmd_scout(args: argparse.Namespace) -> int:
    s = _settings(args)
    store = Store(s)
    summary = run_scout(s, store, only=args.only)
    t = summary.totals
    print()
    print(f"scout done: fetched={t['fetched']} new={t['new']} stored={t['stored']} "
          f"filtered(title={t['filtered_title']} location={t['filtered_location']} blocklist={t['filtered_blocklist']})")
    if summary.bad_slugs:
        print("\nbad slugs (404) — fix in config/companies.yaml:")
        for b in summary.bad_slugs:
            print(f"  - {b.company}: {b.ats}/{b.slug}")
    if summary.errors:
        print("\nerrors:")
        for b in summary.errors:
            print(f"  - {b.company}: {b.error}")
    if args.sync and t["stored"]:
        tr = Tracker(settings=s)
        rows = []
        for b in summary.boards:
            for jid in b.stored_ids:
                p = store.load_posting(jid)
                if p:
                    rows.append(TrackerRow.from_posting(p, folder=str(store.job_dir(jid))))
        counts = tr.upsert_jobs(rows)
        tr.set_config("last_scout", datetime.now().strftime("%Y-%m-%d %H:%M"))
        print(f"tracker: {counts}")
    return 0


def cmd_tracker_init(args: argparse.Namespace) -> int:
    s = _settings(args)
    tr = Tracker(settings=s)
    existed = tr.path.exists()
    tr.init(force=args.force)
    print(f"{'exists' if existed and not args.force else 'created'}: {tr.path}")
    return 0


def cmd_tracker_sync(args: argparse.Namespace) -> int:
    s = _settings(args)
    store = Store(s)
    tr = Tracker(settings=s)
    tr.init()
    rows = []
    for jid in store.iter_job_ids():
        p = store.load_posting(jid)
        if not p:
            continue
        row = TrackerRow.from_posting(p, store.load_score(jid), folder=str(store.job_dir(jid)))
        st = store.get_status(jid)
        if st:
            row.status = st  # type: ignore[assignment]
        rows.append(row)
    counts = tr.upsert_jobs(rows)
    n = counts.get("created", 0) + counts.get("updated", 0)
    jobs = store.list_jobs()
    tr.set_config("last_sync", datetime.now().strftime("%Y-%m-%d %H:%M"))
    tr.set_config("jobs_count", len(jobs))
    tr.set_config("applied_count", sum(1 for j in jobs if j["status"] == "applied"))
    pend = tr.pending_count()
    print(f"synced {n} jobs -> {tr.path}" + (f" ({pend} ops queued, file locked)" if pend else ""))
    return 0


def cmd_tracker_flush(args: argparse.Namespace) -> int:
    tr = Tracker(settings=_settings(args))
    print(f"flushed {tr.flush_pending()} queued ops; {tr.pending_count()} remaining")
    return 0


def cmd_tracker_applied_count(args: argparse.Namespace) -> int:
    """Applications (DateApplied within --days) to <company>, or to all companies when omitted; 0 without a tracker."""
    tr = Tracker(settings=_settings(args))
    print(tr.applied_count(args.company, days=args.days) if tr.path.exists() else 0)
    return 0


def cmd_tracker_show(args: argparse.Namespace) -> int:
    """One Jobs row as JSON (header -> value), or `null` when there is no tracker or no such row."""
    tr = Tracker(settings=_settings(args))
    row = tr.get_job(args.job_id) if tr.path.exists() else None
    print(json.dumps(row, default=str))
    return 0


def cmd_tracker_upsert(args: argparse.Namespace) -> int:
    try:
        data = parse_field_args(args.field or [])
    except ValueError as e:
        print(f"tracker upsert: {e}", file=sys.stderr)
        return 2
    if not data:
        print("tracker upsert: give at least one --field key=value", file=sys.stderr)
        return 2
    s = _settings(args)
    if "status" in data:  # keep status.json in step, or the next `tracker sync` reverts the row
        store = Store(s)
        if store.exists(args.job_id):
            store.set_status(args.job_id, data["status"], "via tracker upsert")
    tr = Tracker(settings=s)
    res = tr.upsert_job({"job_id": args.job_id, **data})
    print(f"{args.job_id}: {res} ({', '.join(sorted(data))})")
    return 0


def cmd_jobs_list(args: argparse.Namespace) -> int:
    store = Store(_settings(args))
    jobs = store.list_jobs(args.status)
    if args.json:
        print(json.dumps(jobs, indent=2))
        return 0
    if not jobs:
        print("no jobs" + (f" with status={args.status}" if args.status else ""))
        return 0
    print(f"{'id':<12} {'status':<13} {'fit':>3} {'company':<20} {'title':<45} location")
    for j in jobs:
        fit = "" if j["fit"] is None else str(j["fit"])
        print(f"{j['job_id']:<12} {j['status']:<13} {fit:>3} {j['company'][:20]:<20} {j['title'][:45]:<45} {j['location'][:30]}")
    print(f"\n{len(jobs)} jobs")
    return 0


def cmd_job_show(args: argparse.Namespace) -> int:
    store = Store(_settings(args))
    p = store.load_posting(args.job_id)
    if not p:
        print(f"job {args.job_id} not found", file=sys.stderr)
        return 1
    print(f"{p.company} — {p.title}")
    print(f"id: {p.job_id}   status: {store.get_status(p.job_id) or 'found'}   ats: {p.ats}/{p.source_slug}")
    print(f"location: {p.location or '?'}   remote: {p.remote}   posted: {p.posted_at or '?'}")
    if p.salary_min or p.salary_max:
        print(f"salary: {p.salary_min} - {p.salary_max} {p.salary_currency or ''}")
    if p.departments:
        print(f"departments: {', '.join(p.departments)}")
    print(f"url: {p.url}")
    print(f"dir: {store.job_dir(p.job_id)}")
    sc = store.load_score(p.job_id)
    if sc:
        print(f"score: category={sc.category} fit={sc.fit} tier={sc.tier} fails={sc.hard_filter_fails}")
    if args.full:
        print("\n" + p.description_text)
    else:
        print("\n" + p.description_text[:800] + ("..." if len(p.description_text) > 800 else ""))
    log = store.read_log(p.job_id)
    if log:
        print("\nlog:\n" + log.rstrip())
    return 0


def cmd_action_add(args: argparse.Namespace) -> int:
    s = _settings(args)
    tr = Tracker(settings=s)
    company, role = args.company or "", args.role or ""
    if args.job and not (company and role):
        p = Store(s).load_posting(args.job)
        if p:
            company, role = company or p.company, role or p.title
    if getattr(args, "dedupe", False):
        for it in tr.list_action_items(open_only=True):
            if str(it.get("JobID") or "") == (args.job or "") and str(it.get("Type") or "") == args.type:
                print(f"action item {it.get('ID')} already open ({args.type}, job {args.job or '-'}); not added")
                return 0
    aid = tr.add_action_item(what=args.what, type=args.type, job_id=args.job or "", company=company,
                             role=role, link=args.link or "", priority=args.priority, needs=args.needs)
    print(f"action item {aid} added ({args.type}/{args.priority}/{args.needs})")
    return 0


def cmd_job_status(args: argparse.Namespace) -> int:
    """Set a job's status in both data/jobs/<id>/status.json and the tracker row."""
    s = _settings(args)
    store = Store(s)
    if not store.exists(args.job_id):
        print(f"job {args.job_id} not found", file=sys.stderr)
        return 1
    store.set_status(args.job_id, args.status, args.note)
    tr = Tracker(settings=s)
    tr.set_status(args.job_id, args.status, args.note)
    pend = tr.pending_count()
    print(f"{args.job_id}: status -> {args.status}" + (f" (tracker op queued, file locked)" if pend else ""))
    return 0


def cmd_action_list(args: argparse.Namespace) -> int:
    tr = Tracker(settings=_settings(args))
    items = tr.list_action_items(open_only=not args.all)
    if not items:
        print("no open action items")
        return 0
    for it in items:
        print(f"[{it['ID']}] {it['Priority']} {it['Type']:<15} {(it.get('Needs') or 'anytime'):<8} {it['Company'] or '':<18} {it['What to do']}")
    return 0


def cmd_action_done(args: argparse.Namespace) -> int:
    tr = Tracker(settings=_settings(args))
    ok = tr.mark_action_done(args.id)
    if ok is None:
        print(f"action item {args.id}: queued (tracker locked); run `careeros tracker flush`")
        return 0
    print("done" if ok else f"action item {args.id} not found")
    return 0 if ok else 1


def cmd_stats(args: argparse.Namespace) -> int:
    s = _settings(args)
    store = Store(s)
    jobs = store.list_jobs()
    print(f"jobs in data: {len(jobs)}   seen ids: {len(store.load_seen())}")
    by_status = Counter(j["status"] for j in jobs)
    print("by status: " + ", ".join(f"{k}={v}" for k, v in sorted(by_status.items(), key=lambda kv: STATUSES.index(kv[0]) if kv[0] in STATUSES else 99)))
    by_company = Counter(j["company"] for j in jobs)
    print("top companies: " + ", ".join(f"{k}={v}" for k, v in by_company.most_common(10)))
    by_cat = Counter(j["category"] or "unscored" for j in jobs)
    print("by category: " + ", ".join(f"{k}={v}" for k, v in by_cat.most_common()))
    tr = Tracker(settings=s)
    if tr.path.exists():
        cfg = tr.get_config()
        print(f"tracker: {tr.path}  rows={len(tr.list_jobs())}  open actions={len(tr.list_action_items())}  "
              f"last_scout={cfg.get('last_scout') or '-'}  last_sync={cfg.get('last_sync') or '-'}"
              + (f"  QUEUED={tr.pending_count()}" if tr.pending_count() else ""))
    else:
        print(f"tracker: not created ({tr.path}); run `careeros tracker init`")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="careeros", description="career-os job-search automation")
    p.add_argument("--root", help="repo root (default: auto-detect)")
    sub = p.add_subparsers(dest="cmd", required=True)

    it = sub.add_parser("init", help="create profile/ and config/ (copy examples, or --link your private dir)")
    it.add_argument("--link", metavar="DIR", help="symlink profile/, config/ (and CLAUDE.local.md) from DIR instead of copying")
    it.set_defaults(fn=cmd_init)

    dr = sub.add_parser("doctor", help="check setup: files, example data left, tools (exit 1 on any FAIL)")
    dr.add_argument("--quiet", action="store_true", help="print only FAIL lines (nothing when all good)")
    dr.set_defaults(fn=cmd_doctor)

    sc = sub.add_parser("scout", help="fetch postings from configured boards")
    sc.add_argument("--only", nargs="*", help="limit to company names or slugs")
    sc.add_argument("--sync", action="store_true", help="upsert new postings into tracker")
    sc.set_defaults(fn=cmd_scout)

    tr = sub.add_parser("tracker", help="JobTracker.xlsx ops")
    trs = tr.add_subparsers(dest="tracker_cmd", required=True)
    ti = trs.add_parser("init")
    ti.add_argument("--force", action="store_true")
    ti.set_defaults(fn=cmd_tracker_init)
    trs.add_parser("sync").set_defaults(fn=cmd_tracker_sync)
    trs.add_parser("flush").set_defaults(fn=cmd_tracker_flush)
    tac = trs.add_parser("applied-count", help="applications within --days to a company (or all); prints an integer")
    tac.add_argument("company", nargs="?", help="company name (normalized match); omit for all companies")
    tac.add_argument("--days", type=int, default=90)
    tac.set_defaults(fn=cmd_tracker_applied_count)
    tsh = trs.add_parser("show", help="one Jobs row as JSON (e.g. the Override column); null if absent")
    tsh.add_argument("job_id")
    tsh.add_argument("--json", action="store_true", help="JSON output (the only format)")
    tsh.set_defaults(fn=cmd_tracker_show)
    tup = trs.add_parser("upsert", help="create/update one Jobs row: --field Header=value (repeatable)")
    tup.add_argument("job_id")
    tup.add_argument("--field", action="append", metavar="KEY=VALUE",
                     help="column header or snake_case key, e.g. DateApplied=today Status=applied ATS=greenhouse")
    tup.set_defaults(fn=cmd_tracker_upsert)

    jobs = sub.add_parser("jobs")
    js = jobs.add_subparsers(dest="jobs_cmd", required=True)
    jl = js.add_parser("list")
    jl.add_argument("--status", choices=STATUSES)
    jl.add_argument("--json", action="store_true")
    jl.set_defaults(fn=cmd_jobs_list)

    job = sub.add_parser("job")
    jbs = job.add_subparsers(dest="job_cmd", required=True)
    jsh = jbs.add_parser("show")
    jsh.add_argument("job_id")
    jsh.add_argument("--full", action="store_true")
    jsh.set_defaults(fn=cmd_job_show)
    jst = jbs.add_parser("status", help="set status in status.json and the tracker row")
    jst.add_argument("job_id")
    jst.add_argument("status", choices=STATUSES)
    jst.add_argument("--note")
    jst.set_defaults(fn=cmd_job_status)

    act = sub.add_parser("action")
    acs = act.add_subparsers(dest="action_cmd", required=True)
    aa = acs.add_parser("add")
    aa.add_argument("what")
    aa.add_argument("--type", choices=ACTION_TYPES, default="other")
    aa.add_argument("--job")
    aa.add_argument("--company")
    aa.add_argument("--role")
    aa.add_argument("--link")
    aa.add_argument("--priority", choices=["H", "M", "L"], default="M")
    aa.add_argument("--needs", choices=ACTION_NEEDS, default="anytime", help="what you need on hand: laptop | phone | anytime")
    aa.add_argument("--dedupe", action="store_true",
                    help="no-op (print existing id) if an open item with the same --job and --type already exists")
    aa.set_defaults(fn=cmd_action_add)
    al = acs.add_parser("list")
    al.add_argument("--all", action="store_true")
    al.set_defaults(fn=cmd_action_list)
    ad = acs.add_parser("done")
    ad.add_argument("id")
    ad.set_defaults(fn=cmd_action_done)

    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except (SetupError, ConfigError) as e:
        print(f"careeros: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
