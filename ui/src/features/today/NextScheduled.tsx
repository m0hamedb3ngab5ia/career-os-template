import { Moon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Button } from "../../kit/Button";
import { useToast } from "../../kit/Toast";
import { formatWhen } from "../../lib/dates";
import { formatCount } from "../../lib/format";
import { errorText, useCatchUp } from "./api";
import { kindLabel, SCHEDULE_ORDER } from "./kinds";
import type { CatchUp, TodayStatus } from "./types";
import styles from "./Today.module.css";

type Schedule = NonNullable<TodayStatus["schedule"]>;

export function NextScheduled({ schedule, catchUp, now }: { schedule: Schedule; catchUp: CatchUp | null | undefined; now: Date }) {
  const next = schedule.next ?? {};
  const kinds = [...SCHEDULE_ORDER, ...Object.keys(next).filter((k) => !(SCHEDULE_ORDER as readonly string[]).includes(k))];
  return (
    <section className={styles.panel} aria-labelledby="next-scheduled-title">
      <div className={styles.panelHead}>
        <h2 id="next-scheduled-title" className={styles.h2}>
          Next scheduled
        </h2>
        <Link to="/automation" className={styles.headLink}>
          Run schedule
        </Link>
      </div>
      <CatchUpBanner catchUp={catchUp} now={now} />
      {schedule.error ? (
        <p className={styles.plain}>Schedule can’t be read: {schedule.error}. Check Settings › Runs.</p>
      ) : (
        <dl className={styles.rows}>
          {kinds.map((k) => (
            <div key={k} className={styles.schedRow}>
              <dt>{kindLabel(k)}</dt>
              <dd className="tabular">{formatWhen(next[k], now) ?? "off"}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

function CatchUpBanner({ catchUp, now }: { catchUp: CatchUp | null | undefined; now: Date }) {
  const run = useCatchUp();
  const toast = useToast();
  const [note, setNote] = useState("");
  const entries = Object.entries(catchUp?.kinds ?? {});
  const total = entries.reduce((n, [, v]) => n + (v.slots ?? 1), 0);

  function go(dismiss: boolean) {
    run.mutate(dismiss, {
      onSuccess: (res) =>
        setNote(
          dismiss
            ? "Missed runs skipped. They run at their next scheduled time."
            : res?.started === false
              ? "Nothing left to catch up."
              : "Catch-up run started.",
        ),
      onError: (e) => toast.show({ message: `Couldn’t ${dismiss ? "skip missed runs" : "start the catch-up run"}: ${errorText(e)}` }),
    });
  }

  return (
    <>
      <div className={styles.note} role="status">
        {note}
      </div>
      {entries.length && !note ? (
        <div className={styles.catchUp}>
          <p className={styles.catchUpTitle}>
            <span className={styles.bannerIcon}>
              <Moon size={14} strokeWidth={1.7} aria-hidden="true" />
            </span>
            {formatCount(total)} {total === 1 ? "run" : "runs"} missed
          </p>
          <ul className={styles.catchUpList}>
            {entries.map(([kind, v]) => {
              const since = formatWhen(v.first_missed, now);
              return (
                <li key={kind}>
                  {kindLabel(kind)}: {formatCount(v.slots ?? 1)} missed{since ? ` since ${since}` : ""}
                </li>
              );
            })}
          </ul>
          <div className={styles.catchUpButtons}>
            <Button
              size="small"
              variant="primary"
              pending={run.isPending && run.variables === false}
              pendingLabel="Starting…"
              disabled={run.isPending}
              onClick={() => go(false)}
            >
              Catch up now
            </Button>
            <Button
              size="small"
              pending={run.isPending && run.variables === true}
              pendingLabel="Skipping…"
              disabled={run.isPending}
              onClick={() => go(true)}
            >
              Skip missed runs
            </Button>
          </div>
        </div>
      ) : null}
    </>
  );
}
