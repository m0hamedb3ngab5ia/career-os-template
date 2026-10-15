import { Link, useLocation } from "react-router";
import { Button } from "../../kit/Button";
import { StatusChip } from "../../kit/chips";
import { formatCount, formatDate } from "../../lib/format";
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

// REQ-136 reasons. Defaults of scoring.min_prescore / scoring.stale_days (TASK-039); the UI does not read that config yet.
export const MIN_PRESCORE = 30;
export const STALE_DAYS = 21;

/** Why an unscored job is still unscored: below the quick-match cutoff, an older posting (scored after newer ones), else queued. */
export function notScoredReason(j: JobListItem, now = Date.now()): string {
  if (j.prescore != null && j.prescore < MIN_PRESCORE) return `Below cutoff (${MIN_PRESCORE})`;
  const found = j.found_at ? Date.parse(j.found_at) : NaN;
  if (!Number.isNaN(found) && now - found > STALE_DAYS * 86_400_000) return "Older posting, scored after newer ones";
  return "Queued";
}

interface NotScoredProps {
  rows: JobListItem[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  /** Jobs a score run was started for; they leave the tab once scored. */
  scoring: Set<string>;
  onScore: (ids: string[]) => void;
}

/** REQ-136 card: Quick match (labelled, never styled like the fit score) + title · company · place + reason + Score now. */
export function NotScoredList({ rows, selected, onToggle, scoring, onScore }: NotScoredProps) {
  const { search } = useLocation();
  return (
    <ul className={styles.list} aria-label="Jobs">
      {rows.map((j) => {
        const busy = scoring.has(j.job_id);
        return (
          <li key={j.job_id} className={styles.card}>
            <input type="checkbox" checked={selected.has(j.job_id)} onChange={() => onToggle(j.job_id)} aria-label={`Select ${j.company || j.job_id}`} />
            <span className={styles.quick}>
              <span className={styles.quickLabel}>Quick match</span>{" "}
              <span className={styles.quickNum}>{j.prescore == null ? "–" : formatCount(j.prescore)}</span>
            </span>
            <span className={styles.text}>
              <Link to={{ pathname: `/jobs/${encodeURIComponent(j.job_id)}`, search }} className={styles.title} translate="no">
                {j.company || j.job_id} <span className={styles.role}>{j.title}</span>
              </Link>
              <span className={styles.meta}>{[j.location, j.found_at ? formatDate(j.found_at) : ""].filter(Boolean).join(" · ")}</span>
              <span className={styles.reasons}>{notScoredReason(j)}</span>
            </span>
            <Button size="small" disabled={busy} onClick={() => onScore([j.job_id])}>
              {busy ? "Scoring…" : "Score now"}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}
