import { Clock } from "lucide-react";
import { Link, useSearchParams } from "react-router";
import { Page } from "../../app/PageHeader";
import { Details } from "../../kit/Details";
import { HUMAN } from "../../kit/labels";
import { useCurrentRun, useMeta, useSchedule } from "./api";
import { CatchUpBanner, PauseAllControl, PausedBanner } from "./Banners";
import { CurrentRunCard } from "./CurrentRunCard";
import { HistoryCard } from "./HistoryCard";
import styles from "./Runs.module.css";
import { SchedulePanel } from "./SchedulePanel";
import { StartRunCard } from "./StartRunCard";
import { UpNextCard } from "./UpNextCard";

/** Automation (design doc 3, was Runs): status, schedule, up next; manual runs and history under Advanced. */
export function RunsPage() {
  const meta = useMeta();
  const current = useCurrentRun();
  const schedule = useSchedule();
  const run = current.data?.id ? current.data : null;
  const paused = schedule.data?.paused ?? null;
  const catchUp = schedule.data?.catch_up ?? null;
  const [params] = useSearchParams();
  return (
    <Page
      title={HUMAN.term.runs}
      subtitle="What runs by itself, when, and whether it worked"
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
            <SchedulePanel schedule={schedule.data} runningKind={run?.kind} />
          </div>
        </div>
        <UpNextCard />
        <Details summary="Advanced" defaultOpen={params.has("kind")}>
          <p>Scheduled runs score and prepare only · uses your Claude Code subscription, no API calls</p>
          <div className={styles.bottomRow}>
            <StartRunCard meta={meta.data} schedule={schedule.data} paused={Boolean(paused)} />
            <HistoryCard />
          </div>
        </Details>
      </div>
    </Page>
  );
}
