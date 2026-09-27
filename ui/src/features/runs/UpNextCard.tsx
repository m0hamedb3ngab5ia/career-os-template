import { Link, useSearchParams } from "react-router";
import { EmptyState } from "../../kit/EmptyState";
import { SegmentedControl } from "../../kit/SegmentedControl";
import { formatCount, formatNumber } from "../../lib/format";
import { useQueue } from "./api";
import { ReasonChips } from "./ReasonChips";
import styles from "./Runs.module.css";
import type { BatchKind } from "./types";

/** "Why next": the live ranking for the next score or prepare run, and the jobs left out with their reason. */
export function UpNextCard() {
  const [params, setParams] = useSearchParams();
  const kind: BatchKind = params.get("queue") === "prepare" ? "prepare" : "score";
  const { data, isPending, error } = useQueue(kind);

  function pick(v: string) {
    const next = new URLSearchParams(params);
    next.set("queue", v);
    setParams(next, { replace: true });
  }

  return (
    <section className={`${styles.card} ${styles.grow}`} aria-labelledby="next-h">
      <div className={styles.cardHeadInline}>
        <h2 id="next-h" className={styles.h2Inline}>
          Up next <span className={styles.h2Quiet}>· why each job is here</span>
        </h2>
        <Link to="/settings/runs">Ranking weights</Link>
      </div>
      <div className={styles.toolbarRow}>
        <SegmentedControl label="Queue" value={kind} onValueChange={pick}>
          <SegmentedControl.Option value="score">Score</SegmentedControl.Option>
          <SegmentedControl.Option value="prepare">Prepare</SegmentedControl.Option>
        </SegmentedControl>
        {data ? (
          <span className={styles.caption}>
            {formatCount(data.total)} in the queue · no Claude usage to rank
            {data.excluded_total === 0 ? " · nothing is skipped" : ""}
          </span>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={styles.fix}>
          {error.message}
        </p>
      ) : isPending ? (
        <p className={styles.sub}>Ranking…</p>
      ) : !data.items.length ? (
        <EmptyState title={kind === "score" ? "Nothing to score" : "Nothing to prepare"} headingLevel={3}>
          {kind === "score"
            ? "New jobs from Scout land here once they pass the filters."
            : "Scored jobs whose decision is prepare land here."}
        </EmptyState>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col" className={styles.numCol}>
                  #
                </th>
                <th scope="col">Job</th>
                <th scope="col">Why</th>
                <th scope="col" className={styles.right}>
                  Points
                </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((i) => (
                <tr key={i.job_id}>
                  <td className={styles.numCol}>{i.rank}</td>
                  <td>
                    <Link to={`/jobs/${i.job_id}`} className={styles.jobLink}>
                      <span className={styles.strong}>{i.company}</span> <span className={styles.sec}>{i.title}</span>
                    </Link>
                  </td>
                  <td>
                    <ReasonChips reasons={i.reasons} />
                  </td>
                  <td className={`${styles.right} tabular`}>{formatNumber(i.score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.total > data.items.length ? (
            <p className={styles.caption}>
              Showing the top {formatCount(data.items.length)} of {formatCount(data.total)}.
            </p>
          ) : null}
        </div>
      )}
      {data && data.excluded_total > 0 ? (
        <details className={styles.details}>
          <summary>Not in queue ({formatCount(data.excluded_total)})</summary>
          <ul className={styles.plainList}>
            {data.excluded.map((e) => (
              <li key={e.job_id} className={styles.row}>
                <div className={styles.grow}>
                  <span className={styles.strong}>{e.company ?? e.job_id}</span>{" "}
                  <span className={styles.sec}>{e.title}</span>
                </div>
                <span className={styles.rowMeta}>{e.reason}</span>
              </li>
            ))}
          </ul>
          {data.excluded_total > data.excluded.length ? (
            <p className={styles.caption}>
              {formatCount(data.excluded_total - data.excluded.length)} more not shown.
            </p>
          ) : null}
        </details>
      ) : null}
    </section>
  );
}
