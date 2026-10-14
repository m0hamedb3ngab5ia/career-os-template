import { useState } from "react";
import { STATUSES, describeCode } from "../../kit/labels";
import styles from "./JobsCards.module.css";
import { CardBody, needsYou } from "./JobsCards";
import type { JobListItem } from "./types";

// Stage columns of the Applied tab (REQ-129). Anything else past applied (rejected, withdrawn, ghosted…) sits in
// Closed, which is not a drop target: closing a job needs its own status, picked on the job.
const STAGES = ["applied", "screening", "interview", "offer"];
const label = (s: string) => describeCode(STATUSES, s).label;

interface Props {
  rows: JobListItem[];
  /** Resolves when the move was saved; rejects with the reason, and the card stays where it was. */
  onMove: (job: JobListItem, status: string) => Promise<unknown>;
}

export function JobsBoard({ rows, onMove }: Props) {
  const [over, setOver] = useState<string | null>(null);
  const columns = [
    ...STAGES.map((s) => ({ key: s, name: label(s), jobs: rows.filter((j) => j.status === s) })),
    { key: "", name: "Closed", jobs: rows.filter((j) => !STAGES.includes(j.status ?? "")) },
  ];
  const drop = (id: string, status: string) => {
    const job = rows.find((j) => j.job_id === id);
    if (job && job.status !== status) void onMove(job, status).catch(() => undefined);
  };
  return (
    <div className={styles.board}>
      {columns.map((c) => (
        <section
          key={c.name}
          aria-label={c.name}
          className={styles.column}
          data-over={over === c.key && c.key ? true : undefined}
          onDragOver={c.key ? (e) => (e.preventDefault(), setOver(c.key)) : undefined}
          onDragLeave={() => setOver(null)}
          onDrop={
            c.key
              ? (e) => {
                  e.preventDefault();
                  setOver(null);
                  drop(e.dataTransfer.getData("text/plain"), c.key);
                }
              : undefined
          }
        >
          <h3>
            {c.name} ({c.jobs.length})
          </h3>
          {c.jobs.map((j) => (
            <div
              key={j.job_id}
              className={styles.boardCard}
              draggable
              data-needs-you={needsYou(j) || undefined}
              onDragStart={(e) => {
                e.dataTransfer.setData("text/plain", j.job_id);
                e.dataTransfer.effectAllowed = "move";
              }}
            >
              <CardBody job={j} tab="applied" />
              <select
                aria-label={`Move ${j.company || j.job_id} to`}
                value={j.status ?? ""}
                onChange={(e) => drop(j.job_id, e.target.value)}
              >
                {!STAGES.includes(j.status ?? "") ? <option value={j.status ?? ""}>{label(j.status ?? "")}</option> : null}
                {STAGES.map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
