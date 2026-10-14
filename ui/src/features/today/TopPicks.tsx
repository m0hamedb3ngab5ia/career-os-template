import { Link } from "react-router";
import { ButtonLink } from "../../kit/Button";
import type { components } from "../../api/schema.gen";
import styles from "./Today.module.css";

type Pick = components["schemas"]["JobListItem"];

/** REQ-130 reasons line: "<covered>/<total> skills · missing: <top 2>, +n"; null = not computed yet. */
export function reasonsLine(r: Pick["reasons"]): string {
  if (!r) return "Match pending";
  const head = `${r.covered}/${r.total} skills`;
  if (!r.missing.length) return head;
  const more = r.missing.length > 2 ? `, +${r.missing.length - 2}` : "";
  return `${head} · missing: ${r.missing.slice(0, 2).join(", ")}${more}`;
}

/** REQ-127: best-fit new jobs from GET /api/today `top_picks`; a card opens that job. */
export function TopPicks({ picks }: { picks: Pick[] }) {
  return (
    <section className={styles.panel} aria-labelledby="picks-title">
      <div className={styles.panelHead}>
        <h2 id="picks-title" className={styles.h2}>Top picks</h2>
        <Link to="/jobs" className={styles.headLink}>All jobs</Link>
      </div>
      {picks.length ? (
        <ul className={styles.plainList}>
          {picks.map((p) => (
            <li key={p.job_id}>
              <Link to={`/jobs/${encodeURIComponent(p.job_id)}`} className={styles.pick}>
                <span className={styles.fit} aria-label={`Fit ${p.fit ?? "unknown"}`}>{p.fit ?? "–"}</span>
                <span className={styles.grow}>
                  <span className={styles.strong}>{p.title}</span>
                  <span className={styles.caption}>{[p.company, p.location].filter(Boolean).join(" · ")}</span>
                  <span className={styles.caption}>{reasonsLine(p.reasons)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className={styles.oneLine}>
          <span>No new picks right now</span>
          <ButtonLink to="/jobs">Browse all jobs</ButtonLink>
        </div>
      )}
    </section>
  );
}
