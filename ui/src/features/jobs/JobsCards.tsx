import { StatusChip } from "../../kit/chips";
import { formatCount, formatDate } from "../../lib/format";
import styles from "./JobsCards.module.css";
import { useRowOpen } from "../inspector/JobInspector";
import { OpenJob, PostingLink } from "./cells";
import { datesLine } from "./dates";
import { reasonsLine } from "./reasons";
import type { JobListItem, TabKey } from "./types";

/** "Needs you" (REQ-132, Q-030) = waiting for the user's review (prepared / filled, not submitted) or has an open
 *  Action Item: the only amber on a card. */
export const needsYou = (j: JobListItem) => j.status === "needs_review" || j.status === "prepared" || !!j.next_action;

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
        <PostingLink job={job} className={styles.title}>
          {job.company || job.job_id} <span className={styles.role}>{job.title}</span>
        </PostingLink>
        <span className={styles.meta}><OpenJob id={job.job_id}>{place}</OpenJob></span>
        {datesLine(job) ? <span className={styles.meta}>{datesLine(job)}</span> : null}
        <span className={pending ? styles.pending : styles.reasons}>{reasonsLine(job.reasons)}</span>
      </span>
      <span className={styles.badge}>
        {needsYou(job) ? (
          <span className={styles.needs}>
            <span className={styles.dot} aria-hidden="true" /> Needs you
          </span>
        ) : tab === "inprogress" && job.progress ? (
          <span className={styles.saved}>{job.progress}</span>
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
  const rowOpen = useRowOpen();
  return (
    <ul className={styles.list} aria-label="Jobs">
      {rows.map((j) => (
        <li key={j.job_id} className={styles.card} onClick={rowOpen(j.job_id)} data-needs-you={needsYou(j) || undefined} aria-current={j.job_id === current ? "true" : undefined}>
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

// REQ-136 reasons follow pipeline.yaml `scoring` (TASK-039), read from pipeline.yaml; these are its defaults until it loads.
const SCORING_DEFAULTS = { minPrescore: 20, staleDays: 21 };
type ScoringCfg = typeof SCORING_DEFAULTS;

function useScoringCfg(): ScoringCfg {
  return SCORING_DEFAULTS;
}

/** Why an unscored job is still unscored: below the quick-match cutoff, an older posting (scored after newer ones), else queued. */
export function notScoredReason(j: JobListItem, cfg: ScoringCfg = SCORING_DEFAULTS, now = Date.now()): string {
  if (j.prescore != null && j.prescore < cfg.minPrescore) return `Below cutoff (${cfg.minPrescore})`;
  const found = j.found_at ? Date.parse(j.found_at) : NaN;
  if (!Number.isNaN(found) && now - found > cfg.staleDays * 86_400_000) return "Older posting, scored after newer ones";
  return "Queued";
}

interface NotScoredProps {
  rows: JobListItem[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  /** Jobs a score run was started for; they leave the tab once scored. */
}

/** REQ-136 card: Quick match (labelled, never styled like the fit score) + title · company · place + reason. */
export function NotScoredList({ rows, selected, onToggle }: NotScoredProps) {
  const cfg = useScoringCfg();
  return (
    <ul className={styles.list} aria-label="Jobs">
      {rows.map((j) => {
        return (
          <li key={j.job_id} className={styles.card}>
            <input type="checkbox" checked={selected.has(j.job_id)} onChange={() => onToggle(j.job_id)} aria-label={`Select ${j.company || j.job_id}`} />
            <span className={styles.quick}>
              <span className={styles.quickLabel}>Quick match</span>{" "}
              <span className={styles.quickNum}>{j.prescore == null ? "–" : formatCount(j.prescore)}</span>
            </span>
            <span className={styles.text}>
              <PostingLink job={j} className={styles.title}>
                {j.company || j.job_id} <span className={styles.role}>{j.title}</span>
              </PostingLink>
              <span className={styles.meta}>{[j.location, j.found_at ? formatDate(j.found_at) : ""].filter(Boolean).join(" · ")}</span>
              <span className={styles.reasons}>{notScoredReason(j, cfg)}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
