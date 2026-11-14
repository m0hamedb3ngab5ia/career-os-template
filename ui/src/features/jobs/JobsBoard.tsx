import { STATUSES, describeCode } from "../../kit/labels";
import styles from "./JobsCards.module.css";
import { CardBody, needsYou } from "./JobsCards";
import type { JobListItem } from "./types";

// Stage columns of the Applied tab (REQ-129). Anything else past applied (rejected, withdrawn, ghosted…) sits in
// Closed.
const STAGES = ["applied", "screening", "interview", "offer"];
const label = (s: string) => describeCode(STATUSES, s).label;

interface Props {
  rows: JobListItem[];
}

/** Read-only board: status changes happen in Claude chat or the CLI. */
export function JobsBoard({ rows }: Props) {
  const columns = [
    ...STAGES.map((s) => ({ key: s, name: label(s), jobs: rows.filter((j) => j.status === s) })),
    { key: "", name: "Closed", jobs: rows.filter((j) => !STAGES.includes(j.status ?? "")) },
  ];
  return (
    <div className={styles.board}>
      {columns.map((c) => (
        <section key={c.name} aria-label={c.name} className={styles.column}>
          <h3>
            {c.name} ({c.jobs.length})
          </h3>
          {c.jobs.map((j) => (
            <div key={j.job_id} className={styles.boardCard} data-needs-you={needsYou(j) || undefined}>
              <CardBody job={j} tab="applied" />
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
