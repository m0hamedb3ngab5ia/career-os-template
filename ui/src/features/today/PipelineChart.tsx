import { describeCode, STATUSES } from "../../kit/labels";
import { formatCount } from "../../lib/format";
import type { PipelineColumn } from "./types";
import styles from "./Today.module.css";

// One series of magnitudes: horizontal bars on one scale (the largest column), each value printed as text next to
// its bar, so the numbers are read, not guessed. Bars are decoration for screen readers (aria-hidden); the list
// reads "Found 412". Colour marks the stage the way its status chip does (the name is always there, never
// colour alone). Column names come from the fixed board (ui/config.py DEFAULT_COLUMNS) via /api/status.

export function PipelineChart({ columns }: { columns: PipelineColumn[] }) {
  const top = columns.reduce<PipelineColumn | null>((m, c) => (!m || c.count > m.count ? c : m), null);
  const max = top?.count ?? 0;
  return (
    <section className={styles.panel} aria-labelledby="pipeline-title">
      <div className={styles.panelHead}>
        <h2 id="pipeline-title" className={styles.h2}>
          Pipeline
        </h2>
        {max > 0 && top ? (
          <span className={styles.caption}>
            Bars to scale of {formatCount(max)} ({top.name})
          </span>
        ) : null}
      </div>
      {max === 0 ? (
        <p className={styles.plain}>No jobs yet</p>
      ) : (
        <ul className={styles.bars}>
          {columns.map((c) => (
            <li key={c.name} className={styles.bar}>
              <span className={styles.barName}>{c.name}</span>
              <span className={styles.barTrack} aria-hidden="true">
                <span
                  data-bar
                  className={styles.barFill}
                  data-tone={describeCode(STATUSES, c.statuses[0]).tone}
                  data-nonzero={c.count > 0 || undefined}
                  style={{ width: `${(c.count / max) * 100}%` }}
                />
              </span>
              <span className={`${styles.barValue} tabular`}>{formatCount(c.count)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
