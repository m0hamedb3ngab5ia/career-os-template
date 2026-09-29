import { useQuery } from "@tanstack/react-query";
import { Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../../api/client";
import { Button } from "../../kit/Button";
import { Details } from "../../kit/Details";
import { useToast } from "../../kit/Toast";
import { runKeys, useCancelRun, useRunStream } from "../runs/api";
import { LogPane, type LogLine } from "../runs/LogPane";
import type { RunDetail } from "../runs/types";
import { type ActionKey, help } from "./actionHelp";
import { errorText, usePipeline, useResetFailures, useStartPipeline } from "./api";
import { Card, Muted } from "./Card";
import styles from "./JobDetail.module.css";
import { NextStepSummary, ReasonDetails, useJobTasks } from "./NextStep";
import type { PipelineState } from "./types";

const NEXT_ACTION_HELP_KEY: Record<string, ActionKey> = {
  start: "startPipeline",
  continue: "continuePipeline",
  approve_continue: "approveContinue",
};

export const STAGES: { id: PipelineState["stage"]; label: string }[] = [
  { id: "score", label: "Score" },
  { id: "prepare", label: "Prepare" },
  { id: "qa", label: "QA" },
  { id: "review", label: "Review" },
  { id: "apply", label: "Apply" },
];

const KIND_HELP: Record<string, string> = {
  score: "Scores the job against your targets and decides whether to prepare it.",
  prepare: "Scores the job, tailors your resume and cover letter, and checks them.",
  apply: "Fills the application in Chrome, then submits it or stops for your review, per your Automation settings.",
};
/** apply help by the server's auto_submit switch (job_pipeline.auto_submit): off = every run stages for review. */
function kindHelp(s: PipelineState): string {
  if (s.next_kind === "apply") {
    return s.note != null || !s.auto_submit
      ? "Fills the application in Chrome and stops before Submit; you review and send it."
      : "Fills the application in Chrome and submits it (auto-submit is on).";
  }
  return KIND_HELP[s.next_kind ?? ""] ?? "";
}
const CHAIN_MSG: Record<string, string> = {
  prepare: "Scored — continuing to prepare…",
  apply: "Prepared — filling & staging for review…",
};

/** True when a state just reached after a score run started here should roll straight into prepare: the server
 * offers a plain (non-forced) continue into prepare and nothing blocks the job. */
function chainsToPrepare(s: PipelineState): boolean {
  return s.next_action === "continue" && s.next_kind === "prepare" && !s.force && !s.blocked_reason &&
    s.active_run_id == null;
}

/** True when a state just reached after a prepare run started here should roll on into apply: only while
 * auto_submit is off (the run fills and stages the form, never submits: the human reviews it in the browser),
 * the server offers a plain continue into apply and nothing blocks the job. Never `approve_continue`: that is
 * the review gate (Tier A doc review, review_required categories) and only a human click approves it. */
function chainsToApply(s: PipelineState): boolean {
  return !s.auto_submit && s.next_kind === "apply" && s.next_action === "continue" && !s.force &&
    !s.blocked_reason && s.active_run_id == null;
}

// Polls of GET /runs/{id} (1s apart) that may 404 before a run the card started is given up on: `careeros run`
// writes run.json within a second or two of spawning; ~15s without one means it never started.
const MAX_MISSING_POLLS = 15;

/** Stage stepper, the one next action (Start / Continue / Approve & continue), the review reasons and, while a
 * run works on this job, its live output with Cancel. The server decides what can run (job_pipeline.py).
 * A score run started here chains into prepare (score → prepare → QA in one click); while auto_submit is off the
 * prepare run chains on into apply (fill & stage the form for review, never submit), so one click takes a job to
 * a staged form. Chaining stops at a blocked state or at the review gate (Approve & continue is always a human
 * click); "Stop after this stage" turns it off. */
export function PipelineCard({ jobId }: { jobId: string }) {
  const toast = useToast();
  // The run id a start returned, kept until the run record shows up as active_run_id (polled), then until it ends.
  const [started, setStarted] = useState<string | null>(null);
  const [stopAfter, setStopAfter] = useState(false);
  // The chained run's message (CHAIN_MSG): from the moment it is requested until it ends.
  const [chaining, setChaining] = useState<string | null>(null);
  // The kind of the run this card started, so only our own score run chains (never a run from elsewhere).
  const startedKind = useRef<string | null>(null);
  // How the last run this card started ended ("Run <id> ended: <stop reason>"), until the next start.
  const [lastEnd, setLastEnd] = useState<string | null>(null);
  const pipeline = usePipeline(jobId, started !== null);
  const tasks = useJobTasks(jobId);
  const state = pipeline.data;
  // Stream the run we started even before the pipeline reports it (it may end before the first 1s poll).
  const runId = state?.active_run_id ?? started;
  const start = useStartPipeline(jobId);
  const reset = useResetFailures(jobId);
  const cancel = useCancelRun();
  const stream = useRunStream(runId, runId !== null);
  // The started run's record: 404 until run.json exists, then its status. A finished record means the run ended
  // (maybe before we ever saw it active); MAX_MISSING_POLLS 404s in a row mean it never started.
  const startedRun = useQuery({
    queryKey: runKeys.detail(started ?? ""),
    queryFn: () => apiFetch<RunDetail>(`/api/runs/${encodeURIComponent(started ?? "")}`),
    enabled: started !== null,
    retry: false,
    refetchInterval: 1000,
  });
  const startedEnded = started !== null && startedRun.data != null && startedRun.data.state !== "running";
  // The server reads the refusal the spawned run printed ("Run <id> did not start: <reason>"): no need to wait.
  const startRefusal = started !== null && startedRun.error ? errorText(startedRun.error) : "";
  const refused = startRefusal.includes("did not start");
  const startedMissing = started !== null && startedRun.data == null &&
    (refused || startedRun.errorUpdateCount >= MAX_MISSING_POLLS);

  useEffect(() => {
    if (state?.active_run_id && started && state.active_run_id !== started) setStarted(null); // another run took the job
  }, [state?.active_run_id, started]);
  useEffect(() => {
    if (!stream.ended && !startedEnded && !startedMissing) return;
    if (started && !stream.ended) {
      const d = startedRun.data;
      setLastEnd(d ? `Run ${d.id} ended: ${d.stop_reason ?? d.status}${d.detail ? ` — ${d.detail}` : ""}`
                   : refused ? startRefusal
                   : `Run ${started} did not start (no run record after ${MAX_MISSING_POLLS}s)`);
    }
    setStarted(null);
    setChaining(null);
    const was = startedKind.current;
    startedKind.current = null;
    // Chain only after a clean finish: a failed or stopped run (usage_limit, error, ...) may still have left
    // runnable files behind, and those stops need the user's attention, not the next stage. A run whose job
    // failed still ends "completed" (the runner only counts it), so the counters must show a clean success too.
    const endReason = stream.ended ? stream.stopReason : startedRun.data?.stop_reason ?? null;
    const counts = (stream.ended ? stream.counters : startedRun.data?.counters) ?? {};
    const completed = endReason === "completed" && (counts.ok ?? 0) >= 1 && (counts.failed ?? 0) === 0;
    void pipeline.refetch().then((r) => {
      if (stopAfter || !completed || !r.data || !r.data.next_action) return;
      const next = was === "score" && chainsToPrepare(r.data) ? "prepare"
        : was === "prepare" && chainsToApply(r.data) ? "apply" : null;
      if (!next) return;
      setChaining(CHAIN_MSG[next] ?? null);
      startedKind.current = next;
      start.mutate(
        { action: r.data.next_action },
        {
          onSuccess: (res) => setStarted(res.run_id),
          onError: (e) => {
            setChaining(null);
            toast.show({ message: errorText(e) });
          },
        },
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetch (and maybe chain) once per run end
  }, [stream.ended, startedEnded, startedMissing]);

  if (pipeline.error) {
    return (
      <Card title="Next step" icon={<Workflow size={16} strokeWidth={1.7} aria-hidden="true" />}>
        <p className={styles.alert}>{errorText(pipeline.error)}</p>
      </Card>
    );
  }
  if (!state) {
    return (
      <Card title="Next step" icon={<Workflow size={16} strokeWidth={1.7} aria-hidden="true" />}>
        <Muted>Loading…</Muted>
      </Card>
    );
  }

  const current = STAGES.findIndex((s) => s.id === state.stage);
  const busy = start.isPending || started !== null || runId !== null;
  const label = state.next_label ?? "Continue pipeline";
  const stageHelp = kindHelp(state);
  const lines: LogLine[] = stream.lines.map((l) => ({
    key: l.key,
    text: l.text,
    prefix: l.attempt != null ? `job ${l.attempt}` : undefined,
    error: l.error,
  }));

  function run() {
    if (!state?.next_action) return;
    const kind = state.next_kind;
    setLastEnd(null);
    start.mutate(
      { action: state.next_action },
      {
        onSuccess: (r) => {
          startedKind.current = kind ?? null;
          setStarted(r.run_id);
        },
        onError: (e) => toast.show({ message: errorText(e) }),
      },
    );
  }

  return (
    <Card title="Next step" icon={<Workflow size={16} strokeWidth={1.7} aria-hidden="true" />}>
      <NextStepSummary state={state} tasks={tasks} />
      <ol className={`${styles.stepper} ${styles.progressLine}`} aria-label="Pipeline stages">
        {STAGES.map((s, i) => {
          const st = i < current ? "done" : i === current ? "current" : "upcoming";
          return (
            <li key={s.id} data-state={st} aria-current={st === "current" ? "step" : undefined}>
              <span className={styles.stepBar} />
              <span className={st === "current" ? styles.stepLabel : "sr-only"}>{s.label}</span>
            </li>
          );
        })}
      </ol>
      {lastEnd && !runId ? <p className={styles.alert}>{lastEnd}</p> : null}
      {runId ? (
        <>
          <div className={styles.buttons}>
            <span className={styles.sec}>
              {chaining ? `${chaining} ` : ""}Running {state.next_kind ?? ""}…
            </span>
            <Button
              variant="destructive"
              disabled={cancel.isPending}
              {...help("cancelRun")}
              onClick={() =>
                cancel.mutate(runId, { onError: (e) => toast.show({ message: errorText(e) }) })
              }
            >
              Cancel
            </Button>
          </div>
          <LogPane label="Live run output" lines={lines} empty="Waiting for output…" live />
        </>
      ) : state.next_action && !state.failures?.excluded ? (
        <div className={styles.buttons}>
          <Button
            variant="primary"
            title={(() => {
              // Tier A/B "stage the form" offers keep the stageReview tooltip even though next_action is
              // approve_continue (label overridden to "Prepare & stage for review"); a plain Tier B/C
              // "Approve & continue" must keep its own tooltip: it approves the docs, it does not stage/submit.
              const key = state.next_action === "approve_continue" && state.next_label === "Approve & continue"
                ? NEXT_ACTION_HELP_KEY.approve_continue
                : state.note != null ? "stageReview"
                : state.next_action ? NEXT_ACTION_HELP_KEY[state.next_action] : undefined;
              return key ? help(key).title : label;
            })()}
            disabled={busy}
            onClick={run}
          >
            {started ? "Starting…" : label}
          </Button>
          <span className={styles.sec}>
            {chaining}
          </span>
        </div>
      ) : (
        <div className={styles.buttons}>
          <Button variant="primary" title={state.blocked_reason ?? label} disabled>
            {label}
          </Button>
          {state.blocked_reason ? <span className={styles.sec}>{state.blocked_reason}</span> : null}
          {state.failures?.excluded ? (
            <Button
              title="Clear this job's failure count so runs pick it up again"
              disabled={reset.isPending}
              onClick={() =>
                reset.mutate(state.failures?.kind, {
                  onSuccess: () => { setLastEnd(null); toast.show({ message: "Failures reset" }); },
                  onError: (e) => toast.show({ message: errorText(e) }),
                })
              }
            >
              Reset failures
            </Button>
          ) : null}
        </div>
      )}
      {state.note ? <Muted>{state.note}</Muted> : null}
      {state.next_kind === "score" || (state.next_kind === "prepare" && !state.auto_submit) || chaining !== null ||
       startedKind.current === "score" || startedKind.current === "prepare" ? (
        <label
          className={styles.caption}
          style={{ display: "flex", alignItems: "center", gap: "var(--space-1)" }}
          {...help("stopAfterStage")}
        >
          <input type="checkbox" checked={stopAfter} onChange={(e) => setStopAfter(e.target.checked)} />
          Stop after this stage
        </label>
      ) : null}
      <Details summary="Details">
        {stageHelp ? <p className={styles.caption}>{stageHelp}</p> : null}
        {runId ? <p className={styles.caption}>Run {runId}</p> : null}
        <ReasonDetails reasons={state.review_reasons} />
      </Details>
    </Card>
  );
}
