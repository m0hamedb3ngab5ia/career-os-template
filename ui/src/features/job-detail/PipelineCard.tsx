import { useQuery } from "@tanstack/react-query";
import { Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../../api/client";
import { Button } from "../../kit/Button";
import { useToast } from "../../kit/Toast";
import { runKeys, useCancelRun, useRunStream } from "../runs/api";
import { LogPane, type LogLine } from "../runs/LogPane";
import type { RunDetail } from "../runs/types";
import { errorText, usePipeline, useStartPipeline } from "./api";
import { Card, Muted } from "./Card";
import styles from "./JobDetail.module.css";
import type { PipelineState } from "./types";

export const STAGES: { id: PipelineState["stage"]; label: string }[] = [
  { id: "score", label: "Score" },
  { id: "prepare", label: "Prepare" },
  { id: "qa", label: "QA" },
  { id: "review", label: "Review" },
  { id: "apply", label: "Apply" },
];

const KIND_HELP: Record<string, string> = {
  score: "Runs score-job headless: score.json, tier and the prepare/skip decision.",
  prepare: "Runs prepare-job headless: score, tailored resume, cover letter and QA.",
  apply: "Runs apply-job headless in Chrome: fills the form, then submits or stages it for you per auto_submit.",
};

/** True when a state just reached after a score run started here should roll straight into prepare: the server
 * offers a plain (non-forced) continue into prepare and nothing blocks the job. Apply is never chained. */
function chainsToPrepare(s: PipelineState): boolean {
  return s.next_action === "continue" && s.next_kind === "prepare" && !s.force && !s.blocked_reason &&
    s.active_run_id == null;
}

// Polls of GET /runs/{id} (1s apart) that may 404 before a run the card started is given up on: `careeros run`
// writes run.json within a second or two of spawning; ~15s without one means it never started.
const MAX_MISSING_POLLS = 15;

/** Stage stepper, the one next action (Start / Continue / Approve & continue), the review reasons and, while a
 * run works on this job, its live output with Cancel. The server decides what can run (job_pipeline.py).
 * A score run started here chains into prepare (score → prepare → QA in one click) and stops at the review gate
 * or a blocked state; "Stop after this stage" turns that off. */
export function PipelineCard({ jobId }: { jobId: string }) {
  const toast = useToast();
  // The run id a start returned, kept until the run record shows up as active_run_id (polled), then until it ends.
  const [started, setStarted] = useState<string | null>(null);
  const [stopAfter, setStopAfter] = useState(false);
  // "Scored — continuing to prepare…": from the moment a chained prepare run is requested until it ends.
  const [chaining, setChaining] = useState(false);
  // The kind of the run this card started, so only our own score run chains (never a run from elsewhere).
  const startedKind = useRef<string | null>(null);
  // How the last run this card started ended ("Run <id> ended: <stop reason>"), until the next start.
  const [lastEnd, setLastEnd] = useState<string | null>(null);
  const pipeline = usePipeline(jobId, started !== null);
  const state = pipeline.data;
  // Stream the run we started even before the pipeline reports it (it may end before the first 1s poll).
  const runId = state?.active_run_id ?? started;
  const start = useStartPipeline(jobId);
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
  const startedMissing = started !== null && startedRun.data == null && startedRun.errorUpdateCount >= MAX_MISSING_POLLS;

  useEffect(() => {
    if (state?.active_run_id && started && state.active_run_id !== started) setStarted(null); // another run took the job
  }, [state?.active_run_id, started]);
  useEffect(() => {
    if (!stream.ended && !startedEnded && !startedMissing) return;
    if (started && !stream.ended) {
      const d = startedRun.data;
      setLastEnd(d ? `Run ${d.id} ended: ${d.stop_reason ?? d.status}${d.detail ? ` — ${d.detail}` : ""}`
                   : `Run ${started} did not start (no run record after ${MAX_MISSING_POLLS}s)`);
    }
    setStarted(null);
    setChaining(false);
    const wasScore = startedKind.current === "score";
    startedKind.current = null;
    void pipeline.refetch().then((r) => {
      if (!wasScore || stopAfter || !r.data || !chainsToPrepare(r.data)) return;
      setChaining(true);
      startedKind.current = "prepare";
      start.mutate(
        { action: "continue" },
        {
          onSuccess: (res) => setStarted(res.run_id),
          onError: (e) => {
            setChaining(false);
            toast.show({ message: errorText(e) });
          },
        },
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetch (and maybe chain) once per run end
  }, [stream.ended, startedEnded, startedMissing]);

  if (pipeline.error) {
    return (
      <Card title="Pipeline" icon={<Workflow size={16} strokeWidth={1.7} aria-hidden="true" />}>
        <p className={styles.alert}>{errorText(pipeline.error)}</p>
      </Card>
    );
  }
  if (!state) {
    return (
      <Card title="Pipeline" icon={<Workflow size={16} strokeWidth={1.7} aria-hidden="true" />}>
        <Muted>Loading…</Muted>
      </Card>
    );
  }

  const current = STAGES.findIndex((s) => s.id === state.stage);
  const busy = start.isPending || started !== null || runId !== null;
  const label = state.next_label ?? "Continue pipeline";
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
    <Card title="Pipeline" icon={<Workflow size={16} strokeWidth={1.7} aria-hidden="true" />}>
      <ol className={styles.stepper} aria-label="Pipeline stages" style={{ marginTop: 0 }}>
        {STAGES.map((s, i) => {
          const st = i < current ? "done" : i === current ? "current" : "upcoming";
          return (
            <li key={s.id} data-state={st} aria-current={st === "current" ? "step" : undefined}>
              <span className={styles.stepBar} />
              <span className={styles.stepLabel}>{s.label}</span>
            </li>
          );
        })}
      </ol>
      {state.review_reasons.length > 0 ? (
        <div className={styles.reviewReasons}>
          <p className={styles.caption}>{state.stage === "review" ? "Waiting on you" : "Notes from the pipeline"}</p>
          <ul className={styles.bullets}>
            {state.review_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {lastEnd && !runId ? <p className={styles.alert}>{lastEnd}</p> : null}
      {runId ? (
        <>
          <div className={styles.buttons}>
            <span className={styles.sec}>
              {chaining ? "Scored — continuing to prepare… " : ""}Running {state.next_kind ?? ""} · {runId}
            </span>
            <Button
              variant="destructive"
              disabled={cancel.isPending}
              onClick={() =>
                cancel.mutate(runId, { onError: (e) => toast.show({ message: errorText(e) }) })
              }
            >
              Cancel
            </Button>
          </div>
          <LogPane label="Live run output" lines={lines} empty="Waiting for output…" live />
        </>
      ) : state.next_action ? (
        <div className={styles.buttons}>
          <Button variant="primary" title={label} disabled={busy} onClick={run}>
            {started ? "Starting…" : label}
          </Button>
          <span className={styles.sec}>
            {chaining ? "Scored — continuing to prepare…" : KIND_HELP[state.next_kind ?? ""] ?? ""}
          </span>
        </div>
      ) : (
        <div className={styles.buttons}>
          <Button variant="primary" title={state.blocked_reason ?? label} disabled>
            {label}
          </Button>
          <span className={styles.sec}>{state.blocked_reason ?? "Nothing left to run for this job."}</span>
        </div>
      )}
      {state.next_kind === "score" || chaining || startedKind.current === "score" ? (
        <label className={styles.caption} style={{ display: "flex", alignItems: "center", gap: "var(--space-1)" }}>
          <input type="checkbox" checked={stopAfter} onChange={(e) => setStopAfter(e.target.checked)} />
          Stop after this stage
        </label>
      ) : null}
    </Card>
  );
}
