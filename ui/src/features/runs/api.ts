import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiFetch, apiSend } from "../../api/client";
import type {
  BatchKind,
  CancelResult,
  CurrentRun,
  HistoryPage,
  Meta,
  Pause,
  Queue,
  RunDetail,
  Schedule,
  Selection,
  Started,
  StepKind,
  StreamLine,
} from "./types";

// Every Runs query key starts with "runs" (or is ["run", id]), so the live events (api/events.ts) refresh them
// when data/runs/ or the config changes. The start/stop mutations also invalidate right away.

export const runKeys = {
  all: ["runs"] as const,
  current: ["runs", "current"] as const,
  history: (kind: string) => ["runs", "history", kind] as const,
  queue: (kind: string) => ["runs", "queue", kind] as const,
  schedule: ["runs", "schedule"] as const,
  detail: (id: string) => ["run", id] as const,
};

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: () => apiFetch<Meta>("/api/meta"), staleTime: 60_000 });
}

export function useCurrentRun() {
  return useQuery({ queryKey: runKeys.current, queryFn: () => apiFetch<CurrentRun | null>("/api/runs/current") });
}

export function useSchedule() {
  return useQuery({ queryKey: runKeys.schedule, queryFn: () => apiFetch<Schedule>("/api/schedule") });
}

export function useQueue(kind: BatchKind) {
  return useQuery({
    queryKey: runKeys.queue(kind),
    queryFn: () => apiFetch<Queue>(`/api/runs/queue/${kind}`),
  });
}

export function useRunHistory(kind: string) {
  return useInfiniteQuery({
    queryKey: runKeys.history(kind),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const q = new URLSearchParams();
      if (kind) q.set("kind", kind);
      if (pageParam) q.set("cursor", pageParam);
      const s = q.toString();
      return apiFetch<HistoryPage>(`/api/runs${s ? `?${s}` : ""}`);
    },
    getNextPageParam: (last) => last.next_cursor,
  });
}

export function useRunDetail(id: string) {
  return useQuery({
    queryKey: runKeys.detail(id),
    queryFn: () => apiFetch<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  });
}

function useRunsMutation<TVars, TOut>(fn: (v: TVars) => Promise<TOut>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: runKeys.all });
      void qc.invalidateQueries({ queryKey: ["status"] });
    },
  });
}

export interface StartVars {
  kind: BatchKind;
  preset?: string;
  max_jobs?: number;
  max_minutes?: number;
  dry_run?: boolean;
}

export function useStartRun() {
  return useRunsMutation((v: StartVars) => apiSend<Started | Selection>("POST", "/api/runs", v));
}

export function useStartStep() {
  return useRunsMutation((kind: StepKind) => apiSend<Started>("POST", `/api/runs/steps/${kind}`));
}

export function useCancelRun() {
  return useRunsMutation((runId: string) => apiSend<CancelResult>("POST", "/api/runs/cancel", { run_id: runId }));
}

export function usePause() {
  return useRunsMutation((until: string | null) => apiSend<Pause>("POST", "/api/runs/pause", { until }));
}

export function useResume() {
  return useRunsMutation(() => apiSend<{ resumed: boolean }>("POST", "/api/runs/resume"));
}

export function useCatchUp() {
  return useRunsMutation((dismiss: boolean) =>
    apiSend<Record<string, unknown>>("POST", "/api/runs/catch-up", { dismiss }),
  );
}

export function useScheduleAction() {
  return useRunsMutation((action: "install" | "uninstall") =>
    apiSend<Record<string, unknown>>("POST", `/api/schedule/${action}`),
  );
}

const MAX_LINES = 20_000;

/**
 * Tail a run's output over SSE (GET /api/runs/{id}/stream): `event` frames append a line, `end` closes the
 * stream. A reconnect replays from the start, so the lines reset on every open after the first.
 */
export function useRunStream(runId: string | null | undefined, enabled = true) {
  const qc = useQueryClient();
  const [lines, setLines] = useState<StreamLine[]>([]);
  const [ended, setEnded] = useState(false);
  // The `end` frame's stop reason (e.g. "completed", "usage_limit"); null until the run ends or if the frame had none.
  const [stopReason, setStopReason] = useState<string | null>(null);
  // The `end` frame's run counters (ok, failed, ...); null until the run ends or if the frame had none.
  const [counters, setCounters] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    setLines([]);
    setEnded(false);
    setStopReason(null);
    setCounters(null);
    if (!runId || !enabled || typeof EventSource === "undefined") return;
    const es = new EventSource(`/api/runs/${encodeURIComponent(runId)}/stream`);
    let key = 0;
    let opens = 0;
    es.onopen = () => {
      opens += 1;
      if (opens > 1) setLines([]);
    };
    es.addEventListener("event", (m) => {
      let ev: Partial<StreamLine> & { text?: string };
      try {
        ev = JSON.parse((m as MessageEvent).data as string) as typeof ev;
      } catch {
        return;
      }
      if (!ev.text) return;
      key += 1;
      const line: StreamLine = { key, type: ev.type ?? "log", text: ev.text, attempt: ev.attempt, error: ev.error };
      setLines((prev) => (prev.length >= MAX_LINES ? [...prev.slice(-MAX_LINES + 1), line] : [...prev, line]));
    });
    es.addEventListener("end", (m) => {
      es.close();
      try {
        const end = JSON.parse((m as MessageEvent).data as string) as {
          stop_reason?: string | null;
          counters?: Record<string, number> | null;
        };
        setStopReason(end.stop_reason ?? null);
        setCounters(end.counters ?? null);
      } catch {
        setStopReason(null);
        setCounters(null);
      }
      setEnded(true);
      void qc.invalidateQueries({ queryKey: runKeys.all });
      void qc.invalidateQueries({ queryKey: runKeys.detail(runId) });
    });
    return () => es.close();
  }, [runId, enabled, qc]);

  return { lines, ended, stopReason, counters };
}
