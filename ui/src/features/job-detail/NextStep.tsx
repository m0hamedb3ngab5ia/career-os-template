import { taskText } from "../../kit/labels";
import { groupByJob } from "../today/actions";
import { useToday } from "../today/api";
import type { ActionItem } from "../today/types";
import styles from "./JobDetail.module.css";
import type { PipelineState } from "./types";

// The Job detail "Next step" block (design doc 3 "Job detail"): one state sentence, what needs you on this job
// (pipeline review reasons + this job's open tasks), and the raw reasons for Details.

/** One plain sentence for the job's pipeline state; `n` is the deduped count of what needs you (default: review reasons). */
export function stateSentence(s: PipelineState, n = s.review_reasons.length): string {
  if (s.active_run_id) return "Working on it: a run is in progress for this job.";
  if (s.blocked_reason) return s.blocked_reason; // already a sentence from the server
  if (n > 0) return `Needs your review: ${n} ${n === 1 ? "thing needs" : "things need"} attention.`;
  if (!s.next_action) return "Nothing left to run for this job.";
  return `Ready for the next step: ${s.next_label ?? "Continue pipeline"}.`;
}

/** This job's open tasks from /api/today, ordered like Today's Needs you (blocked → priority → due). */
export function useJobTasks(jobId: string): ActionItem[] {
  const today = useToday();
  return groupByJob(today.data?.actions ?? []).find((g) => g.jobId === jobId)?.items ?? [];
}

/** The state sentence and the human list of what needs you; no codes (those live in ReasonDetails). */
export function NextStepSummary({ state, tasks }: { state: PipelineState; tasks: readonly ActionItem[] }) {
  const rs = state.review_reasons;
  // A QA warning repeats a failed check's finding: show it only when no check failed.
  const shown = rs.filter((r) => r.code !== "qa_warning" || !rs.some((o) => o.code.startsWith("qa_") && o.code !== "qa_warning"));
  const needs = [...new Set([
    ...shown.map((r) => r.text),
    ...tasks.map((t) => taskText(t.type, t.what)),
  ])];
  return (
    <div className={styles.reviewReasons}>
      <p className={styles.strong}>{stateSentence(state, needs.length)}</p>
      {needs.length ? (
        <ul className={styles.bullets} aria-label="Needs you">
          {needs.map((t, i) => (
            <li key={`${i}:${t}`}>{t}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Raw review reasons (code + detail) for the collapsed Details. */
export function ReasonDetails({ reasons }: { reasons: PipelineState["review_reasons"] }) {
  if (!reasons.length) return null;
  return (
    <ul className={styles.bullets} aria-label="Review reasons">
      {reasons.map((r) => (
        <li key={`${r.code}:${r.detail ?? ""}`}>
          <code>{r.code}</code>: {r.text}
          {r.detail ? ` (${r.detail})` : ""}
        </li>
      ))}
    </ul>
  );
}
