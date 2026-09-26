"""`run_batch`: execute_run plus the policies around it. The CLI and the scheduler call this, not the loop.

- retry: a job that failed on its own (failures.JOB_FAILURES) is retried once in a later run (it gets the
  ranking's retry bonus); when it reaches `runs.retry.max_attempts` it becomes an Action Item (deduped) and
  runs leave it alone. Its status never changes.
- prepare runs: the company gate is checked before each call (a blocked job is passed over, not skipped: the
  skill would record the deferral itself), and with `runs.prepare.stop_at_daily_cap` the run stops once the jobs
  ready to submit (queued) reach today's daily apply cap: preparing more than can be sent today is wasted work.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from careeros.config import Settings
from careeros.runs.config import Budget, RunsConfig, load_runs_config
from careeros.runs.failures import JOB_FAILURES, Failures
from careeros.runs.policy import current_cap, load_prepare_config, load_retry_config
from careeros.runs.runner import SKILLS, execute_run
from careeros.runs.store import RunStore
from careeros.store import Store

READY = ("queued", "prepared")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def gate_check(settings: Settings, warnings: list[str] | None = None,
               echo: Callable[[str], None] = lambda s: None) -> Callable[[dict[str, Any]], str | None]:
    """Company gate before each prepare call. A deferral (company_cap, cooldown) only passes the job over (it
    competes again later); any other block (closed, not_similar, already_applied, ...) is a verdict and the job is
    recorded `skipped` with a note `company <reason>: <detail>`, as prepare-job would. Also warns (never blocks)
    when the company still has unscored `found` jobs: the fit-first slot ranking can't see them yet."""
    from careeros.company_policy import DEFERRED_REASONS, Policy, gate, load_records
    from careeros.tracker import set_status_both

    policy = Policy.from_settings(settings)
    warned: set[str] = set()

    def check(item: dict[str, Any]) -> str | None:
        records = load_records(settings)
        try:
            g = gate(item["job_id"], records=records, policy=policy)
        except KeyError:
            return None
        key = policy.company_key(g["company"])
        if key not in warned and g["allowed"]:
            unscored = [r.job_id for r in records if r.status == "found" and r.fit is None
                        and r.job_id != item["job_id"] and policy.company_key(r.company) == key]
            if unscored:
                warned.add(key)
                msg = (f"warning: {g['company']} still has {len(unscored)} unscored found job(s) "
                       f"({', '.join(unscored[:5])}); fit-first slots can't rank them yet: run `careeros run score` "
                       "to completion first if you want that")
                if warnings is not None:
                    warnings.append(msg)
                echo(f"    {msg}")
        if g["allowed"]:
            return None
        if g["reason"] not in DEFERRED_REASONS:
            set_status_both(settings, item["job_id"], "skipped", f"company {g['reason']}: {g['detail']}"[:200])
        return f"company gate: {g['reason']} ({g['detail']})"

    return check


def _selectable(settings: Settings, kind: str, job_id: str) -> bool:
    from careeros.runs.runner import eligibility

    store = Store(settings)
    score = store._read(job_id, "score.json") or {}
    prep = store._read(job_id, "prepare.json") or {}
    return eligibility(kind, store.get_status(job_id) or "found", (store.job_dir(job_id) / "score.json").exists(),
                       score, bool(prep.get("qa_pass"))) is None


def daily_cap_stop(settings: Settings) -> Callable[[], tuple[str, str] | None]:
    def check() -> tuple[str, str] | None:
        cap = current_cap(settings)
        store = Store(settings)
        ready = sum(1 for j in store.iter_job_ids() if store.get_status(j) in READY)
        if ready >= cap["remaining"]:
            return "daily_cap", (f"{ready} application(s) ready to submit; today's cap leaves {cap['remaining']} "
                                 f"({cap['applied']}/{cap['cap']} sent)")
        return None

    return check


def run_batch(settings: Settings, kind: str, budget: Budget, *, cfg: RunsConfig | None = None,
              trigger: str = "manual", dry_run: bool = False, invoke=None, doctor=None,
              now: Callable[[], datetime] = _utcnow, clock: Callable[[], float] = time.monotonic, cancel=None,
              echo: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    from careeros.tracker import add_action

    cfg = cfg or load_runs_config(settings)
    retry = load_retry_config(cfg.raw)
    fails = Failures(RunStore(settings))
    max_attempts = retry["max_attempts"]

    def after(att: dict[str, Any]) -> None:
        jid, outcome = att["job_id"], att["outcome"]
        if outcome == "ok":
            fails.clear(kind, jid)
            return
        if outcome not in JOB_FAILURES:
            return
        n = fails.record(kind, jid, outcome, att.get("detail") or "", att["run_id"], now())
        if retry["action_item"] and n < max_attempts and not _selectable(settings, kind, jid):
            # the failed call left files that make the job ineligible (e.g. a passing prepare.json with the
            # status never recorded): no run can retry it, so hand it over now
            what = (f"careeros run: /{SKILLS[kind]} failed on job {jid} ({outcome}: "
                    f"{(att.get('detail') or '')[:120]}) and left it where no run picks it up again; finish it by "
                    f"hand (see `careeros run show {att['run_id']}`)")
            add_action(settings, what, "other", job_id=jid, priority="M", needs="laptop", dedupe=True)
            echo(f"    {jid}: not selectable after the failure -> Action Item")
            return
        if n >= max_attempts and retry["action_item"]:
            what = (f"careeros run: /{SKILLS[kind]} failed {n} times on job {jid} ({outcome}: "
                    f"{(att.get('detail') or '')[:120]}). Run it by hand or see `careeros run show {att['run_id']}`")
            add_action(settings, what, "other", job_id=jid, priority="M", needs="laptop", dedupe=True)
            echo(f"    {jid}: out of retries -> Action Item")

    extra_stop = None
    pre_attempt = None
    warnings: list[str] = []
    if kind == "prepare":
        pre_attempt = gate_check(settings, warnings, echo)
        if load_prepare_config(cfg.raw)["stop_at_daily_cap"]:
            extra_stop = daily_cap_stop(settings)
    run = execute_run(settings, kind, budget, cfg=cfg, trigger=trigger, dry_run=dry_run, invoke=invoke,
                      doctor=doctor, now=now, clock=clock, cancel=cancel, echo=echo,
                      retry_ids=fails.retry_ids(kind, max_attempts), skip_ids=fails.exhausted(kind, max_attempts),
                      extra_stop=extra_stop, after_attempt=after, pre_attempt=pre_attempt)
    if not dry_run:
        run["warnings"] = warnings
        rs = RunStore(settings)
        rs.save_run(run)
        for w in warnings:
            rs.log(run["id"], w)
    return run
