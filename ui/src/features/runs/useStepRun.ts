import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { ApiError, apiFetch, apiSend } from "../../api/client";
import { runKeys } from "./api";
import type { RunDetail } from "./types";

type StepRunKind = "scout" | "qa";

/** One step run the UI started and watches (scout, a job's QA; reusable for Prepare/Apply): start, poll, Stop.
 * The run id lives in the query cache, so leaving the page (Back) keeps watching the same run when you return.
 * Stop kills the process and discards its partial output server side; the page drops the run at once. */
export function useStepRun(kind: StepRunKind, jobId?: string, onDone?: (run: RunDetail) => void) {
  const qc = useQueryClient();
  const key = ["stepRun", kind, jobId ?? ""];
  const runId = useQuery({ queryKey: key, queryFn: () => null as string | null, enabled: false, initialData: null,
    staleTime: Infinity, gcTime: Infinity }).data;
  const clear = () => qc.setQueryData(key, null);
  const run = useQuery({
    queryKey: runKeys.detail(runId ?? ""),
    queryFn: () => apiFetch<RunDetail>(`/api/runs/${runId}`),
    enabled: !!runId,
    refetchInterval: 1000,
    retry: (n, e) => !(e instanceof ApiError && /did not start/.test(e.message)) && n < 30,
  });
  const detail = runId ? run.data : undefined;
  const finished = !!detail && detail.state !== "running";
  const startError = runId && run.error instanceof ApiError && /did not start/.test(run.error.message) ? run.error.message : null;
  useEffect(() => {
    if (finished && detail) {
      clear();
      onDone?.(detail);
    } else if (startError) clear();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished, startError]);
  const start = useMutation({
    mutationFn: () =>
      apiSend<{ run_id: string }>("POST", `/api/runs/steps/${kind}${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ""}`),
    onSuccess: (r) => qc.setQueryData(key, r.run_id),
  });
  const stop = useMutation({
    mutationFn: (id: string) => apiSend("POST", "/api/runs/cancel", { run_id: id }),
    onSettled: () => clear(),
  });
  return {
    runId,
    run: detail,
    running: !!runId,
    startError,
    start,
    stop: () => runId && stop.mutate(runId),
  };
}

/** Scout's progress from its run log: the board it last finished, postings stored so far, seconds elapsed. */
export function scoutProgress(run: RunDetail | undefined, now = Date.now()) {
  const lines = (run?.log ?? "").split("\n").filter((l) => l.trim());
  const found = lines.reduce((n, l) => n + Number(/stored=(\d+)/.exec(l)?.[1] ?? 0), 0);
  const last = lines.at(-1)?.replace(/^- \S+ \[run\] /, "").replace(/\s+/g, " ") ?? "Starting…";
  const began = run?.started_at ? Date.parse(run.started_at) : now;
  return { step: last, found, elapsed: Math.max(0, Math.round((now - began) / 1000)) };
}
