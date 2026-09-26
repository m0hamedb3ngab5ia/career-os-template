import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { ActionItem, CatchUpResult, Meta, RunStarted, TodayData, TodayStatus } from "./types";

/** The server's `detail` (ApiError carries it as the message) or the error's own message. */
export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

// Query keys match ui/src/api/events.ts, so SSE `changed` frames refresh this screen with no polling.

export function useTodayStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: () => apiFetch<TodayStatus>("/api/status"),
    staleTime: 30_000,
  });
}

export function useToday() {
  return useQuery({
    queryKey: ["today"],
    queryFn: () => apiFetch<TodayData>("/api/today"),
    staleTime: 30_000,
  });
}

export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: () => apiFetch<Meta>("/api/meta"),
    staleTime: 5 * 60_000,
  });
}

function useRefreshToday() {
  const qc = useQueryClient();
  return () => Promise.all([qc.invalidateQueries({ queryKey: ["today"] }), qc.invalidateQueries({ queryKey: ["status"] })]);
}

interface DoneResult {
  ok: boolean;
  queued?: boolean;
}

const actionPath = (item: ActionItem, verb: "done" | "reopen") =>
  `/api/today/actions/${encodeURIComponent(String(item.id))}/${verb}`;

/** Mark done: the row leaves the list at once; on failure it comes back. */
export function useMarkDone() {
  const qc = useQueryClient();
  const refresh = useRefreshToday();
  return useMutation({
    mutationFn: (item: ActionItem) => apiSend<DoneResult>("POST", actionPath(item, "done")),
    onMutate: async (item) => {
      await qc.cancelQueries({ queryKey: ["today"] });
      const before = qc.getQueryData<TodayData>(["today"]);
      qc.setQueryData<TodayData>(["today"], (d) =>
        d ? { ...d, actions: (d.actions ?? []).filter((a) => a.id !== item.id) } : d,
      );
      return { before };
    },
    onError: (_e, _item, ctx) => {
      if (ctx?.before) qc.setQueryData(["today"], ctx.before);
    },
    onSettled: refresh,
  });
}

/** Undo of Mark done: the row comes back at once; on failure it leaves again. */
export function useReopen() {
  const qc = useQueryClient();
  const refresh = useRefreshToday();
  return useMutation({
    mutationFn: (item: ActionItem) => apiSend<DoneResult>("POST", actionPath(item, "reopen")),
    onMutate: async (item) => {
      await qc.cancelQueries({ queryKey: ["today"] });
      const before = qc.getQueryData<TodayData>(["today"]);
      qc.setQueryData<TodayData>(["today"], (d) =>
        d && !(d.actions ?? []).some((a) => a.id === item.id) ? { ...d, actions: [...(d.actions ?? []), item] } : d,
      );
      return { before };
    },
    onError: (_e, _item, ctx) => {
      if (ctx?.before) qc.setQueryData(["today"], ctx.before);
    },
    onSettled: refresh,
  });
}

export function useRunScout() {
  const refresh = useRefreshToday();
  return useMutation({
    mutationFn: () => apiSend<RunStarted>("POST", "/api/runs/steps/scout"),
    onSettled: refresh,
  });
}

export function usePrepareQueued() {
  const refresh = useRefreshToday();
  return useMutation({
    mutationFn: (preset: string | undefined) =>
      apiSend<RunStarted>("POST", "/api/runs/batches/prepare", preset ? { preset } : {}),
    onSettled: refresh,
  });
}

export function useCatchUp() {
  const refresh = useRefreshToday();
  return useMutation({
    mutationFn: (dismiss: boolean) => apiSend<CatchUpResult>("POST", "/api/runs/catch-up", { dismiss }),
    onSettled: refresh,
  });
}

export function useResume() {
  const refresh = useRefreshToday();
  return useMutation({
    mutationFn: () => apiSend<{ resumed: boolean }>("POST", "/api/runs/resume"),
    onSettled: refresh,
  });
}
