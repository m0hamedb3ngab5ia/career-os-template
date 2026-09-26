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
from careeros.outreach import OutreachPolicy, check_contacts, manual_action_text, mark_contact
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
          f"filtered(title={t['filtered_title']} location={t['filtered_location']} blocklist={t['filtered_blocklist']} "
          f"flagged={t['filtered_flagged']} ghost={t['filtered_ghost']})")
    if summary.bad_slugs:
        print("\nbad slugs (404) — fix in config/companies.yaml:")
        for b in summary.bad_slugs:
            print(f"  - {b.company}: {b.ats}/{b.slug}")
    if summary.errors:
        print("\nerrors:")
        for b in summary.errors:
            print(f"  - {b.company}: {b.error}")
    if args.sync and t["stored"]:
        from careeros.scout import sync_to_tracker

        print(f"tracker: {sync_to_tracker(s, store, summary)}")
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
    if "status" in data and (locked := _job_lock_guard(s, args.job_id, args)) is not None:
        return locked
    if "status" in data:  # keep status.json in step, or the next `tracker sync` reverts the row
        store = Store(s)
        if store.exists(args.job_id):
            store.set_status(args.job_id, data["status"], "via tracker upsert")
    tr = Tracker(settings=s)
    res = tr.upsert_job({"job_id": args.job_id, **data})
    print(f"{args.job_id}: {res} ({', '.join(sorted(data))})")
    return 0


def cmd_jobs_list(args: argparse.Namespace) -> int:
    s = _settings(args)
    store = Store(s)
    wanted = args.status or []
    jobs = store.list_jobs(wanted[0] if len(wanted) == 1 else None)
    if len(wanted) > 1:
        jobs = [j for j in jobs if j["status"] in wanted]
    if getattr(args, "order", None) == "urgent":
        from careeros.company_policy import Policy, load_records, order_jobs

        jobs = order_jobs(jobs, records=load_records(s, store=store), policy=Policy.from_settings(s))
    if args.json:
        print(json.dumps(jobs, indent=2))
        return 0
    if not jobs:
        print("no jobs" + (f" with status={','.join(args.status)}" if args.status else ""))
        return 0
    print(f"{'id':<12} {'status':<13} {'fit':>3} {'company':<20} {'title':<45} location")
    for j in jobs:
        fit = "" if j["fit"] is None else str(j["fit"])
        urgent = f"  URGENT closes {j['closes_at']}" if j.get("urgent") and j.get("closes_at") else (
            "  URGENT" if j.get("urgent") else "")
        print(f"{j['job_id']:<12} {j['status']:<13} {fit:>3} {j['company'][:20]:<20} {j['title'][:45]:<45} "
              f"{j['location'][:30]}{urgent}")
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
    from careeros.apply.snapshot import latest

    snap = latest(store.job_dir(p.job_id))
    if snap:
        print(f"submitted: {snap['frozen_at']} ({snap['reason']}) -> {snap['dir']}")
    log = store.read_log(p.job_id)
    if log:
        print("\nlog:\n" + log.rstrip())
    return 0


def _add_action(s: Settings, what: str, type: str, job_id: str = "", company: str = "", role: str = "",
                link: str = "", priority: str = "M", needs: str = "anytime", dedupe: bool = False) -> str:
    from careeros.tracker import add_action

    return add_action(s, what, type, job_id=job_id, company=company, role=role, link=link, priority=priority,
                      needs=needs, dedupe=dedupe)


def cmd_action_add(args: argparse.Namespace) -> int:
    print(_add_action(_settings(args), args.what, args.type, job_id=args.job or "", company=args.company or "",
                      role=args.role or "", link=args.link or "", priority=args.priority, needs=args.needs,
                      dedupe=getattr(args, "dedupe", False)))
    return 0


SAFETY_HARD_EXIT = 3
GHOST_SKIP_EXIT = 4
COMPANY_BLOCKED_EXIT = 3


def _policy_inputs(s: Settings):
    from careeros.company_policy import Policy, load_records

    return Policy.from_settings(s), load_records(s)


def cmd_company_slots(args: argparse.Namespace) -> int:
    """Per-company slot use (cap window, reservations, cooldown) and how its candidate roles rank."""
    from careeros.company_policy import rank_candidates, slots

    policy, records = _policy_inputs(_settings(args))
    sl = slots(args.company, records=records, policy=policy)
    ranked = rank_candidates(args.company, records=records, policy=policy)
    if args.json:
        print(json.dumps({**sl, "candidates": ranked}, indent=2))
        return 0
    print(f"{args.company}: {sl['used']}/{sl['allowed']} used in {sl['window_days']} days "
          f"(submitted {sl['submitted']}, reserved {sl['reserved']}); {sl['remaining']} left"
          + (f"; cooldown until {sl['cooldown_until']}" if sl["cooldown_until"] else ""))
    for c in ranked:
        flag = "ALLOW" if c["allowed"] else "wait "
        extra = (" URGENT" if c["urgent"] else "") + (f" closes {c['closes_at']}" if c["closes_at"] else "")
        print(f"  {flag} {c['job_id']:<12} {c['status']:<12} {str(c['fit'] or ''):>3} {c['reason']:<12} "
              f"{(c['title'] or '')[:40]}{extra}")
    return 0


def cmd_company_gate(args: argparse.Namespace) -> int:
    """Exit 0 = may prepare/submit now, 3 = blocked (company_cap | cooldown | not_similar | closed |
    unscored | already_applied), 1 = unknown job. Read-only: the calling skill records the decision."""
    from careeros.company_policy import gate

    policy, records = _policy_inputs(_settings(args))
    try:
        g = gate(args.job_id, records=records, policy=policy)
    except KeyError:
        print(f"job {args.job_id} not found", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(g, indent=2))
    else:
        print(f"{args.job_id}: {'ALLOWED' if g['allowed'] else 'BLOCKED'} ({g['reason']}"
              + (", urgent" if g["urgent"] else "") + f") {g['detail']}")
    return 0 if g["allowed"] else COMPANY_BLOCKED_EXIT


def cmd_company_active(args: argparse.Namespace) -> int:
    """Other live applications at a company and the recruiter transparency note (inbox-sync)."""
    from careeros.company_policy import active_applications, transparency_note

    policy, records = _policy_inputs(_settings(args))
    act = active_applications(args.company, records=records, exclude_job=args.exclude, policy=policy)
    note = transparency_note(args.company, records=records, exclude_job=args.exclude, policy=policy)
    if args.json:
        print(json.dumps({"company": args.company, "active": act, "note": note}, indent=2))
    else:
        print(note or f"no other active applications at {args.company}")
    return 0


def cmd_company_requeue(args: argparse.Namespace) -> int:
    """Jobs skipped as `company_cap` / `cooldown` whose gate is open now -> status `scored` (re-run
    /prepare-job on them). Other skips, and deferred jobs whose posting retention pruned, are never touched."""
    from careeros.company_policy import DEFERRED_REASONS, gate

    s = _settings(args)
    policy, records = _policy_inputs(s)
    want = policy.company_key(args.company) if args.company else None
    requeued, waiting = [], []
    for r in records:
        if r.status != "skipped" or r.skip_reason not in DEFERRED_REASONS or r.pruned:
            continue  # a pruned posting is only a preview: prepare-job would refuse it
        if want is not None and policy.company_key(r.company) != want:
            continue
        g = gate(r.job_id, records=records, policy=policy)
        item = {"job_id": r.job_id, "company": r.company, "title": r.title, "was": r.skip_reason,
                "reason": g["reason"], "urgent": g["urgent"], "closes_at": g["closes_at"], "until": g["until"]}
        (requeued if g["allowed"] else waiting).append(item)
    if not args.dry_run:
        for it in requeued:
            _set_status_both(s, it["job_id"], "scored", f"requeued: {it['was']} cleared")
    if args.json:
        print(json.dumps({"requeued": requeued, "still_deferred": waiting, "dry_run": args.dry_run}, indent=2))
        return 0
    verb = "would requeue" if args.dry_run else "requeued"
    for it in requeued:
        print(f"{verb} {it['job_id']} {it['company']} — {it['title']} (was {it['was']})"
              + (" URGENT" if it["urgent"] else "") + f"; next: /prepare-job data/jobs/{it['job_id']}")
    for it in waiting:
        print(f"still deferred {it['job_id']} {it['company']} — {it['title']}: {it['reason']}"
              + (f" until {it['until']}" if it["until"] else ""))
    if not requeued and not waiting:
        print("no deferred jobs")
    return 0


