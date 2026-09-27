import { StatusChip } from "../../kit/chips";
import { formatDateTime } from "../../lib/format";
import { Card, Muted } from "./Card";
import styles from "./JobDetail.module.css";
import type { ActivityEntry, HistoryEntry } from "./types";

export function ActivityCard({ activity, history }: { activity: ActivityEntry[]; history: HistoryEntry[] }) {
  const changes = history.toReversed();
  return (
    <Card title="Activity">
      {activity.length ? (
        <ul className={styles.list}>
          {activity.map((a, i) => (
            <li key={`${a.at}-${i}`} className={styles.logRow}>
              <span className={styles.logTime}>{formatDateTime(a.at) ?? a.at}</span>
              <span className={styles.grow}>{a.message}</span>
              <span translate="no" className={styles.component}>
                {a.component}
              </span>
            </li>
          ))}
        </ul>
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
