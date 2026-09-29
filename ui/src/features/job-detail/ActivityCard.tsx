import { StatusChip } from "../../kit/chips";
import { Details } from "../../kit/Details";
import { formatCount, formatDateTime } from "../../lib/format";
import { Card, Muted } from "./Card";
import styles from "./JobDetail.module.css";
import type { ActivityEntry, HistoryEntry } from "./types";

/** How many log entries show before "Show all". */
export const ACTIVITY_PREVIEW = 3;

function ActivityRow({ entry }: { entry: ActivityEntry }) {
  // Title only; the time, component and raw log line sit behind the click.
  return (
    <li>
      <Details summary={entry.label || entry.message}>
        <p className={styles.caption}>
          {formatDateTime(entry.at) ?? entry.at} · <span translate="no">{entry.component}</span>
        </p>
        <p className={styles.caption} translate="no">{`[${entry.component}] ${entry.message}`}</p>
      </Details>
    </li>
  );
}

export function ActivityCard({ activity, history }: { activity: ActivityEntry[]; history: HistoryEntry[] }) {
  const changes = history.toReversed();
  const recent = activity.slice(0, ACTIVITY_PREVIEW);
  const older = activity.slice(ACTIVITY_PREVIEW);
  return (
    <Card title="Activity">
      {activity.length ? (
        <>
          <ul className={styles.list} aria-label="Recent activity">
            {recent.map((a, i) => (
              <ActivityRow key={`${a.at}-${i}`} entry={a} />
            ))}
          </ul>
          {older.length ? (
            <details className={styles.details}>
              <summary>Show all ({formatCount(activity.length)})</summary>
              <ul className={styles.list} aria-label="Older activity">
                {older.map((a, i) => (
                  <ActivityRow key={`${a.at}-${i}`} entry={a} />
                ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : (
        <Muted>No activity logged yet.</Muted>
      )}
      <h3 className={styles.h3}>Status history</h3>
      {changes.length ? (
        <ul className={styles.list}>
          {changes.map((h, i) => (
            <li key={`${h.at}-${i}`} className={styles.logRow}>
              <span className={styles.logTime}>{formatDateTime(h.at) ?? h.at}</span>
              <span className={styles.grow}>
                <StatusChip status={h.status} />
                {h.note ? <span className={styles.sec}> {h.note}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <Muted>No status changes yet.</Muted>
      )}
    </Card>
  );
}
