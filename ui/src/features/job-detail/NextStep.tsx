import { Link } from "react-router";
import { Details } from "../../kit/Details";
import { groupByJob } from "../today/actions";
import { useToday } from "../today/api";
import type { ActionItem } from "../today/types";
import styles from "./JobDetail.module.css";
import type { PipelineState } from "./types";

// The Job detail "Next step" block (design doc 3 "Job detail"): one state sentence, then one line of counts that
// link to the cards owning the detail (QA, Action Items). The detail itself is never repeated here.

/** One plain sentence for the job's pipeline state; `n` is the deduped count of what needs you (default: review reasons). */
export function stateSentence(s: PipelineState, n = s.review_reasons.length, tab?: string): string {
  if (s.active_run_id) return "Working on it: a run is in progress for this job.";
  // The server only knows the form was staged; the live tab check (GET .../application, polled) knows if it's gone.
  if (s.blocked_reason?.startsWith("Application staged") && tab && tab !== "open") {
    return "The browser tab with this application is closed: refill it, then review and submit.";
  }
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

/** The state sentence and one line linking to what needs you: QA checks (#qa), this job's tasks (Action Items),
 * and any other review reason by its text. QA/task/staged reasons are not repeated: their cards own them. */
export function NextStepSummary({ state, tasks, tab }: { state: PipelineState; tasks: readonly ActionItem[]; tab?: string }) {
  const rs = state.review_reasons;
  const failedQa = rs.filter((r) => r.code.startsWith("qa_") && r.code !== "qa_warning");
  const warnedQa = rs.filter((r) => r.code === "qa_warning");
  const failed = failedQa.length;
  const warned = warnedQa.length;
  // Fail reasons carry the sentence in detail; checks carry "check_id: detail", so drop the id.
  const qaLines = (failed ? failedQa : warnedQa).map((r) =>
    r.code === "qa_fail" || r.code === "qa_warning" ? (r.detail ?? r.text) : r.detail ? `${r.text}: ${r.detail.replace(/^[^:]+: /, "")}` : r.text);
  // prepare_action is the task the prepare run left: the task count already covers it.
  const other = [...new Set(rs.filter((r) =>
    !r.code.startsWith("qa_") && !r.code.startsWith("action_") && r.code !== "apply_staged" &&
    !(r.code === "prepare_action" && tasks.length)).map((r) => r.text))];
  const qa = failed ? `${failed} QA check${failed === 1 ? "" : "s"} failed` : warned ? `${warned} QA warning${warned === 1 ? "" : "s"}` : "";
  const n = failed + tasks.length + other.length;
  return (
    <div className={styles.reviewReasons}>
      <p className={styles.strong}>{stateSentence(state, n, tab)}</p>
      {qa ? (
        <Details summary={qa}>
          <ul className={styles.bullets}>
            {[...new Set(qaLines)].map((l) => <li key={l}>{l}</li>)}
          </ul>
        </Details>
      ) : null}
      {tasks.length || other.length ? (
        <p className={styles.caption}>
          {tasks.length ? <Link to="/actions">{tasks.length} task{tasks.length === 1 ? "" : "s"}</Link> : null}
          {other.length ? `${tasks.length ? " · " : ""}${other.join(" · ")}` : null}
        </p>
      ) : null}
    </div>
  );
}

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