def _set_status_both(s: Settings, job_id: str, status: str, note: str) -> None:
    from careeros.tracker import set_status_both

    set_status_both(s, job_id, status, note)


def cmd_safety_check(args: argparse.Namespace) -> int:
    """Posting gate: scam + company risk + ghost checks -> data/jobs/<id>/safety.json with a verdict
    (pass | review | skip | block), every flag's reason code, evidence and timestamp, and a `runs` trail.
    Exit 0 = pass or review (review turns auto-submit off), 3 = block (Action Item `scam_suspected`,
    needs_review, company recorded in the registry), 4 = skip (dead posting, status skipped)."""
    from careeros.safety import registry
    from careeros.safety.ghost import check_ghost, load_signals
    from careeros.safety.scam import apply_levels, auto_submit_allowed, check_posting, registrable_domain, verdict

    s = _settings(args)
    store = Store(s)
    p = store.load_posting(args.job_id)
    if not p:
        print(f"job {args.job_id} not found", file=sys.stderr)
        return 1
    if (store._read(p.job_id, "posting.json") or {}).get("pruned"):
        print(f"job {p.job_id}: posting.json was pruned by retention (description is only a preview); "
              "refusing to run the safety check. Re-fetch the posting first.", file=sys.stderr)
        return 1
    reg_path = registry.default_path(s)
    flags = check_posting(p, s, registry=registry.load(reg_path), verified=registry.load(registry.verified_path(s)))
    flags += check_ghost(p, store.history_for(p), load_signals(s), s, company_history=store.load_history())
    flags = apply_levels(flags, s)
    v = verdict(flags)
    ok, why = auto_submit_allowed(p, s)
    concerns = [f.code for f in flags if f.level != "info"]
    prev = store._read(p.job_id, "safety.json") or {}
    now = datetime.now().isoformat(timespec="seconds")
    result = {"job_id": p.job_id, "checked_at": now, "verdict": v, "flags": [f.to_dict() for f in flags],
              "auto_submit_allowed": ok and v == "pass",
              "auto_submit_reason": why or ", ".join(dict.fromkeys(concerns)),
              "runs": (prev.get("runs") or []) + [{"at": now, "verdict": v, "codes": [f.code for f in flags]}]}
    store._write(p.job_id, "safety.json", result)
    for f in flags:
        print(f"  {f.level.upper():<6} {f.code:<32} {f.detail}")
    codes = "; ".join(dict.fromkeys(f.code for f in flags if f.level == v))
    if v == "block":
        registry.add_or_bump(reg_path, p.company, domain=registrable_domain(p.apply_url or p.url), reason=codes,
                             job_id=p.job_id, confidence="high",
                             evidence=[u for f in flags if f.level == "block" for u in f.evidence])
        print(_add_action(s, f"scam gate BLOCK: {codes} at {p.company} ({p.apply_url or p.url}); see safety.json",
                          "scam_suspected", job_id=p.job_id, link=p.apply_url or p.url, priority="H", needs="phone",
                          dedupe=True))
        _set_status_both(s, p.job_id, "needs_review", f"safety block: {codes}"[:200])
        store.append_log(p.job_id, f"safety block: {codes}", component="safety")
        print(f"{p.job_id}: BLOCK ({codes})")
        return SAFETY_HARD_EXIT
    if v == "skip":
        _set_status_both(s, p.job_id, "skipped", f"ghost job: {codes}"[:200])
        store.append_log(p.job_id, f"safety skip: {codes}", component="safety")
        print(f"{p.job_id}: SKIP ({codes})")
        return GHOST_SKIP_EXIT
    ghosts = [f for f in flags if f.code.startswith("GHOST_") and f.level == "review"]
    if ghosts and s.is_dream(p.company):
        print(_add_action(s, f"possible ghost job at dream company: {'; '.join(f.detail for f in ghosts)}"[:300],
                          "ghost_job", job_id=p.job_id, link=p.url or p.apply_url, priority="M",
                          needs="anytime", dedupe=True))
    store.append_log(p.job_id, f"safety {v}" + (f": {', '.join(concerns)}" if concerns else ""), component="safety")
    print(f"{p.job_id}: {v.upper()}" + (f" ({', '.join(dict.fromkeys(concerns))}; auto-submit off)" if v == "review" else ""))
    return 0


def cmd_safety_fields(args: argparse.Namespace) -> int:
    """Form gate: JSON list of visible labels (stdin with `-`). Exit 3 on any blocked field."""
    from careeros.safety.scam import apply_levels, check_form_fields

    s = _settings(args)
    store = Store(s)
    if not store.exists(args.job_id):
        print(f"job {args.job_id} not found", file=sys.stderr)
        return 1
    raw = sys.stdin.read() if args.labels_json == "-" else Path(args.labels_json).read_text(encoding="utf-8")
    labels = [str(x) for x in json.loads(raw or "[]")]
    flags = [f for f in apply_levels(check_form_fields(labels, status=store.get_status(args.job_id),
                                                       page_url=args.page_url or ""), s) if f.level == "block"]
    if not flags:
        print(f"{args.job_id}: {len(labels)} field(s) ok")
        return 0
    for f in flags:
        print(f"  BLOCK  {f.code:<26} {f.detail}")
    what = "; ".join(f"{f.code}: {f.detail}" for f in flags)[:300]
    print(_add_action(s, f"scam gate (form): {what}", "scam_suspected", job_id=args.job_id, link=args.page_url or "",
                      priority="H", needs="phone", dedupe=True))
    _set_status_both(s, args.job_id, "needs_review", f"safety block (form): {what}"[:200])
    return SAFETY_HARD_EXIT


def cmd_safety_verify(args: argparse.Namespace) -> int:
    from careeros.safety import registry

    s = _settings(args)
    try:
        e = registry.add_verified(registry.verified_path(s), args.company, risk=args.risk, domain=args.domain or "",
                                  signals=args.signal or [], evidence=args.evidence or [])
    except ValueError as err:
        print(f"safety verify: {err}", file=sys.stderr)
        return 2
    print(f"verified: {e['company']} risk={e['risk']} signals={len(e['signals'])} -> {registry.verified_path(s)}")
    return 0


def cmd_safety_signal(args: argparse.Namespace) -> int:
    """Record a hiring freeze / layoffs report (or `none` after a clean check) for ghost-job detection."""
    from careeros.safety.ghost import default_signals_path, save_signal

    s = _settings(args)
    e = save_signal(s, args.company, args.kind, args.date, args.source, scope=args.scope or "")
    print(f"signal: {args.company} {e['kind']} {e['date']} scope={e['scope'] or '-'} -> {default_signals_path(s)}")
    return 0


def cmd_safety_flag(args: argparse.Namespace) -> int:
    from careeros.safety import registry

    s = _settings(args)
    e = registry.add_or_bump(registry.default_path(s), args.company, domain=args.domain or "",
                             reason=args.reason or "manual", notes=args.notes or "", confidence=args.confidence,
                             evidence=args.evidence or [], days=args.days)
    print(f"flagged: {e['company']} {e.get('domain') or ''} ({e['confidence']}, until {e['expires_at'][:10]}) "
          f"-> {registry.default_path(s)}")
    return 0


