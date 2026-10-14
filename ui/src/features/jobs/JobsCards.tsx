import { Link } from "react-router";
import { StatusChip } from "../../kit/chips";
import { formatCount } from "../../lib/format";
import styles from "./JobsCards.module.css";
import { reasonsLine } from "./reasons";
import type { JobListItem, TabKey } from "./types";

/** "Needs you" = the pipeline stopped for a human (REQ-132): the only amber on a card. */
export const needsYou = (j: JobListItem) => j.status === "needs_review";

/** REQ-130 card body: fit as the anchor number, title · company · place, one reasons line, one status badge. */
export function CardBody({ job, tab }: { job: JobListItem; tab: TabKey }) {
  const place = [job.title, job.company, job.location].filter(Boolean).join(" · ");
  const pending = !job.reasons;
  return (
    <>
      <span className={styles.fit} aria-label={job.fit == null ? "No fit score" : `Fit ${job.fit}`}>
        {job.fit == null ? "–" : formatCount(Math.round(job.fit))}
      </span>
      <span className={styles.text}>
        <Link to={`/jobs/${encodeURIComponent(job.job_id)}`} className={styles.title} translate="no">
          {job.company || job.job_id} <span className={styles.role}>{job.title}</span>
        </Link>
        <span className={styles.meta}>{place}</span>
        <span className={pending ? styles.pending : styles.reasons}>{reasonsLine(job.reasons)}</span>
      </span>
      <span className={styles.badge}>
        {needsYou(job) ? (
          <span className={styles.needs}>
            <span className={styles.dot} aria-hidden="true" /> Needs you
          </span>
        ) : tab === "saved" ? (
          <span className={styles.saved}>
            <span className={styles.dot} aria-hidden="true" /> Saved
          </span>
        ) : tab === "applied" && job.status ? (
          <StatusChip status={job.status} />
        ) : null}
      </span>
    </>
  );
}

interface ListProps {
  rows: JobListItem[];
  tab: TabKey;
  selected: Set<string>;
  onToggle: (id: string) => void;
}

export function JobsList({ rows, tab, selected, onToggle }: ListProps) {
  return (
    <ul className={styles.list} aria-label="Jobs">
      {rows.map((j) => (
        <li key={j.job_id} className={styles.card} data-needs-you={needsYou(j) || undefined}>
          <input
            type="checkbox"
            checked={selected.has(j.job_id)}
            onChange={() => onToggle(j.job_id)}
            aria-label={`Select ${j.company || j.job_id}`}
          />
          <CardBody job={j} tab={tab} />
        </li>
      ))}
    </ul>
  );
}
