import { STATUSES, describeCode } from "../../kit/labels";
import type { Meta } from "../../api/meta";
import styles from "./JobDetail.module.css";
import type { HistoryEntry } from "./types";

export type StepState = "done" | "current" | "upcoming";
export interface Step {
  status: string;
  state: StepState;
  terminal?: boolean;
}

/**
 * The lifecycle path is the Pipeline board's column statuses in order (meta.pipeline.columns). A closed status
 * (rejected, withdrawn, …) is not on the path: it shows as a terminal step after the last path status the job
 * reached, from its history.
 */
export function buildSteps(status: string | null, history: HistoryEntry[], pipeline: Meta["pipeline"]): Step[] {
  const path = [...new Set(pipeline.columns.flatMap((c) => c.statuses))];
  const at = status ? path.indexOf(status) : -1;
  if (at >= 0 || !status) {
    return path.map((s, i) => ({ status: s, state: i < at ? "done" : i === at ? "current" : "upcoming" }));
  }
  let reached = -1;
  for (const h of history) {
    const i = path.indexOf(h.status);
    if (i > reached) reached = i;
  }
  return [
    ...path.slice(0, reached + 1).map((s) => ({ status: s, state: "done" as const })),
    { status, state: "current", terminal: true },
  ];
}

const SR: Record<StepState, string> = { done: "Done: ", current: "Current step: ", upcoming: "Upcoming: " };

export function StatusStepper({ steps }: { steps: Step[] }) {
  return (
    <ol aria-label="Application progress" className={styles.stepper}>
      {steps.map((s) => (
        <li key={s.status} aria-current={s.state === "current" ? "step" : undefined} data-state={s.state}>
          <span
            aria-hidden="true"
            className={styles.stepBar}
            data-tone={s.state === "current" ? describeCode(STATUSES, s.status).tone : undefined}
          />
          <span className={styles.stepLabel}>
            <span className="sr-only">{SR[s.state]}</span>
            {describeCode(STATUSES, s.status).label}
          </span>
        </li>
      ))}
    </ol>
  );
}
