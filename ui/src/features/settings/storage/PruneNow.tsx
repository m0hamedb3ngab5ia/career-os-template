import { Link } from "react-router";
import { ApiError } from "../../../api/client";
import { Button } from "../../../kit/Button";
import { ConfirmPanel } from "../../../kit/ConfirmPanel";
import { useToast } from "../../../kit/Toast";
import { usePrunePlan, usePruneStart } from "../api";
import { formatBytes, humanize, plural } from "../format";
import styles from "./storage.module.css";

const SHOWN = 200; // the rest are summarized; the totals above cover everything

const ACTIONS: Record<string, string> = {
  delete_screenshots: "Screenshots of a closed job",
  stub_posting: "Posting trimmed to a stub",
  delete_run_logs: "Run logs",
  delete_run: "Old run summary",
};

/** Prune now: the dry-run list first (`careeros prune`), then a confirm, then `careeros prune --yes` as a step run. */
export function PruneNow() {
  const toast = useToast();
  const plan = usePrunePlan();
  const start = usePruneStart();
  const p = plan.data;

  return (
    <section className={styles.panel} aria-labelledby="prune-title">
      <div className={styles.panelHead}>
        <h2 id="prune-title" className={styles.panelTitle}>
          Prune now
        </h2>
        <span className={styles.panelSub}>
          Applies the retention rules below. Prune never touches applied jobs’ submitted snapshots, your profile or config.
        </span>
      </div>
      {!p ? (
        <div className={styles.pruneActions}>
          <Button onClick={() => plan.mutate()} pending={plan.isPending} pendingLabel="Checking…">
            See what would be removed
          </Button>
          {plan.isError ? (
            <span role="alert" className={styles.panelSub}>
              {plan.error instanceof ApiError ? plan.error.message : "Couldn't check. Try again."}
            </span>
          ) : null}
        </div>
      ) : p.items.length === 0 ? (
        <div className={styles.pruneActions}>
          <span className={styles.panelSub} role="status">
            Nothing to prune right now.
          </span>
          <Button size="small" onClick={() => plan.reset()}>
            Done
          </Button>
        </div>
      ) : (
        <>
          <p role="status" className={styles.panelSub}>
            {plural(p.summary.files, "file")} ({formatBytes(p.summary.bytes)}) from {plural(p.summary.jobs, "job")}
            {p.summary.runs ? ` and ${plural(p.summary.runs, "run")}` : ""}.
          </p>
          <ul className={styles.pruneList} aria-label="What prune would remove">
            {p.items.slice(0, SHOWN).map((it, i) => (
              <li key={`${it.job_id}-${it.run_id}-${it.action}-${i}`}>
                <span>
                  {ACTIONS[it.action] ?? humanize(it.action)} ·{" "}
                  <code translate="no">{it.run_id || it.job_id}</code>
                </span>
                <span>{formatBytes(it.bytes)}</span>
              </li>
            ))}
            {p.items.length > SHOWN ? <li>and {plural(p.items.length - SHOWN, "more item")}</li> : null}
          </ul>
          <div className={styles.pruneActions}>
            <ConfirmPanel
              question={`Remove ${plural(p.summary.files, "file")} (${formatBytes(p.summary.bytes)})? This can’t be undone.`}
              cancelLabel="Cancel"
              confirmLabel="Prune"
              pending={start.isPending}
              onCancel={() => plan.reset()}
              onConfirm={() =>
                start.mutate(undefined, {
                  onSuccess: () => {
                    plan.reset();
                    toast.show({ message: "Prune started. Progress is on the Runs page." });
                  },
                  onError: (e) =>
                    toast.show({ message: e instanceof ApiError ? e.message : "Couldn't start prune. Try again." }),
                })
              }
            />
          </div>
        </>
      )}
      <p className={styles.panelSub}>
        Past prunes are in <Link to="/automation">Automation</Link>.
      </p>
    </section>
  );
}
