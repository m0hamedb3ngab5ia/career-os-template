import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { EmptyState } from "../../kit/EmptyState";
import { formatLongDate } from "../../lib/dates";
import { formatCount } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { errorText, useToday, useTodayStatus } from "./api";
import { HeaderActions } from "./HeaderActions";
import { NeedsYou } from "./NeedsYou";
import { NextScheduled } from "./NextScheduled";
import { PausedBanner } from "./PausedBanner";
import { PipelineChart } from "./PipelineChart";
import { RecentRuns } from "./RecentRuns";
import { StatTiles } from "./StatTiles";
import styles from "./Today.module.css";

/** Route `/` (docs/UI.md "Today"; mockup Main / TodayDark). */
export function TodayPage() {
  const now = useNow(60_000);
  const status = useTodayStatus();
  const today = useToday();
  const s = status.data;
  const open = today.data ? (today.data.actions ?? []).length : s ? (s.tiles?.needs_you?.value ?? 0) : null;
  const subtitle =
    open === null ? formatLongDate(now) : `${formatLongDate(now)} · ${formatCount(open)} ${open === 1 ? "item needs" : "items need"} you`;

  return (
    <Page title="Today" subtitle={subtitle} actions={<HeaderActions queue={today.data?.prepare_queue ?? (today.data ? { total: null, error: null } : undefined)} paused={!!s?.paused} />}>
      <div className={styles.stack}>
        {s?.paused ? <PausedBanner paused={s.paused} now={now} /> : null}
        {status.isPending ? (
          <div className={styles.tiles} role="img" aria-label="Loading today’s numbers">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className={styles.skeletonTile} />
            ))}
          </div>
        ) : status.isError ? (
          <div className={styles.panel}>
            <EmptyState
              title="Couldn’t load today’s numbers"
              action={
                <Button size="small" onClick={() => void status.refetch()}>
                  Retry
                </Button>
              }
            >
              {errorText(status.error)}
            </EmptyState>
          </div>
        ) : (
          <StatTiles tiles={s?.tiles} now={now} />
        )}
        <div className={styles.columns}>
          <div className={styles.main}>
            <NeedsYou />
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
