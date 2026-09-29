import { useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { Page } from "../../../app/PageHeader";
import { Button } from "../../../kit/Button";
import { ConfirmPanel } from "../../../kit/ConfirmPanel";
import { EmptyState } from "../../../kit/EmptyState";
import { formatCount } from "../../../lib/format";
import { errorText } from "../../today/api";
import { useBatch, useBatchAction, type Batch } from "./api";
import styles from "./batch.module.css";

// docs/design/ui-redesign.md §4.2 Progress / Review queue / Completed / Pause-cancel / Retry. Job states come from
// runs/batches.py: pending, waiting, working, done, needs_you, skipped, failed, cancelled (null = not started).

type Row = Batch["selected"][number];
const BUCKETS = [
  ["done", "done"],
  ["working", "working"],
  ["needs_you", "need you"],
  ["waiting", "waiting"],
  ["skipped", "skipped"],
  ["failed", "failed"],
  ["cancelled", "cancelled"],
] as const;
type Bucket = (typeof BUCKETS)[number][0];
const STATE_LABEL: Record<Bucket, string> = {
  done: "Done", working: "Working", needs_you: "Needs you", waiting: "Waiting", skipped: "Skipped", failed: "Failed",
  cancelled: "Cancelled",
};
const STAGE_LABEL: Record<string, string> = { score: "Score", prepare: "Prepare documents", apply: "Fill application" };
const STATUS_LABEL: Record<string, string> = {
  queued: "Ready to start", ready: "Ready to start", running: "Running", paused: "Paused", cancelled: "Cancelled",
  done: "Done",
};
const RETRYABLE = new Set(["failed", "cancelled"]);

/** Not started and between-runs both wait in the queue. */
export const bucketOf = (r: Row): Bucket => (!r.state || r.state === "pending" ? "waiting" : (r.state as Bucket));

/** "25 selected · 12 done · 4 working …", zero buckets left out. */
export function countsLine(rows: readonly Row[]): string {
  const n = (b: Bucket) => rows.filter((r) => bucketOf(r) === b).length;
  return [`${formatCount(rows.length)} selected`, ...BUCKETS.filter(([b]) => n(b)).map(([b, l]) => `${formatCount(n(b))} ${l}`)].join(" · ");
}

/** Route `/pipeline/batch/:id`: live progress of one batch (refetched on the SSE `changed` event). */
export function BatchProgressPage() {
  const { id = "" } = useParams();
  const batch = useBatch(id);
  const act = useBatchAction(id);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const b = batch.data;

  if (!b) {
    return (
      <Page title="Batch" busy={batch.isPending}>
        {batch.isError ? (
          <EmptyState title="Couldn’t load this batch" action={<Button size="small" onClick={() => void batch.refetch()}>Retry</Button>}>
            {errorText(batch.error)}
          </EmptyState>
        ) : null}
      </Page>
    );
  }

  const status = b.status ?? "queued";
  const open = status !== "done" && status !== "cancelled";
  const review = b.selected.filter((r) => bucketOf(r) === "needs_you");
  const retryable = b.selected.filter((r) => RETRYABLE.has(r.state ?? "")).length;
  const pending = act.isPending;
  const run = (a: "start" | "pause" | "cancel") => act.mutate(a, { onSuccess: () => setConfirmCancel(false) });
  const retry = () => act.mutate("retry", { onSuccess: () => act.mutate("start") });
  const requested = b.requested === "pause" ? "Pausing after the current job…" : b.requested === "cancel" ? "Cancelling after the current step…" : null;

  return (
    <Page
      title={b.name || "Batch"}
      subtitle={[STATUS_LABEL[status] ?? status, b.reason, countsLine(b.selected)].filter(Boolean).join(" · ")}
    >
      <div className={styles.builder}>
        <div className={styles.row}>
          {status === "running" ? (
            <Button onClick={() => run("pause")} disabled={pending || !!b.requested}>Pause after this job</Button>
          ) : open ? (
            <Button variant="primary" onClick={() => run("start")} disabled={pending}>
              {status === "paused" ? "Resume" : "Start batch"}
            </Button>
          ) : null}
          {open ? (
            <Button ref={cancelRef} variant="destructive" onClick={() => setConfirmCancel(true)} disabled={pending || confirmCancel}>
              Cancel batch
            </Button>
          ) : null}
          {!open && retryable ? (
            <Button variant="primary" onClick={retry} disabled={pending}>
              Retry {formatCount(retryable)} {retryable === 1 ? "job" : "jobs"}
            </Button>
          ) : null}
          {review.length ? (
            <Link to={`/?batch=${encodeURIComponent(id)}`}>Review {formatCount(review.length)} in Today</Link>
          ) : null}
        </div>
        {requested ? <p className={styles.note} role="status">{requested}</p> : null}
        {act.isError ? <p className={styles.note} role="alert">Couldn’t update the batch: {errorText(act.error)}</p> : null}
        {confirmCancel ? (
          <ConfirmPanel
            question="Cancel this batch?"
            detail="Jobs not yet started are dropped; the current job finishes its step. Failed and cancelled jobs can be retried later."
            cancelLabel="Keep running"
            confirmLabel="Cancel batch"
            onCancel={() => setConfirmCancel(false)}
            onConfirm={() => run("cancel")}
            pending={pending}
            returnFocusRef={cancelRef}
          />
        ) : null}
        <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr><th scope="col">Job</th><th scope="col">Stage</th><th scope="col">State</th><th scope="col">Reason</th></tr>
          </thead>
          <tbody>
            {b.selected.map((r) => (
              <tr key={r.job_id}>
                <td><Link to={`/jobs/${encodeURIComponent(r.job_id)}`}>{r.company} · {r.title}</Link></td>
                <td>{STAGE_LABEL[r.stage] ?? r.stage}</td>
                <td>{STATE_LABEL[bucketOf(r)] ?? r.state}</td>
                <td>{r.reason ?? r.result ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </Page>
  );
}
