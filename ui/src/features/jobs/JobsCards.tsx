import { Link, useLocation } from "react-router";
import { StatusChip } from "../../kit/chips";
import { formatCount } from "../../lib/format";
import styles from "./JobsCards.module.css";
import { reasonsLine } from "./reasons";
import type { JobListItem, TabKey } from "./types";

/** "Needs you" (REQ-132, Q-030) = waiting for the user's review (prepared / filled, not submitted) or has an open
 *  Action Item: the only amber on a card. */
export const needsYou = (j: JobListItem) => j.status === "needs_review" || j.status === "prepared" || !!j.next_action;

/** REQ-130 card body: fit as the anchor number, title · company · place, one reasons line, one status badge. */
export function CardBody({ job, tab }: { job: JobListItem; tab: TabKey }) {
  const place = [job.title, job.company, job.location].filter(Boolean).join(" · ");
  const pending = !job.reasons;
  const { search } = useLocation();
  return (
    <>
      <span className={styles.fit} aria-label={job.fit == null ? "No fit score" : `Fit ${job.fit}`}>
        {job.fit == null ? "–" : formatCount(Math.round(job.fit))}
      </span>
      <span className={styles.text}>
        <Link to={{ pathname: `/jobs/${encodeURIComponent(job.job_id)}`, search }} className={styles.title} translate="no">
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
  /** The job open in the detail pane (master-detail). */
  current?: string;
}

export function JobsList({ rows, tab, selected, onToggle, current }: ListProps) {
  return (
    <ul className={styles.list} aria-label="Jobs">
      {rows.map((j) => (
        <li key={j.job_id} className={styles.card} data-needs-you={needsYou(j) || undefined} aria-current={j.job_id === current ? "true" : undefined}>
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
