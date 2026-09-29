import { Moon } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { Button } from "../../kit/Button";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { useToast } from "../../kit/Toast";
import { formatClock, formatRelative, formatWhen } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { useScheduleAction } from "./api";
import { SCHEDULE_NAMES, cadence } from "./labels";
import styles from "./Runs.module.css";
import type { Schedule } from "./types";
import { help } from "../job-detail/actionHelp";

interface SchedulePanelProps {
  schedule: Schedule | undefined;
  /** The kind of the batch running right now: its row says "running now". */
  runningKind?: string | null;
}

/** Next time per scheduled job, the LaunchAgent that runs `careeros tick`, quiet hours; edits live in Settings › Runs. */
export function SchedulePanel({ schedule, runningKind }: SchedulePanelProps) {
  const now = useNow(30_000);
  const action = useScheduleAction();
  const toast = useToast();
  const [asking, setAsking] = useState<"install" | "uninstall" | null>(null);
  const [warning, setWarning] = useState<string | null>(null); // install succeeded but the server flagged a problem
  const trigger = useRef<HTMLButtonElement>(null); // Install or Uninstall, whichever is shown

  function run(which: "install" | "uninstall") {
    setWarning(null);
    action.mutate(which, {
      onSuccess: (out) => {
        const warn = typeof out?.warning === "string" && out.warning ? out.warning : null;
        setWarning(warn);
        const done = which === "install" ? "Scheduler installed" : "Scheduler uninstalled";
        toast.show({ message: warn ? `${done} with a warning.` : `${done}.` });
      },
      onSettled: () => setAsking(null),
    });
  }

  const agent = !schedule
    ? ""
    : schedule.installed && schedule.loaded
      ? "Scheduler on"
      : schedule.installed
        ? "Scheduler installed but not loaded"
        : "Scheduler not installed: nothing runs on its own";
  const tick = schedule?.last_tick ? `last tick ${formatRelative(schedule.last_tick, now)}` : "no tick yet";

  return (
    <section className={styles.card} aria-labelledby="sched-h">
      <div className={styles.cardHeadInline}>
        <h2 id="sched-h" className={styles.h2Inline}>
          Schedule
        </h2>
        <Link to="/settings/runs">Edit schedule</Link>
      </div>
      <ul className={styles.plainList}>
        {(schedule?.jobs ?? []).map((j) => {
          const next = !j.enabled
            ? "off"
            : runningKind === j.kind
              ? "running now"
              : j.next
                ? `next ${formatWhen(j.next, now)}`
                : "—";
          const desc =
            j.kind === "inbox_sync" && !j.enabled
              ? `${cadence(j)} · off until inbox sync is ready`
              : cadence(j);
          return (
            <li key={j.kind} className={styles.row}>
              <div className={styles.grow}>
                <div>{SCHEDULE_NAMES[j.kind] ?? j.kind}</div>
                <div className={styles.caption}>{desc}</div>
              </div>
              <span className={styles.rowMeta}>{next}</span>
            </li>
          );
        })}
      </ul>
      {schedule?.quiet_hours ? (
        <div className={styles.footNoteIcon}>
          <Moon size={13} strokeWidth={1.7} aria-hidden="true" />
          Claude runs skip quiet hours {formatClock(schedule.quiet_hours.start)}–{formatClock(schedule.quiet_hours.end)}{" "}
          so your daytime quota stays free
        </div>
      ) : null}
      {schedule ? (
        <div className={styles.agent}>
          <div className={styles.grow}>
            <div>{agent}</div>
            <div className={styles.caption}>{tick}</div>
          </div>
          {asking === null ? (
            schedule.installed ? (
              <Button ref={trigger} size="small" variant="destructive" {...help("uninstallSchedule")} onClick={() => setAsking("uninstall")}>
                Uninstall
              </Button>
            ) : (
              <Button ref={trigger} size="small" {...help("installSchedule")} onClick={() => setAsking("install")}>
                Install
              </Button>
            )
          ) : null}
        </div>
      ) : null}
      {asking === "install" ? (
        <ConfirmPanel
          question="Install the scheduler? It checks for work every few minutes while you're logged in."
          cancelLabel="Not now"
          confirmLabel="Install"
          confirmVariant="primary"
          pending={action.isPending}
          returnFocusRef={trigger}
          onCancel={() => setAsking(null)}
          onConfirm={() => run("install")}
        />
      ) : null}
      {asking === "uninstall" ? (
        <ConfirmPanel
          question="Uninstall the scheduler? Scheduled runs stop until you install it again."
          cancelLabel="Keep it"
          confirmLabel="Uninstall"
          pending={action.isPending}
          returnFocusRef={trigger}
          onCancel={() => setAsking(null)}
          onConfirm={() => run("uninstall")}
        />
      ) : null}
      {warning ? (
        <p role="status" aria-label="Scheduler warning" className={styles.fix}>
          {warning}
        </p>
      ) : null}
      {action.error ? (
        <p role="alert" className={styles.fix}>
          {action.error.message}
        </p>
      ) : null}
    </section>
  );
}
