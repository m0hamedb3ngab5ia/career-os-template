import { Link } from "react-router";
import { ButtonLink } from "../../kit/Button";
import { formatRelative } from "../../lib/format";
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

/** REQ-127: best-fit new jobs from GET /api/today `top_picks`; a card opens the posting. */
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
            <PickCard key={p.job_id} pick={p} />
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

/** One pick: read-only. Title links to the posting when it has a URL (external), else plain text. */
function PickCard({ pick: p }: { pick: Pick }) {
  const body = (
    <>
      <span className={styles.fit} aria-label={`Fit ${p.fit ?? "unknown"}`}>{p.fit ?? "–"}</span>
      <span className={styles.grow}>
        <span className={styles.strong}>{p.title}</span>
        <span className={styles.caption}>{[p.company, p.location, formatRelative(p.found_at)].filter(Boolean).join(" · ")}</span>
        <span className={styles.caption}>{reasonsLine(p.reasons)}</span>
      </span>
    </>
  );
  return (
    <li>
      {p.url ? (
        <a href={p.url} target="_blank" rel="noopener noreferrer" className={styles.pick}>{body}</a>
      ) : (
        <div className={styles.pick}>{body}</div>
      )}
    </li>
  );
}
