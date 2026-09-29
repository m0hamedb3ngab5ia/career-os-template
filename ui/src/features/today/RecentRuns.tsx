import { Link } from "react-router";
import { StopReasonChip } from "../../kit/chips";
import { formatWhen } from "../../lib/dates";
import { formatCount } from "../../lib/format";
import { runKindLabel } from "./kinds";
import type { RunRow } from "./types";
import styles from "./Today.module.css";

const MAX = 5;

function reasonOf(r: RunRow): string | null {
  if (r.interrupted) return "interrupted";
  if (r.status === "running") return "running";
  return r.stop_reason ?? r.status ?? null;
}

function detailOf(r: RunRow): string | null {
  if (r.detail) return r.detail;
  if (r.attempted) return `${formatCount(r.ok ?? 0)} of ${formatCount(r.attempted)} jobs`;
  return null;
}

export function RecentRuns({ runs, now }: { runs: RunRow[]; now: Date }) {
  const shown = runs.slice(0, MAX);
  return (
    <section className={styles.panel} aria-labelledby="recent-runs-title">
      <div className={styles.panelHead}>
        <h2 id="recent-runs-title" className={styles.h2}>
          Recent runs
        </h2>
        <Link to="/automation" className={styles.headLink}>
          All runs
        </Link>
      </div>
      {shown.length === 0 ? (
        <p className={styles.plain}>No runs yet</p>
      ) : (
        <ul className={styles.rows}>
          {shown.map((r) => {
            const detail = detailOf(r);
            const when = formatWhen(r.started_at, now);
            return (
              <li key={r.id} className={styles.runRow}>
                <div className={styles.runMain}>
                  <div className={styles.runLine}>
                    <span className={styles.strong}>{runKindLabel(r.kind)}</span>
                    <StopReasonChip reason={reasonOf(r)} />
                  </div>
                  {detail ? (
                    <div className={styles.runDetail} title={detail}>
                      {detail}
                    </div>
                  ) : null}
                </div>
                {when ? (
                  <time className={`${styles.time} tabular`} dateTime={r.started_at ?? undefined}>
                    {when}
                  </time>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
