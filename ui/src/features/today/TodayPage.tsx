import { Link, useSearchParams } from "react-router";
import { ApiError } from "../../api/client";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { EmptyState } from "../../kit/EmptyState";
import { formatLongDate } from "../../lib/dates";
import { formatCount } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { useBatch } from "../pipeline/batch/api";
import { errorText, useToday, useTodayStatus } from "./api";
import { groupByJob } from "./actions";
import { NeedsYou } from "./NeedsYou";
import { PausedBanner } from "./PausedBanner";
import { SetupCard, useSetupOpen } from "./SetupCard";
import { TopPicks } from "./TopPicks";
import { formatWhen } from "../../lib/dates";
import styles from "./Today.module.css";
import type { ActionItem, PipelineColumn, RunRow } from "./types";

/** Route `/` (docs/UI.md "Today"; mockup Main / TodayDark). */
export function TodayPage() {
  const now = useNow(60_000);
  const status = useTodayStatus();
  const today = useToday();
  const s = status.data;
  const setupOpen = useSetupOpen();
  const batchId = useSearchParams()[0].get("batch") ?? undefined;
  const batch = useBatch(batchId);
  // Unknown/failed batch: say so and show every task; still loading: show none (not a false "Nothing needs you").
  const jobIds = batchId && !batch.isError ? batch.data?.selected.map((r) => r.job_id) : undefined;
  const batchMissing = batch.error instanceof ApiError && batch.error.status === 404;
  const subtitle = today.data ? `${formatLongDate(now)} · ${headline(today.data.actions ?? [])}` : formatLongDate(now);

  return (
    <Page title="Today" subtitle={subtitle}>
      <div className={styles.stack}>
        {s?.paused ? <PausedBanner paused={s.paused} now={now} /> : null}
        {status.isError ? (
          <div className={styles.panel}>
            <EmptyState
              title="Couldn’t load automation status"
              action={
                <Button size="small" onClick={() => void status.refetch()}>
                  Retry
                </Button>
              }
            >
              {errorText(status.error)}
            </EmptyState>
          </div>
        ) : null}
        {setupOpen ? <SetupCard /> : null}
        {setupOpen === false ? <TopPicks picks={today.data?.top_picks ?? []} /> : null}
        {batchId ? (
          <p className={styles.batchNote}>
            Only jobs in <Link to={`/pipeline/batch/${encodeURIComponent(batchId)}`}>{batch.data?.name || "this batch"}</Link> ·{" "}
            <Link to="/">Show all</Link>
            {batch.isError ? (
              <span role="status"> · {batchMissing ? "Batch not found" : `Couldn’t load the batch: ${errorText(batch.error)}`}, showing all tasks</span>
            ) : null}
          </p>
        ) : null}
        {batchId && batch.isPending ? null : <NeedsYou jobIds={jobIds} />}
        {s ? <RecentActivity runs={s.recent_runs ?? []} now={now} /> : null}
        {s ? <JobSearch columns={s.pipeline?.columns ?? []} /> : null}
      </div>
    </Page>
  );
}

/** Headline sentence (replaces the stat tiles): "3 jobs need you · 1 other task". */
function headline(actions: ActionItem[]): string {
  const groups = groupByJob(actions);
  const jobs = groups.filter((g) => g.jobId !== null).length;
  const other = groups.find((g) => g.jobId === null)?.items.length ?? 0;
  const parts = [
    jobs ? `${formatCount(jobs)} ${jobs === 1 ? "job needs" : "jobs need"} you` : null,
    other ? `${formatCount(other)} other ${other === 1 ? "task" : "tasks"}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "nothing needs you";
}

const plural = (n: number, word: string) => `${formatCount(n)} ${word}${n === 1 ? "" : "s"}`;

/** Outcome of a finished run in plain words; null = not worth showing (running, housekeeping). */
export function outcome(r: RunRow): string | null {
  if (r.status === "running" || !r.kind) return null;
  const n = r.ok ?? 0;
  const found = /(\d+) new/.exec(r.detail ?? "")?.[1];
  const text: Record<string, string> = {
    scout: found ? `Found ${plural(Number(found), "new matching job")}` : "Found new jobs",
    prepare: n ? `Prepared ${plural(n, "application")}` : "Prepared applications",
    apply: n ? `Filled ${plural(n, "application")}` : "Filled applications",
    score: n ? `Checked ${plural(n, "job")}` : "Checked new jobs",
  };
  const t = text[r.kind];
  if (!t) return null;
  return r.status === "failed" || r.status === "error" ? `${t}, stopped early` : t;
}

function RecentActivity({ runs, now }: { runs: RunRow[]; now: Date }) {
  const rows = runs.flatMap((r) => {
    const t = outcome(r);
    return t ? [{ id: r.id, t, when: formatWhen(r.ended_at ?? r.started_at, now) }] : [];
  }).slice(0, 3);
  return (
    <section className={styles.panel} aria-labelledby="activity-title">
      <div className={styles.panelHead}>
        <h2 id="activity-title" className={styles.h2}>Recent activity</h2>
        <Link to="/runs" className={styles.headLink}>View all activity</Link>
      </div>
      {rows.length ? (
        <ul className={styles.plainList}>
          {rows.map((r) => (
            <li key={r.id} className={styles.oneLine}>
              <span>{r.t}</span>
              {r.when ? <span className={styles.caption}>{r.when}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.caption}>Nothing yet</p>
      )}
    </section>
  );
}

const sumOf = (cols: PipelineColumn[], statuses: string[]) =>
  cols.filter((c) => c.statuses.some((x) => statuses.includes(x))).reduce((t, c) => t + c.count, 0);

function JobSearch({ columns }: { columns: PipelineColumn[] }) {
  const line = [
    `${formatCount(sumOf(columns, ["found", "scored"]))} new matches`,
    `${formatCount(sumOf(columns, ["needs_review"]))} need review`,
    `${plural(sumOf(columns, ["applied", "screening", "interview"]), "application")} active`,
  ].join(" · ");
  return (
    <section className={`${styles.panel} ${styles.oneLine}`} aria-labelledby="search-title">
      <h2 id="search-title" className="sr-only">Job search</h2>
      <span>{line}</span>
      <Link to="/pipeline" className={styles.headLink}>View pipeline</Link>
    </section>
  );
}
