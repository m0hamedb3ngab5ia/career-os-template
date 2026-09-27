import { Check, Square } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { EmptyState } from "../../kit/EmptyState";
import { humanize } from "../../kit/labels";
import { Meter } from "../../kit/Meter";
import { formatDuration, formatNumber, formatWhen } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { useCancelRun, useRunStream } from "./api";
import { kindLabel, triggerLabel } from "./labels";
import { LogPane } from "./LogPane";
import styles from "./Runs.module.css";
import type { CurrentRun, JobRow, Step } from "./types";

function StepPill({ step }: { step: Step }) {
  const words = { done: " done", active: " in progress", pending: " not started", skipped: " skipped" }[step.state];
  return (
    <span className={styles.step} data-state={step.state}>
      {step.state === "done" ? <Check size={12} strokeWidth={2.4} aria-hidden="true" /> : null}
      {step.state === "active" ? <span className={styles.stepDot} aria-hidden="true" /> : null}
      {step.name}
      <span className="sr-only">{words}</span>
    </span>
  );
}

function jobOutcome(row: JobRow): string {
  if (row.state === "queued") return "queued";
  if (row.state === "active") return "in progress";
  const took = formatDuration(row.duration_s);
  const what = row.state === "done" ? "Done" : humanize(row.outcome ?? "failed");
  return took ? `${what} · ${took}` : what;
}

function JobRowView({ row, n }: { row: JobRow; n: number }) {
  return (
    <li className={styles.jobRow}>
      <span className={styles.rank}>{n}</span>
      <div className={styles.grow}>
        <div>
          <span className={styles.strong}>{row.company ?? row.job_id}</span>{" "}
          <span className={styles.sec}>{row.title}</span>
        </div>
        <div className={styles.steps}>
          {row.steps.map((s) => (
            <StepPill key={s.name} step={s} />
          ))}
        </div>
        {row.state === "failed" && row.detail ? <div className={styles.fix}>{row.detail}</div> : null}
      </div>
      <span className={styles.jobOutcome} data-state={row.state}>
        {jobOutcome(row)}
      </span>
    </li>
  );
}

export function CurrentRunCard({ run }: { run: CurrentRun | null | undefined }) {
  const now = useNow(30_000);
  const { lines } = useRunStream(run?.id, Boolean(run));
  const cancel = useCancelRun();
  const [asking, setAsking] = useState(false);
  const cancelButton = useRef<HTMLButtonElement>(null);
  if (!run) {
    return (
      <section className={`${styles.card} ${styles.grow}`} aria-labelledby="now-h">
        <h2 id="now-h" className={styles.h2}>
          Now
        </h2>
        <EmptyState title="Nothing running" headingLevel={3}>
          Start a run, or wait for the next scheduled one.
        </EmptyState>
      </section>
    );
  }
  const u = run.used;
  const noun = run.kind === "prepare" ? "Jobs prepared" : run.kind === "score" ? "Jobs scored" : "Jobs";
  const started = formatWhen(run.started_at, now);
  const preset = run.budget?.preset ? `${humanize(run.budget.preset)} budget` : null;
  const minutes = u.minutes ?? 0;
  const trig = triggerLabel(run.trigger);
  const queued = run.jobs.some((j) => j.state === "queued");
  const stopping = cancel.data?.status === "cancelling" || cancel.data?.status === "already_stopping";
  return (
    <section className={`${styles.card} ${styles.grow}`} aria-labelledby="now-h">
      <div className={styles.cardHead}>
        <div>
          <h2 id="now-h" className={styles.runTitle}>
            {kindLabel(run.kind)}
            {trig ? ` · ${trig}` : ""}
          </h2>
          <div className={styles.sub}>
            {[preset, started ? `started ${started}` : null, formatDuration(Math.round(minutes) * 60)].filter(Boolean).join(" · ")}
          </div>
        </div>
        <div className={styles.headActions}>
          <Chip tone="blue">
            <span className={styles.chipDot} aria-hidden="true" />
            Running
          </Chip>
          {run.scheduled ? (
            <span className={styles.note}>Use Pause all to stop a scheduled run</span>
          ) : stopping || asking ? null : (
            <Button
              ref={cancelButton}
              size="small"
              icon={<Square size={14} strokeWidth={1.7} aria-hidden="true" />}
              onClick={() => setAsking(true)}
            >
              Cancel run
            </Button>
          )}
        </div>
      </div>
      {asking ? (
        <div className={styles.block}>
          <ConfirmPanel
            question="Cancel this run? Jobs already finished are kept."
            cancelLabel="Keep running"
            confirmLabel="Cancel run"
            pending={cancel.isPending}
            returnFocusRef={cancelButton}
            onCancel={() => setAsking(false)}
            onConfirm={() => cancel.mutate(run.id, { onSettled: () => setAsking(false) })}
          />
        </div>
      ) : null}
      <div role="status" className={styles.statusSlot}>
        {stopping ? <div className={styles.infoBox}>Cancelling at the next safe point…</div> : null}
        {cancel.data?.status === "refused" ? <div className={styles.infoBox}>{cancel.data.detail}</div> : null}
        {cancel.error ? <div className={styles.infoBox}>{cancel.error.message}</div> : null}
      </div>
      <div className={styles.meters}>
        <Meter
          label={noun}
          value={u.jobs}
          max={u.max_jobs ?? 0}
          valueText={`${formatNumber(u.jobs)} of ${formatNumber(u.max_jobs ?? 0)}`}
        />
        <Meter
          label="Time budget"
          value={minutes}
          max={u.max_minutes ?? 0}
          valueText={`${formatNumber(Math.round(minutes))} of ${formatNumber(u.max_minutes ?? 0)} min`}
        />
        {run.cap ? (
          <Meter
            label="Daily apply cap"
            value={run.cap.applied}
            max={run.cap.cap}
            valueText={`${formatNumber(run.cap.applied)} of ${formatNumber(run.cap.cap)}`}
            note="prepare stops at the cap"
          />
        ) : null}
      </div>
      {run.jobs.length ? (
        <ol className={styles.jobList} aria-label="Jobs in this run">
          {run.jobs.map((row, i) => (
            <JobRowView key={row.job_id} row={row} n={i + 1} />
          ))}
        </ol>
      ) : (
        <p className={styles.sub}>Picking the first job…</p>
      )}
      <div className={styles.footNote}>
        {queued ? "" : "No more queued · "}
        Cancel waits for a safe point, then the run stops as Cancelled
      </div>
      <LogPane
        label="Live run output"
        empty="Waiting for output…"
        lines={lines.map((l) => ({
          key: l.key,
          text: l.text,
          prefix: l.attempt ? `job ${l.attempt}` : undefined,
          error: l.error,
        }))}
      />
    </section>
  );
}