def cmd_safety_clear(args: argparse.Namespace) -> int:
    from careeros.safety import registry

    s = _settings(args)
    e = registry.clear(registry.default_path(s), args.company, note=args.note or "")
    if e is None:
        print(f"{args.company}: not in the flagged registry", file=sys.stderr)
        return 1
    print(f"cleared: {e['company']} ({e['review_note']})")
    return 0


JOB_LOCKED_EXIT = 6
DAILY_CAP_EXIT = 3


def _lock_token(args: argparse.Namespace) -> str | None:
    import os

    return getattr(args, "lock_token", None) or getattr(args, "token", None) or os.environ.get("CAREEROS_LOCK_TOKEN")


def _job_lock_guard(s: Settings, job_id: str, args: argparse.Namespace) -> int | None:
    """None when this command may change the job; JOB_LOCKED_EXIT (after printing why) when a run or a skill
    holds its lock. Matching --lock-token / CAREEROS_LOCK_TOKEN, a stale lock or --force let it through."""
    from careeros.runs import locks
    from careeros.runs.store import RunStore

    if getattr(args, "force", False):
        return None
    st = locks.status(RunStore(s).job_lock_path(job_id))
    if st["state"] != "held" or (_lock_token(args) and _lock_token(args) == st.get("token")):
        return None
    print(f"job {job_id} is locked by {st.get('owner')} until {st.get('expires_at')} ({st.get('note') or '-'}); "
          "not changed. Wait for it, pass --lock-token <token>, or --force", file=sys.stderr)
    return JOB_LOCKED_EXIT


def cmd_job_lock(args: argparse.Namespace) -> int:
    """Take the per-job lock (exit 6 if someone else holds it). The token from CAREEROS_LOCK_TOKEN (set by
    `careeros run` for the skill it calls) re-enters the runner's lock: `reentrant: true`, nothing changes."""
    import os

    from careeros.runs import locks
    from careeros.runs.config import load_runs_config
    from careeros.runs.store import RunStore

    s = _settings(args)
    if not Store(s).exists(args.job_id):
        print(f"job {args.job_id} not found", file=sys.stderr)
        return 1
    minutes = args.ttl_minutes if args.ttl_minutes is not None else load_runs_config(s).job_lock_minutes
    try:
        lk = locks.acquire(RunStore(s).job_lock_path(args.job_id), owner=args.owner, ttl_seconds=minutes * 60,
                           token=_lock_token(args), note=args.note or "")
    except locks.LockBusy as e:
        h = e.holder
        print(f"job {args.job_id} is locked by {h.get('owner')} until {h.get('expires_at')} ({h.get('note') or '-'})",
              file=sys.stderr)
        return JOB_LOCKED_EXIT
    out = {"job_id": args.job_id, "acquired": not lk.reentrant, "reentrant": lk.reentrant,
           "stale_taken": lk.stale_taken, "token": lk.token, "owner": lk.info.get("owner"),
           "expires_at": lk.info.get("expires_at")}
    if args.json:
        print(json.dumps(out))
    else:
        print(f"{args.job_id}: " + ("already held by this run (reentrant)" if lk.reentrant else
                                    f"locked by {args.owner} until {out['expires_at']}") + f"; token {lk.token}")
    return 0


def cmd_job_unlock(args: argparse.Namespace) -> int:
    from careeros.runs import locks
    from careeros.runs.store import RunStore

    ok = locks.release(RunStore(_settings(args)).job_lock_path(args.job_id), _lock_token(args), force=args.force)
    print(f"{args.job_id}: " + ("unlocked" if ok else "not unlocked (no lock, or the token does not match)"))
    return 0 if ok else 1


def cmd_job_check(args: argparse.Namespace) -> int:
    """Exit 0 = free (or a stale lock anyone may take), 6 = held."""
    from careeros.runs import locks
    from careeros.runs.store import RunStore

    st = locks.status(RunStore(_settings(args)).job_lock_path(args.job_id))
    st.pop("token", None)
    if args.json:
        print(json.dumps({"job_id": args.job_id, **st}))
    else:
        print(f"{args.job_id}: {st['state']}" + (f" by {st.get('owner')} until {st.get('expires_at')}"
                                                 if st["state"] != "free" else ""))
    return JOB_LOCKED_EXIT if st["state"] == "held" else 0


def cmd_job_status(args: argparse.Namespace) -> int:
    """Set a job's status in both data/jobs/<id>/status.json and the tracker row."""
    s = _settings(args)
    store = Store(s)
    if not store.exists(args.job_id):
        print(f"job {args.job_id} not found", file=sys.stderr)
        return 1
    if (locked := _job_lock_guard(s, args.job_id, args)) is not None:
        return locked
    store.set_status(args.job_id, args.status, args.note)
    tr = Tracker(settings=s)
    tr.set_status(args.job_id, args.status, args.note)
    pend = tr.pending_count()
    print(f"{args.job_id}: status -> {args.status}" + (f" (tracker op queued, file locked)" if pend else ""))
    return 0


def cmd_job_freeze(args: argparse.Namespace) -> int:
    """Freeze an as-submitted copy of the job's documents (and the form values, if given)."""
    from careeros.apply.snapshot import freeze

    s = _settings(args)
    store = Store(s)
    if not store.exists(args.job_id):
        print(f"job {args.job_id} not found", file=sys.stderr)
        return 1
    if (locked := _job_lock_guard(s, args.job_id, args)) is not None:
        return locked
    answers = None
    if args.answers_json:
        raw = sys.stdin.read() if args.answers_json == "-" else Path(args.answers_json).read_text(encoding="utf-8")
        try:
            answers = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"job freeze: --answers-json is not valid JSON: {e}", file=sys.stderr)
            return 2
        if not isinstance(answers, (list, dict)):
            print("job freeze: --answers-json must be a JSON list of {label, value, source} or an object",
                  file=sys.stderr)
            return 2
    try:
        out = freeze(store.job_dir(args.job_id), reason=args.reason, answers_entered=answers)
    except ValueError as e:
        print(f"job freeze: {e}", file=sys.stderr)
        return 2
    store.append_log(args.job_id, f"frozen as-submitted copy -> {out.relative_to(store.job_dir(args.job_id))}",
                     component="snapshot")
    print(f"{args.job_id}: frozen -> {out}")
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


def cmd_prune(args: argparse.Namespace) -> int:
    from careeros import retention

    s = _settings(args)
    items = retention.plan(s)
    dry = args.dry_run or not args.yes
    summary = retention.summarize(items)
    if args.json:
        freed = 0 if dry else retention.execute(s, items)
        if not dry:
            _snapshot_after_prune(s, freed)
        print(json.dumps({"dry_run": dry, "items": [i.to_dict() for i in items], "summary": summary,
                          "freed_bytes": freed}, indent=2))
        return 0
    if not items:
        if not dry:
            _snapshot_after_prune(s, 0)
        print("prune: nothing to remove")
        return 0
    for i in items:
        if i.run_id:
            what = "delete the whole run" if i.action == "delete_run" else f"delete {len(i.paths)} run log file(s)"
            print(f"run {i.run_id}  {what}  ({retention.human_bytes(i.bytes)})")
            continue
        what = (f"{len(i.paths)} screenshot(s): " + ", ".join(Path(p).name for p in i.paths[:4])
                + (" ..." if len(i.paths) > 4 else "")) if i.action == "delete_screenshots" else "trim posting.json to a stub"
        print(f"{i.job_id}  {what}  ({retention.human_bytes(i.bytes)})")
    total = (f"{summary['jobs']} job(s), " + (f"{summary['runs']} run(s), " if summary.get("runs") else "")
             + f"{summary['files']} file(s), {retention.human_bytes(summary['bytes'])}")
    if dry:
        print(f"\ndry run: would free {total}. Re-run with --yes to apply.")
        return 0
    freed = retention.execute(s, items)
    _snapshot_after_prune(s, freed)
    print(f"\npruned {total}; freed {retention.human_bytes(freed)}")
    return 0


