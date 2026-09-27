import { Clock } from "lucide-react";
import { Link } from "react-router";
import { Page } from "../../app/PageHeader";
import { useCurrentRun, useMeta, useSchedule } from "./api";
import { CatchUpBanner, PauseAllControl, PausedBanner } from "./Banners";
import { CurrentRunCard } from "./CurrentRunCard";
import { HistoryCard } from "./HistoryCard";
import styles from "./Runs.module.css";
import { SchedulePanel } from "./SchedulePanel";
import { StartRunCard } from "./StartRunCard";
import { UpNextCard } from "./UpNextCard";

/** Runs (docs/UI.md screen 8, Runs artboard): now, start, schedule, up next, history, pause and catch-up. */
export function RunsPage() {
  const meta = useMeta();
  const current = useCurrentRun();
  const schedule = useSchedule();
  const run = current.data?.id ? current.data : null;
  const paused = schedule.data?.paused ?? null;
  const catchUp = schedule.data?.catch_up ?? null;
  return (
    <Page
      title="Runs"
      subtitle="Scheduled runs score and prepare only · uses your Claude Code subscription, no API calls"
      actions={
        <>
          <PauseAllControl paused={paused} />
          <Link to="/settings/runs" className={styles.linkButton}>
            <Clock size={14} strokeWidth={1.7} aria-hidden="true" />
            Schedule settings
          </Link>
        </>
      }
    >
      <div className={styles.stack}>
        {paused ? <PausedBanner paused={paused} /> : null}
        {catchUp && !paused ? <CatchUpBanner record={catchUp} /> : null}
        {current.error ? (
          <p role="alert" className={styles.fix}>
            {current.error.message}
          </p>
        ) : null}
        <div className={styles.topRow}>
          <CurrentRunCard key={run?.id ?? "idle"} run={run} />
          <div className={styles.side}>
            <StartRunCard meta={meta.data} schedule={schedule.data} paused={Boolean(paused)} />
            <SchedulePanel schedule={schedule.data} runningKind={run?.kind} />
          </div>
        </div>
        <div className={styles.bottomRow}>
          <UpNextCard />
          <HistoryCard />
        </div>
      </div>
    </Page>
  );
}
