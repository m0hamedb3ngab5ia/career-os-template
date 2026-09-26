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
    tr = Tracker(settings=s)
    if job_id and not (company and role):
        p = Store(s).load_posting(job_id)
        if p:
            company, role = company or p.company, role or p.title
    if dedupe:
        for it in tr.list_action_items(open_only=True):
            if str(it.get("JobID") or "") == job_id and str(it.get("Type") or "") == type:
                return f"action item {it.get('ID')} already open ({type}, job {job_id or '-'}); not added"
    aid = tr.add_action_item(what=what, type=type, job_id=job_id, company=company,
                             role=role, link=link, priority=priority, needs=needs)
    return f"action item {aid} added ({type}/{priority}/{needs})"


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
    /prepare-job on them). Other skips are never touched."""
    from careeros.company_policy import DEFERRED_REASONS, gate

    s = _settings(args)
    policy, records = _policy_inputs(s)
    want = policy.company_key(args.company) if args.company else None
    requeued, waiting = [], []
    for r in records:
        if r.status != "skipped" or r.skip_reason not in DEFERRED_REASONS:
            continue
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


def cmd_job_freeze(args: argparse.Namespace) -> int:
    """Freeze an as-submitted copy of the job's documents (and the form values, if given)."""
    from careeros.apply.snapshot import freeze

    store = Store(_settings(args))
    if not store.exists(args.job_id):
        print(f"job {args.job_id} not found", file=sys.stderr)
        return 1
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
        print(json.dumps({"dry_run": dry, "items": [i.to_dict() for i in items], "summary": summary,
                          "freed_bytes": freed}, indent=2))
        return 0
    if not items:
        print("prune: nothing to remove")
        return 0
    for i in items:
        what = (f"{len(i.paths)} screenshot(s): " + ", ".join(Path(p).name for p in i.paths[:4])
                + (" ..." if len(i.paths) > 4 else "")) if i.action == "delete_screenshots" else "trim posting.json to a stub"
        print(f"{i.job_id}  {what}  ({retention.human_bytes(i.bytes)})")
    total = f"{summary['jobs']} job(s), {summary['files']} file(s), {retention.human_bytes(summary['bytes'])}"
    if dry:
        print(f"\ndry run: would free {total}. Re-run with --yes to apply.")
        return 0
    freed = retention.execute(s, items)
    print(f"\npruned {total}; freed {retention.human_bytes(freed)}")
    return 0


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
    jst.set_defaults(fn=cmd_job_status)
    jfz = jbs.add_parser("freeze", help="keep an as-submitted copy of the documents under submitted/<stamp>/")
    jfz.add_argument("job_id")
    jfz.add_argument("--reason", choices=("submitted", "assisted_stop", "manual"),
                     help="default: from apply_session.json, else manual")
    jfz.add_argument("--answers-json", help="file or - (stdin): [{label, value, source}] or {label: value}")
    jfz.set_defaults(fn=cmd_job_freeze)

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
