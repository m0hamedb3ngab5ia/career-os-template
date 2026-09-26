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


def gate_check(settings: Settings) -> Callable[[dict[str, Any]], str | None]:
    from careeros.company_policy import Policy, gate, load_records

    policy = Policy.from_settings(settings)

    def check(item: dict[str, Any]) -> str | None:
        try:
            g = gate(item["job_id"], records=load_records(settings), policy=policy)
        except KeyError:
            return None
        return None if g["allowed"] else f"company gate: {g['reason']} ({g['detail']})"

    return check


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
        if n >= max_attempts and retry["action_item"]:
            what = (f"careeros run: /{SKILLS[kind]} failed {n} times on job {jid} ({outcome}: "
                    f"{(att.get('detail') or '')[:120]}). Run it by hand or see `careeros run show {att['run_id']}`")
            add_action(settings, what, "other", job_id=jid, priority="M", needs="laptop", dedupe=True)
            echo(f"    {jid}: out of retries -> Action Item")

    extra_stop = None
    pre_attempt = None
    if kind == "prepare":
        pre_attempt = gate_check(settings)
        if load_prepare_config(cfg.raw)["stop_at_daily_cap"]:
            extra_stop = daily_cap_stop(settings)
    return execute_run(settings, kind, budget, cfg=cfg, trigger=trigger, dry_run=dry_run, invoke=invoke,
                       doctor=doctor, now=now, clock=clock, cancel=cancel, echo=echo,
                       retry_ids=fails.retry_ids(kind, max_attempts), skip_ids=fails.exhausted(kind, max_attempts),
                       extra_stop=extra_stop, after_attempt=after, pre_attempt=pre_attempt)