def _snapshot_after_prune(s: Settings, freed: int) -> None:
    from careeros.runs.storage import snapshot_after_prune

    try:
        snapshot_after_prune(s, freed)
    except OSError as e:  # a snapshot must never make a prune fail
        print(f"prune: storage snapshot skipped ({e})", file=sys.stderr)


def _contacts_path(args: argparse.Namespace) -> tuple[Settings, Path | None]:
    s = _settings(args)
    f = Store(s).job_dir(args.job_id) / "contacts.json"
    if not f.exists():
        print(f"no contacts.json for job {args.job_id}; run /find-contacts first", file=sys.stderr)
        return s, None
    return s, f


def cmd_outreach_check(args: argparse.Namespace) -> int:
    s, f = _contacts_path(args)
    if f is None:
        return 1
    rows = check_contacts(json.loads(f.read_text(encoding="utf-8")), OutreachPolicy.from_settings(s))
    print(json.dumps({"job_id": args.job_id, "manual": sum(r["manual"] for r in rows),
                      "action_text": manual_action_text(rows), "contacts": rows}, indent=2))
    return 0


def cmd_outreach_mark(args: argparse.Namespace) -> int:
    if args.degree is None and args.mutuals is None:
        print("outreach mark: give --degree and/or --mutuals", file=sys.stderr)
        return 2
    _, f = _contacts_path(args)
    if f is None:
        return 1
    try:
        c = mark_contact(f, args.name, degree=args.degree, mutuals=args.mutuals)
    except KeyError:
        print(f"no contact named {args.name!r} in {f}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"outreach mark: {e}", file=sys.stderr)
        return 2
    print(f"{c.get('name')}: degree={c.get('linkedin_degree')} mutuals={c.get('mutuals')}")
    return 0


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


# --- runs (careeros.runs) -------------------------------------------------------------------------------

RUN_BUSY_EXIT = 5


def _fmt_minutes(sec: float | None) -> str:
    if sec is None:
        return "-"
    return f"{sec / 60:.0f}m" if sec >= 60 else f"{sec:.0f}s"


def _run_state(rs, run: dict) -> str:
    """run.json `status`, except a `running` run whose process no longer holds the runner lock: interrupted."""
    from careeros.runs import locks

    if run.get("status") != "running":
        return str(run.get("status"))
    held = locks.status(rs.runner_lock_path)
    return "running" if held.get("state") == "held" and held.get("owner") == f"run:{run['id']}" else "interrupted"


def _print_queue(items: list, limit: int) -> None:
    for r in items[:limit]:
        print(f"  {r['rank']:>3}. {r['job_id']:<12} {str(r.get('company') or '')[:18]:<18} "
              f"{str(r.get('title') or '')[:36]:<36} {r['score']:>6g}  {r['why']}")


def _run_kind(args: argparse.Namespace, kind: str) -> int:
    import signal
    import threading

    from careeros.runs.config import budget_for, load_runs_config
    from careeros.runs.runner import CLEAN_STOPS, RunBusy
    from careeros.runs.service import run_batch

    s = _settings(args)
    cfg = load_runs_config(s)
    try:
        budget = budget_for(cfg, kind, preset=args.preset, max_jobs=args.max_jobs, max_minutes=args.max_minutes)
    except ValueError as e:
        print(f"run {kind}: {e}", file=sys.stderr)
        return 2
    cancel = threading.Event()
    old = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            old[sig] = signal.signal(sig, lambda *_: cancel.set())
        except ValueError:  # not the main thread
            pass
    echo = (lambda line: None) if args.json else print
    try:
        rec = run_batch(s, kind, budget, cfg=cfg, trigger=args.trigger, dry_run=args.dry_run, cancel=cancel,
                        echo=echo)
    except RunBusy as e:
        print(f"run {kind}: {e}; not started", file=sys.stderr)
        return RUN_BUSY_EXIT
    finally:
        for sig, h in old.items():
            signal.signal(sig, h)
    if args.json:
        print(json.dumps(rec, indent=2, default=str))
    elif rec.get("dry_run"):
        b = rec["budget"]
        print(f"dry run: {kind} would take {len(rec['selected'])} of {rec['candidates']} candidate(s) "
              f"(preset {b['preset']}: max {b['max_jobs']} jobs, {b['max_minutes']:g} min)")
        _print_queue(rec["selected"], len(rec["selected"]))
        if rec["excluded"]:
            print(f"excluded: " + ", ".join(f"{e['job_id']} ({e['reason']})" for e in rec["excluded"][:10]))
    else:
        c = rec["counters"]
        print(f"run {rec['id']}: {rec['stop_reason']} — attempted {c['attempted']}, ok {c['ok']}, "
              f"failed {c['failed']}" + (f", locked {c['locked']}" if c.get("locked") else "")
              + (f" ({rec['detail']})" if rec.get("detail") else ""))
    if rec.get("dry_run"):
        return 0
    return 0 if rec["stop_reason"] in CLEAN_STOPS else 1


def cmd_run_score(args: argparse.Namespace) -> int:
    """Score the best-ranked `found` jobs with /score-job, one headless call each, within a budget."""
    return _run_kind(args, "score")


def cmd_run_prepare(args: argparse.Namespace) -> int:
    """/prepare-job the best-ranked scored jobs (fit-first within a company, company gate before each call)."""
    return _run_kind(args, "prepare")


def cmd_run_cap(args: argparse.Namespace) -> int:
    """Today's apply cap: volume.max_applications_per_day x season_multiplier. --check exits 3 when reached."""
    from careeros.runs.policy import current_cap

    st = current_cap(_settings(args))
    if args.json:
        print(json.dumps(st))
    else:
        print(f"{st['date']}: {st['applied']}/{st['cap']} applications today ({st['remaining']} left; "
              f"{st['base']}/day x {st['multiplier']:g} this month)")
    return DAILY_CAP_EXIT if args.check and st["reached"] else 0


def cmd_run_list(args: argparse.Namespace) -> int:
    from careeros.runs.store import RunStore

    rs = RunStore(_settings(args))
    runs = rs.list_runs(kind=args.kind, limit=args.limit)
    for r in runs:
        r["state"] = _run_state(rs, r)
    if args.json:
        print(json.dumps(runs, indent=2, default=str))
        return 0
    if not runs:
        print("no runs yet")
        return 0
    print(f"{'id':<30} {'trigger':<9} {'state':<12} {'stop':<21} {'done':>9}  took")
    for r in runs:
        c = r.get("counters") or {}
        print(f"{r['id']:<30} {r.get('trigger', ''):<9} {r['state']:<12} {str(r.get('stop_reason') or '-'):<21} "
              f"{c.get('ok', 0):>3}/{c.get('attempted', 0):<3}{'':>2}  {_fmt_minutes(r.get('duration_s'))}")
    return 0


def cmd_run_show(args: argparse.Namespace) -> int:
    from careeros.runs.store import RunStore

    rs = RunStore(_settings(args))
    run = rs.load_run(args.run_id)
    if run is None:
        print(f"run {args.run_id} not found", file=sys.stderr)
        return 1
    run["state"] = _run_state(rs, run)
    atts = rs.load_attempts(args.run_id)
    if args.json:
        print(json.dumps({**run, "attempts": atts}, indent=2, default=str))
        return 0
    if args.log:
        print(rs.read_log(args.run_id).rstrip())
        return 0
    c = run.get("counters") or {}
    print(f"{run['id']}  {run['kind']} ({run['trigger']})  {run['state']}  stop={run.get('stop_reason') or '-'}")
    print(f"budget: {run['budget']}  started {run['started_at']}  took {_fmt_minutes(run.get('duration_s'))}")
    print(f"counters: " + ", ".join(f"{k}={v}" for k, v in c.items()))
    if run.get("detail"):
        print(f"detail: {run['detail']}")
    for a in atts:
        print(f"  [{a['n']}] {a['job_id']} {a['stage']:<7} {a['outcome']:<17} {_fmt_minutes(a.get('duration_s')):>5} "
              f"session {a.get('session_id') or '-'}" + (f"  {a['detail']}" if a.get("detail") else ""))
    return 0


def _run_status_data(s: Settings) -> dict:
    from datetime import timezone

    from careeros.runs import locks
    from careeros.runs.config import KINDS, load_runs_config
    from careeros.runs.runner import select_candidates
    from careeros.runs.store import RunStore

    rs = RunStore(s)
    now = datetime.now(timezone.utc)
    held = locks.status(rs.runner_lock_path)
    cfg = load_runs_config(s)
    last, nxt = {}, {}
    for kind in KINDS:
        prev = rs.list_runs(kind=kind, limit=1)
        last[kind] = ({k: prev[0].get(k) for k in ("id", "trigger", "stop_reason", "started_at", "ended_at",
                                                    "counters")} | {"state": _run_state(rs, prev[0])}) if prev else None
    for kind in _STATUS_QUEUE_KINDS:
        ranked, _ = select_candidates(s, kind, cfg, now)
        nxt[kind] = [{k: r[k] for k in ("job_id", "company", "title", "score", "why")} for r in ranked[:5]]
    from careeros.runs.policy import AutoSubmitPolicy, current_cap

    auto = AutoSubmitPolicy.from_config(cfg.raw)
    return {"running": held if held.get("state") == "held" else None, "paused": rs.pause_state(now),
            "preset": cfg.preset, "last": last, "next": nxt, "cap": current_cap(s),
            "auto_submit": {"enabled": auto.enabled, "allow": auto.allow, "manual": auto.manual},
            "catch_up": _catch_up(rs), "schedule": _schedule_next(s)}


def _catch_up(rs):
    from careeros.runs.tick import load_catch_up

    return load_catch_up(rs)


def _schedule_next(s: Settings) -> dict:
    from careeros.runs.tick import schedule_overview

    return schedule_overview(s)["next"]


_STATUS_QUEUE_KINDS = ("score", "prepare")


def cmd_run_status(args: argparse.Namespace) -> int:
    """What is running, whether runs are paused, the last run of each kind and what goes next (and why)."""
    data = _run_status_data(_settings(args))
    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return 0
    r = data["running"]
    print("running: " + (f"{r.get('owner')} ({r.get('note')}, pid {r.get('pid')}, since {r.get('acquired_at')})"
                         if r else "none"))
    p = data["paused"]
    print("paused: " + (f"yes, until {p.get('until') or 'resumed'} ({p.get('reason') or '-'})" if p else "no"))
    c = data["cap"]
    print(f"today: {c['applied']}/{c['cap']} applications ({c['remaining']} left); auto-submit "
          + ("on" if data["auto_submit"]["enabled"] else "off (runs never apply)"))
    for kind, prev in data["last"].items():
        print(f"last {kind}: " + (f"{prev['id']} {prev['state']} stop={prev.get('stop_reason') or '-'}"
                                  if prev else "never"))
    print("scheduled: " + ", ".join(f"{k} {v or 'off'}" for k, v in data["schedule"].items()))
    if data["catch_up"]:
        print("missed runs waiting: " + ", ".join(data["catch_up"]["kinds"]) + " -> `careeros run catch-up`")
    for kind, items in data["next"].items():
        print(f"next {kind} (preset {data['preset']}):" + ("" if items else " nothing waiting"))
        for i, it in enumerate(items, 1):
            print(f"  {i}. {it['job_id']} {it['company'][:18]} — {it['title'][:36]}: {it['why']}")
    return 0


def _lock_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--lock-token", help="token of the job lock you hold (default: $CAREEROS_LOCK_TOKEN)")
    p.add_argument("--force", action="store_true", help="change the job even while it is locked")


def _parse_until(v: str | None):
    """`+2h`, `+30m`, `+1d` or an ISO date/time (local when no offset) -> aware datetime; None = until resumed."""
    import re
    from datetime import timedelta, timezone

    if not v:
        return None
    m = re.fullmatch(r"\+(\d+(?:\.\d+)?)([mhd])", v.strip())
    if m:
        n, unit = float(m[1]), m[2]
        return datetime.now(timezone.utc) + timedelta(**{{"m": "minutes", "h": "hours", "d": "days"}[unit]: n})
    dt = datetime.fromisoformat(v)
    return dt if dt.tzinfo else dt.astimezone()


def cmd_run_pause(args: argparse.Namespace) -> int:
    """Pause every run: the running one stops before its next job (stop reason paused); ticks skip due slots."""
    from datetime import timezone

    from careeros.runs.store import RunStore

    try:
        until = _parse_until(args.until)
    except ValueError:
        print(f"run pause: --until {args.until!r}: use +2h, +30m, +1d or an ISO date/time", file=sys.stderr)
        return 2
    p = RunStore(_settings(args)).set_pause(until, args.reason or "", datetime.now(timezone.utc))
    print(f"runs paused until {p['until'] or 'you run `careeros run resume`'}")
    return 0


def cmd_run_resume(args: argparse.Namespace) -> int:
    from careeros.runs.store import RunStore

    print("runs resumed" if RunStore(_settings(args)).clear_pause() else "runs were not paused")
    return 0


def cmd_run_catch_up(args: argparse.Namespace) -> int:
    """Start the pending catch-up (missed scheduled slots, collapsed into one record), or --dismiss it."""
    from careeros.runs.tick import load_catch_up, run_catch_up
    from careeros.runs.store import RunStore

    s = _settings(args)
    if args.dry_run:
        rec = load_catch_up(RunStore(s))
        print(json.dumps(rec, indent=2) if args.json else (
            "no missed runs" if not rec else "pending catch-up: " + ", ".join(
                f"{k} ({v.get('slots')} slot(s) since {v.get('first_missed')})" for k, v in rec["kinds"].items())))
        return 0
    try:
        res = run_catch_up(s, dismiss=args.dismiss, echo=(lambda line: None) if args.json else print)
    except RuntimeError as e:
        print(f"run catch-up: {e}", file=sys.stderr)
        return 1
    if res.get("status") == "busy":
        print(json.dumps(res) if args.json else "run catch-up: a tick is running; try again in a moment",
              file=None if args.json else sys.stderr)
        return RUN_BUSY_EXIT
    if args.json:
        print(json.dumps(res, indent=2, default=str))
    elif args.dismiss:
        print("catch-up dismissed" if res["dismissed"] else "no missed runs")
    elif not res["ran"] and not res["left"]:
        print("no missed runs")
    else:
        for k, r in res["results"].items():
            print(f"{k}: {r['status']} {r['detail']}")
        if res["left"]:
            print(f"still pending (runner busy): {', '.join(res['left'])}")
    return 0


def cmd_tick(args: argparse.Namespace) -> int:
    """One scheduler tick (launchd calls this every schedule.tick_minutes). Idempotent."""
    from careeros.runs.tick import tick

    out = tick(_settings(args), dry_run=args.dry_run, echo=(lambda line: None) if args.json else print)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    if out["status"] == "busy":
        print("tick: another tick is still running; nothing to do")
        return 0
    for d in out["decisions"]:
        res = out["results"].get(d["kind"])
        print(f"{d['kind']:<8} {d['action']:<12} " + (f"{res['status']}: {res['detail']}" if res else d["detail"]))
    return 0


def _schedule_env(s: Settings):
    import os
    import shutil

    from careeros.runs.schedule import load_schedule
    from careeros.runs.store import RunStore

    sc = load_schedule(s)
    claude = shutil.which("claude")
    dirs = [os.path.dirname(p) for p in (claude, sys.executable) if p]
    return sc, RunStore(s), claude, dirs


def cmd_schedule_install(args: argparse.Namespace) -> int:
    from careeros.runs import launchd

    s = _settings(args)
    sc, rs, claude, dirs = _schedule_env(s)
    plist = launchd.build_plist(label=sc.launchd_label, python=sys.executable, root=s.root, runs_dir=rs.dir,
                                tick_minutes=sc.tick_minutes, path_dirs=dirs)
    try:
        out = launchd.install(plist)
    except RuntimeError as e:
        print(f"schedule install: {e}", file=sys.stderr)
        return 1
    print(f"installed {out['plist']}: `careeros tick` every {sc.tick_minutes:g} min (logs in {rs.dir})")
    if not claude:
        print("warning: `claude` is not on PATH here; scheduled score/prepare runs will stop with doctor_failed",
              file=sys.stderr)
    return 0


def cmd_schedule_uninstall(args: argparse.Namespace) -> int:
    from careeros.runs import launchd

    sc, _, _, _ = _schedule_env(_settings(args))
    out = launchd.uninstall(sc.launchd_label)
    print(f"removed {out['plist']}" if out["removed"] else f"not installed ({out['plist']})")
    return 0


def cmd_schedule_status(args: argparse.Namespace) -> int:
    from careeros.runs import launchd
    from careeros.runs.tick import schedule_overview

    s = _settings(args)
    sc, _, _, _ = _schedule_env(s)
    data = {**launchd.status(sc.launchd_label), **schedule_overview(s)}
    if args.json:
        print(json.dumps(data, indent=2, default=str))
        return 0
    print(f"LaunchAgent {data['label']}: " + ("installed" if data["installed"] else "not installed")
          + (", loaded" if data["loaded"] else "") + f" ({data['plist']})")
    print(f"last tick: {data['last_tick'] or 'never'}" + ("   PAUSED" if data["paused"] else ""))
    for kind, at in data["next"].items():
        last = data["jobs"].get(kind) or {}
        print(f"  {kind:<8} next {at or 'disabled':<27} last {last.get('last_run') or '-'} "
              f"{last.get('last_status') or ''}")
    if data["catch_up"]:
        print("missed runs waiting: " + ", ".join(data["catch_up"]["kinds"]) + " -> `careeros run catch-up`")
    return 0


def cmd_storage(args: argparse.Namespace) -> int:
    """Disk use by category (postings, résumés/PDFs, screenshots, run logs, tracker, other) and free disk."""
    from careeros.retention import human_bytes
    from careeros.runs.storage import CATEGORIES, append_snapshot, measure
    from careeros.runs.store import RunStore

    s = _settings(args)
    m = measure(s)
    if args.snapshot:
        append_snapshot(RunStore(s), m, trigger="manual")
    if args.json:
        print(json.dumps(m, indent=2))
        return 0
    for c in CATEGORIES:
        share = m["bytes"][c] / m["total"] * 100 if m["total"] else 0
        print(f"  {c:<13} {human_bytes(m['bytes'][c]):>10}  {share:5.1f}%")
    d = m["disk"]
    print(f"  {'total':<13} {human_bytes(m['total']):>10}\ndisk free: {human_bytes(d['free'])} of "
          f"{human_bytes(d['total'])} ({d['free_pct']}%)" + ("\nsnapshot saved" if args.snapshot else ""))
    return 0


def cmd_advise(args: argparse.Namespace) -> int:
    """Suggestions from storage history and run history. Never changes anything (see `advise apply`)."""
    from datetime import timezone

    from careeros.retention import human_bytes
    from careeros.runs.advisor import advise

    out = advise(_settings(args), datetime.now(timezone.utc))
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    st, rn = out["storage"], out["runs"]
    if st["ready"]:
        p = st["projection"]
        print(f"storage: {human_bytes(st['current'])} now, {human_bytes(p['30d'])} in 30 days, "
              f"{human_bytes(p['90d'])} in 90 days (budget {human_bytes(st['budget'])})")
    else:
        print(f"storage: collecting data ({st['days']} of {st['need_days']} days of snapshots)")
    if not rn["ready"]:
        print(f"runs: collecting data (advice after {rn['min_runs']} runs of a kind)")
    for kind, m in rn["metrics"].items():
        print(f"{kind}: {m['runs']} runs, {m['attempts']} jobs, avg {m['avg_job_s']:.0f}s/job, "
              f"failures {m['failure_rate']:.0%}, budget used {m['budget_used']:.0%}")
    if not out["recommendations"]:
        print("no recommendations")
    for r in out["recommendations"]:
        c = r["change"]
        how = (f"  -> `careeros advise apply {r['id']}`: {c['path']}: {c['from']} -> {c['to']}" if c
               else "  (advice only)")
        print(f"[{r['severity']}] {r['id']}: {r['title']}. {r['why']}\n{how}")
    return 0


def _validate_root(root: Path) -> None:
    """Every config check the CLI would run; ConfigError rolls `advise apply` back."""
    from careeros import retention
    from careeros.runs.advisor import load_advisor_config
    from careeros.runs.config import load_runs_config
    from careeros.runs.schedule import load_schedule

    s = Settings.load(root)
    load_runs_config(s)
    load_schedule(s)
    retention.retention_config(s)
    load_advisor_config(s.pipeline)


def cmd_advise_apply(args: argparse.Namespace) -> int:
    """Apply ONE recommendation's YAML change to config/pipeline.yaml (comments kept, validated, rolled back on error)."""
    from datetime import timezone

    from careeros.runs import yamledit
    from careeros.runs.advisor import advise

    s = _settings(args)
    recs = {r["id"]: r for r in advise(s, datetime.now(timezone.utc))["recommendations"]}
    rec = recs.get(args.id)
    if rec is None:
        print(f"advise apply: no current recommendation {args.id!r}" +
              (f"; current: {', '.join(recs)}" if recs else "; run `careeros advise`"), file=sys.stderr)
        return 1
    c = rec["change"]
    if not c:
        print(f"advise apply: {args.id} is advice only; nothing to change", file=sys.stderr)
        return 1
    path = s.root / c["file"]
    try:
        from careeros.runs.advisor import effective_value

        yamledit.apply_change(path, c["path"], c["to"], expect_from=c["from"],
                              validate=lambda p: _validate_root(s.root),
                              current=lambda data: effective_value(json.loads(json.dumps(data or {}, default=str)),
                                                                   c["path"]))
    except (ConfigError, ValueError) as e:
        print(f"advise apply: {e}; {c['file']} left unchanged", file=sys.stderr)
        return 1
    print(f"{c['file']}: {c['path']}: {c['from']} -> {c['to']}")
    return 0


def _sync_root(args: argparse.Namespace) -> Path:
    from careeros.sync import git_root

    return git_root(Path(args.root).resolve() if getattr(args, "root", None) else Path.cwd())


def cmd_sync_status(args: argparse.Namespace) -> int:
    """Exit 0 in sync, 1 behind the template, 2 drift (files to port to the template). Needs no setup."""
    from careeros.sync import SyncError, compute_status, format_status

    try:
        st = compute_status(_sync_root(args), remote=args.remote, template_branch=args.template_branch,
                            fetch=not args.no_fetch)
    except SyncError as e:
        print(f"sync status: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ref": st.ref, "behind": st.behind, "drift": st.drift, "exit_code": st.exit_code},
                         indent=2))
    else:
        print("\n".join(format_status(st)))
    return st.exit_code


