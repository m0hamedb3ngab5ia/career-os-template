import { ChevronLeft } from "lucide-react";
import { Link, useParams } from "react-router";
import { Page } from "../../app/PageHeader";
import { StopReasonChip } from "../../kit/chips";
import { EmptyState } from "../../kit/EmptyState";
import { humanize } from "../../kit/labels";
import { formatDuration, formatWhen } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { useRunDetail, useRunStream } from "./api";
import { runSummary } from "./HistoryCard";
import { STOP_FIX, kindLabel, needsYou, runChipCode, triggerLabel } from "./labels";
import { LogPane } from "./LogPane";
import styles from "./Runs.module.css";

/** One run: its attempts (job, outcome, duration, session id, detail) and run.log; live while it runs. */
export function RunDetailPage() {
  const { runId = "" } = useParams();
  const { data: run, error, isPending } = useRunDetail(runId);
  const now = useNow(60_000);
  const live = run?.state === "running";
  const stream = useRunStream(runId, live);
  const back = (
    <Link to="/automation" className={styles.back}>
      <ChevronLeft size={14} strokeWidth={1.7} aria-hidden="true" />
      All runs
    </Link>
  );
  if (error || (!isPending && !run)) {
    return (
      <Page title="Run not found">
        {back}
        <EmptyState title="No run with this id">{error?.message ?? "It may have been pruned."}</EmptyState>
      </Page>
    );
  }
  if (!run) {
    return (
      <Page busy title="Run">
        {back}
        <p className={styles.sub}>Loading…</p>
      </Page>
    );
  }
  const code = runChipCode(run);
  const trig = triggerLabel(run.trigger);
  const logLines = live
    ? stream.lines.map((l) => ({ key: l.key, text: l.text, prefix: l.attempt ? `job ${l.attempt}` : undefined, error: l.error }))
    : run.log
        .split("\n")
        .filter((l) => l.trim())
        .map((text, i) => ({ key: i, text }));
  return (
    <Page
      title={`${kindLabel(run.kind)} run`}
      subtitle={[trig, run.started_at ? `started ${formatWhen(run.started_at, now)}` : null, formatDuration(run.duration_s)]
        .filter(Boolean)
        .join(" · ")}
      actions={<StopReasonChip reason={code} />}
    >
      <div className={styles.stack}>
        {back}
        <section className={styles.card} aria-labelledby="sum-h">
          <h2 id="sum-h" className={styles.h2}>
            Summary
          </h2>
          <p>{runSummary(run) || "—"}</p>
          {code && STOP_FIX[code] && !needsYou(run) ? <p className={styles.caption}>{STOP_FIX[code]}</p> : null}
          {run.detail && run.kind !== "scout" && run.kind !== "tracker" && run.kind !== "prune" ? (
            <p className={styles.caption}>{run.detail}</p>
          ) : null}
          {(run.warnings ?? []).map((w) => (
            <p key={w} className={styles.fix}>
              {w}
            </p>
          ))}
        </section>
        <section className={styles.card} aria-labelledby="att-h">
          <h2 id="att-h" className={styles.h2}>
            Attempts
          </h2>
          {run.attempts.length === 0 ? (
            <p className={styles.sub}>No jobs attempted.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col" className={styles.numCol}>
                      #
                    </th>
                    <th scope="col">Job</th>
                    <th scope="col">Outcome</th>
                    <th scope="col" className={styles.right}>
                      Duration
                    </th>
                    <th scope="col">Session</th>
                    <th scope="col">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {run.attempts.map((a) => (
                    <tr key={a.n}>
                      <td className={styles.numCol}>{a.n}</td>
                      <td>
                        <Link to={`/jobs/${a.job_id}`} className={styles.jobLink}>
                          <span className={styles.strong}>{a.company ?? a.job_id}</span>{" "}
                          <span className={styles.sec}>{a.title}</span>
                        </Link>
                      </td>
                      <td>{a.outcome === "ok" ? "OK" : humanize(a.outcome)}</td>
                      <td className={`${styles.right} tabular`}>{formatDuration(a.duration_s) ?? "—"}</td>
                      <td className={styles.mono} translate="no">
                        {a.session_id ?? "—"}
                      </td>
                      <td className={styles.detailCell}>{a.detail || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section className={styles.card} aria-labelledby="log-h">
          <h2 id="log-h" className={styles.h2}>
            {live ? "Live output" : "Log"}
          </h2>
          <LogPane label={live ? "Live run output" : "Run log"} lines={logLines} empty="Nothing logged." live={live} />
        </section>
      </div>
    </Page>
  );
}
