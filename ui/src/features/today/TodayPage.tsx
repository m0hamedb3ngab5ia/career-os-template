import { Link, useSearchParams } from "react-router";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { EmptyState } from "../../kit/EmptyState";
import { formatLongDate } from "../../lib/dates";
import { formatCount } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { useBatch } from "../pipeline/batch/api";
import { errorText, useToday, useTodayStatus } from "./api";
import { HeaderActions } from "./HeaderActions";
import { groupByJob } from "./actions";
import { NeedsYou } from "./NeedsYou";
import { NextScheduled } from "./NextScheduled";
import { PausedBanner } from "./PausedBanner";
import { PipelineChart } from "./PipelineChart";
import { RecentRuns } from "./RecentRuns";
import styles from "./Today.module.css";
import type { ActionItem } from "./types";

/** Route `/` (docs/UI.md "Today"; mockup Main / TodayDark). */
export function TodayPage() {
  const now = useNow(60_000);
  const status = useTodayStatus();
  const today = useToday();
  const s = status.data;
  const batchId = useSearchParams()[0].get("batch") ?? undefined;
  const batch = useBatch(batchId);
  const jobIds = batchId ? (batch.data?.selected.map((r) => r.job_id) ?? []) : undefined;
  const subtitle = today.data ? `${formatLongDate(now)} · ${headline(today.data.actions ?? [])}` : formatLongDate(now);

  return (
    <Page title="Today" subtitle={subtitle} actions={<HeaderActions queue={today.data?.prepare_queue ?? (today.data ? { total: null, error: null } : undefined)} paused={!!s?.paused} />}>
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
        <div className={styles.columns}>
          <div className={styles.main}>
            {batchId ? (
              <p className={styles.batchNote}>
                Only jobs in <Link to={`/pipeline/batch/${encodeURIComponent(batchId)}`}>{batch.data?.name || "this batch"}</Link> ·{" "}
                <Link to="/">Show all</Link>
              </p>
            ) : null}
            <NeedsYou jobIds={jobIds} />
          </div>
          {s ? (
            <aside className={styles.side} aria-label="Runs and pipeline">
              <RecentRuns runs={s.recent_runs ?? []} now={now} />
              <NextScheduled schedule={s.schedule ?? {}} catchUp={s.catch_up} now={now} />
              <PipelineChart columns={s.pipeline?.columns ?? []} />
            </aside>
          ) : null}
        </div>
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