def cmd_sync_pull(args: argparse.Namespace) -> int:
    from careeros.sync import SyncError, pull

    try:
        res = pull(_sync_root(args), remote=args.remote, template_branch=args.template_branch, base=args.base,
                   branch=args.branch, checks=not args.no_checks)
    except SyncError as e:
        print(f"sync pull: {e}", file=sys.stderr)
        return 1
    if res.lines:
        print("\n".join(res.lines))
    if res.err:
        print("\n".join(res.err), file=sys.stderr)
    return res.code


def cmd_sync_install_hook(args: argparse.Namespace) -> int:
    from careeros.sync import SyncError, hook_path, install_hook

    try:
        hook = hook_path(_sync_root(args))
        what = install_hook(hook, sys.executable, force=args.force)
    except SyncError as e:
        print(f"sync install-hook: {e}", file=sys.stderr)
        return 1
    print(f"{what}: {hook}")
    return 0


def cmd_sync_check_template_push(args: argparse.Namespace) -> int:
    """pre-push hook body: reads the ref updates on stdin; exit 1 when personal paths would reach the template."""
    from careeros.sync import SyncError, check_push

    try:
        errors = check_push(_sync_root(args), args.url, sys.stdin.read())
    except SyncError as e:
        print(f"BLOCKED: careeros push guard failed: {e}", file=sys.stderr)
        return 1
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


def _run_budget_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--preset", choices=("small", "medium", "large", "max", "custom"),
                   help="budget preset from pipeline.yaml runs.presets (default: runs.preset)")
    p.add_argument("--max-jobs", type=int, help="override the preset's job count")
    p.add_argument("--max-minutes", type=float, help="override the preset's wall-clock minutes")
    p.add_argument("--dry-run", action="store_true", help="rank and show what would run, with the reasons; run nothing")
    p.add_argument("--trigger", choices=("manual", "schedule", "catch_up"), default="manual", help=argparse.SUPPRESS)
    p.add_argument("--json", action="store_true")


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
    _lock_args(tup)
    tup.set_defaults(fn=cmd_tracker_upsert)

    jobs = sub.add_parser("jobs")
    js = jobs.add_subparsers(dest="jobs_cmd", required=True)
    jl = js.add_parser("list")
    jl.add_argument("--status", choices=STATUSES, action="append",
                    help="repeat to list several statuses together (e.g. --status found --status scored)")
    jl.add_argument("--json", action="store_true")
    jl.add_argument("--order", choices=["urgent"],
                    help="urgent: jobs that must go now (deadline / cluster) first, then by close date, then fit")
    jl.set_defaults(fn=cmd_jobs_list)

    co = sub.add_parser("company", help="per-company caps, rejection cooldown, close dates (exit 3 = blocked)")
    cos = co.add_subparsers(dest="company_cmd", required=True)
    csl = cos.add_parser("slots", help="applications used / allowed in the window, and how candidates rank")
    csl.add_argument("company")
    csl.add_argument("--json", action="store_true")
    csl.set_defaults(fn=cmd_company_slots)
    cgt = cos.add_parser("gate", help="may this job be prepared/submitted now? exit 0 allowed, 3 blocked")
    cgt.add_argument("job_id")
    cgt.add_argument("--json", action="store_true")
    cgt.set_defaults(fn=cmd_company_gate)
    cac = cos.add_parser("active", help="other live applications at a company + the recruiter note")
    cac.add_argument("company")
    cac.add_argument("--exclude", metavar="JOB_ID", help="the job the email is about")
    cac.add_argument("--json", action="store_true")
    cac.set_defaults(fn=cmd_company_active)
    crq = cos.add_parser("requeue", help="skipped company_cap/cooldown jobs whose gate is open now -> scored")
    crq.add_argument("--company")
    crq.add_argument("--dry-run", action="store_true")
    crq.add_argument("--json", action="store_true")
    crq.set_defaults(fn=cmd_company_requeue)

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
    _lock_args(jst)
    jst.set_defaults(fn=cmd_job_status)
    jfz = jbs.add_parser("freeze", help="keep an as-submitted copy of the documents under submitted/<stamp>/")
    jfz.add_argument("job_id")
    jfz.add_argument("--reason", choices=("submitted", "assisted_stop", "manual"),
                     help="default: from apply_session.json, else manual")
    jfz.add_argument("--answers-json", help="file or - (stdin): [{label, value, source}] or {label: value}")
    _lock_args(jfz)
    jfz.set_defaults(fn=cmd_job_freeze)
    jlk = jbs.add_parser("lock", help="take the per-job lock (exit 6 if held): runs and prepare/apply skills use it")
    jlk.add_argument("job_id")
    jlk.add_argument("--owner", default="manual", help="who holds it, e.g. prepare-job")
    jlk.add_argument("--ttl-minutes", type=float, help="expires after this long (default runs.job_lock_minutes)")
    jlk.add_argument("--token", help="re-enter a lock you hold (default: $CAREEROS_LOCK_TOKEN)")
    jlk.add_argument("--note")
    jlk.add_argument("--json", action="store_true")
    jlk.set_defaults(fn=cmd_job_lock)
    jul = jbs.add_parser("unlock", help="release the per-job lock (needs its token, or --force)")
    jul.add_argument("job_id")
    jul.add_argument("--token", help="default: $CAREEROS_LOCK_TOKEN")
    jul.add_argument("--force", action="store_true")
    jul.set_defaults(fn=cmd_job_unlock)
    jck = jbs.add_parser("check", help="is the job locked? exit 0 free, 6 held")
    jck.add_argument("job_id")
    jck.add_argument("--json", action="store_true")
    jck.set_defaults(fn=cmd_job_check)

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

    sf = sub.add_parser("safety", help="scam + company + ghost-job gate (exit 3 = block, 4 = skip)")
    sfs = sf.add_subparsers(dest="safety_cmd", required=True)
    sck = sfs.add_parser("check", help="posting checks -> safety.json verdict pass|review|skip|block")
    sck.add_argument("job_id")
    sck.set_defaults(fn=cmd_safety_check)
    sfd = sfs.add_parser("fields", help="check visible form labels (JSON list) for identity/bank/payment/credential fields")
    sfd.add_argument("job_id")
    sfd.add_argument("--labels-json", required=True, help="path to a JSON list of labels, or - for stdin")
    sfd.add_argument("--page-url", help="URL of the page showing the fields (ATS account passwords are normal)")
    sfd.set_defaults(fn=cmd_safety_fields)
    svf = sfs.add_parser("verify", help="record a company check: risk low|medium|high from independent signals")
    svf.add_argument("company")
    svf.add_argument("--risk", choices=["low", "medium", "high"], required=True)
    svf.add_argument("--signal", action="append", help="one independent signal checked (repeat; low needs 2+)")
    svf.add_argument("--evidence", action="append", help="source URL (repeatable)")
    svf.add_argument("--domain")
    svf.set_defaults(fn=cmd_safety_verify)
    ssg = sfs.add_parser("signal", help="record a hiring freeze / layoffs report for ghost-job checks")
    ssg.add_argument("company")
    ssg.add_argument("--kind", choices=["freeze", "layoffs", "none"], required=True)
    ssg.add_argument("--date", required=True, help="YYYY-MM-DD of the report (today for `none`)")
    ssg.add_argument("--scope", help="what the freeze covers: company-wide, or teams/locations (e.g. \"engineering; NYC\")")
    ssg.add_argument("--source", required=True, help="URL of the report, or what was checked")
    ssg.set_defaults(fn=cmd_safety_signal)
    sfl = sfs.add_parser("flag", help="add a company (and domain) to data/flagged_registry.yaml by hand")
    sfl.add_argument("company")
    sfl.add_argument("--domain")
    sfl.add_argument("--reason")
    sfl.add_argument("--notes")
    sfl.add_argument("--confidence", choices=["high", "medium"], default="high",
                     help="high = block (scout drops it), medium = review")
    sfl.add_argument("--evidence", action="append", help="source URL (repeatable)")
    sfl.add_argument("--days", type=int, default=180, help="expire after this many days (default 180)")
    sfl.set_defaults(fn=cmd_safety_flag)
    scl = sfs.add_parser("clear", help="mark a flagged company reviewed and cleared")
    scl.add_argument("company")
    scl.add_argument("--note")
    scl.set_defaults(fn=cmd_safety_clear)

    pr = sub.add_parser("prune", help="remove old screenshots and trim old unprepared postings (dry run unless --yes)")
    pr.add_argument("--dry-run", action="store_true", help="only list what would go (the default; wins over --yes)")
    pr.add_argument("--yes", action="store_true", help="actually delete / trim")
    pr.add_argument("--json", action="store_true", help="machine-readable plan (and result with --yes)")
    pr.set_defaults(fn=cmd_prune)

    out = sub.add_parser("outreach", help="LinkedIn relationship gate: connected / mutuals -> tailor by hand")
    outs = out.add_subparsers(dest="outreach_cmd", required=True)
    och = outs.add_parser("check", help="JSON per contact: manual (never automated) + reason code; action_text for the one Action Item")
    och.add_argument("job_id")
    och.set_defaults(fn=cmd_outreach_check)
    omk = outs.add_parser("mark", help="record what LinkedIn shows for a contact (degree 1 = connected, mutual count)")
    omk.add_argument("job_id")
    omk.add_argument("name")
    omk.add_argument("--degree", type=int)
    omk.add_argument("--mutuals", type=int)
    omk.set_defaults(fn=cmd_outreach_mark)

    rn = sub.add_parser("run", help="unattended batches: rank jobs, call one skill per job headless, within a budget")
    rns = rn.add_subparsers(dest="run_cmd", required=True)
    rsc = rns.add_parser("score", help="/score-job the best-ranked found jobs (exit 1 on a stop that needs you, "
                                       f"{RUN_BUSY_EXIT} if a run is already going)")
    _run_budget_args(rsc)
    rsc.set_defaults(fn=cmd_run_score)
    rpp = rns.add_parser("prepare", help="/prepare-job the best-ranked scored jobs (never applies)")
    _run_budget_args(rpp)
    rpp.set_defaults(fn=cmd_run_prepare)
    rcp = rns.add_parser("cap", help="today's daily apply cap; --check exits 3 when it is reached")
    rcp.add_argument("--check", action="store_true")
    rcp.add_argument("--json", action="store_true")
    rcp.set_defaults(fn=cmd_run_cap)
    rls = rns.add_parser("list", help="past and current runs, newest first")
    rls.add_argument("--kind", choices=("score", "prepare", "inbox_sync"))
    rls.add_argument("--limit", type=int, default=20)
    rls.add_argument("--json", action="store_true")
    rls.set_defaults(fn=cmd_run_list)
    rsh = rns.add_parser("show", help="one run: budget, counters, stop reason, every attempt")
    rsh.add_argument("run_id")
    rsh.add_argument("--json", action="store_true", help="run.json plus its attempts")
    rsh.add_argument("--log", action="store_true", help="print run.log")
    rsh.set_defaults(fn=cmd_run_show)
    rpz = rns.add_parser("pause", help="pause all runs (the current one stops before its next job; ticks skip)")
    rpz.add_argument("--until", help="+2h, +30m, +1d or an ISO date/time (default: until `run resume`)")
    rpz.add_argument("--reason")
    rpz.set_defaults(fn=cmd_run_pause)
    rns.add_parser("resume", help="lift `run pause`").set_defaults(fn=cmd_run_resume)
    rcu = rns.add_parser("catch-up", help="run the missed scheduled slots (one pending record) now, or --dismiss")
    rcu.add_argument("--dismiss", action="store_true", help="drop the pending catch-up without running it")
    rcu.add_argument("--dry-run", action="store_true", help="show what is pending")
    rcu.add_argument("--json", action="store_true")
    rcu.set_defaults(fn=cmd_run_catch_up)
    rst = rns.add_parser("status", help="running run, pause, last run per kind, what goes next and why")
    rst.add_argument("--json", action="store_true")
    rst.set_defaults(fn=cmd_run_status)

    sto = sub.add_parser("storage", help="disk use by category + free disk; --snapshot records it for `advise`")
    sto.add_argument("--snapshot", action="store_true", help="append this measurement to data/runs/storage.jsonl")
    sto.add_argument("--json", action="store_true")
    sto.set_defaults(fn=cmd_storage)
    adv = sub.add_parser("advise", help="suggestions from storage + run history (never changes anything)")
    adv.add_argument("--json", action="store_true")
    adv.set_defaults(fn=cmd_advise)
    advs = adv.add_subparsers(dest="advise_cmd")
    ada = advs.add_parser("apply", help="apply one recommendation's change to config/pipeline.yaml (comments kept)")
    ada.add_argument("id")
    ada.set_defaults(fn=cmd_advise_apply)
    tk = sub.add_parser("tick", help="one scheduler tick: run what schedule.jobs says is due (launchd calls it)")
    tk.add_argument("--dry-run", action="store_true", help="show the decisions; run nothing")
    tk.add_argument("--json", action="store_true")
    tk.set_defaults(fn=cmd_tick)
    sch = sub.add_parser("schedule", help="macOS LaunchAgent that runs `careeros tick`")
    schs = sch.add_subparsers(dest="schedule_cmd", required=True)
    schs.add_parser("install", help="write ~/Library/LaunchAgents/<label>.plist and load it").set_defaults(
        fn=cmd_schedule_install)
    schs.add_parser("uninstall", help="unload and remove the LaunchAgent").set_defaults(fn=cmd_schedule_uninstall)
    sst = schs.add_parser("status", help="agent installed/loaded, last tick, next run per job, missed runs")
    sst.add_argument("--json", action="store_true")
    sst.set_defaults(fn=cmd_schedule_status)

    syn = sub.add_parser("sync", help="keep a private copy in sync with the public template (git remote `template`)")
    syns = syn.add_subparsers(dest="sync_cmd", required=True)

    def _sync_remote(q: argparse.ArgumentParser) -> None:
        q.add_argument("--remote", default="template", help="git remote of the template (default: template)")
        q.add_argument("--template-branch", default="main", help="template branch to follow (default: main)")

    sys_ = syns.add_parser("status", help="template commits not merged + drift to port (exit 0 in sync, 1 behind, 2 drift)")
    _sync_remote(sys_)
    sys_.add_argument("--no-fetch", action="store_true", help="use the last fetched state (offline)")
    sys_.add_argument("--json", action="store_true")
    sys_.set_defaults(fn=cmd_sync_status)
    spl = syns.add_parser("pull", help="merge the template on a sync/<date> branch, run local checks, print the PR "
                                       "command (exit 3 = conflicts to resolve)")
    _sync_remote(spl)
    spl.add_argument("--base", default="main", help="branch to start from (default: main)")
    spl.add_argument("--branch", help="sync branch name (default: sync/<YYYY-MM-DD>)")
    spl.add_argument("--no-checks", action="store_true", help="skip pytest and the ui/ npm checks")
    spl.set_defaults(fn=cmd_sync_pull)
    sih = syns.add_parser("install-hook", help="pre-push guard: never push personal paths to a template URL "
                                               "(git config careeros.templateUrlPattern / careeros.personalPaths)")
    sih.add_argument("--force", action="store_true", help="replace a pre-push hook careeros did not write (kept as .bak)")
    sih.set_defaults(fn=cmd_sync_install_hook)
    sct = syns.add_parser("check-template-push", help="the guard itself (the pre-push hook calls it; reads stdin)")
    sct.add_argument("remote_name")
    sct.add_argument("url")
    sct.set_defaults(fn=cmd_sync_check_template_push)

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
