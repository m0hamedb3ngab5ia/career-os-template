import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { ActionItem, CatchUpResult, RunStarted, TodayData, TodayStatus } from "./types";

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

/** The viewer's time zone, so date-only deadlines end at local midnight (as on /api/actions). */
function todayUrl(): string {
  let tz: string | undefined;
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    tz = undefined;
  }
  return tz ? `/api/today?tz=${encodeURIComponent(tz)}` : "/api/today";
}

export function useToday() {
  return useQuery({
    queryKey: ["today"],
    queryFn: () => apiFetch<TodayData>(todayUrl()),
    staleTime: 30_000,
  });
}

export { useMeta } from "../../api/meta";

function useRefreshToday() {
  const qc = useQueryClient();
  return () => Promise.all([qc.invalidateQueries({ queryKey: ["today"] }), qc.invalidateQueries({ queryKey: ["status"] })]);
}

/** POST /api/actions/{id}/done|reopen (the Action Items API): ids written, queued (Excel open) and missing. */
interface DoneResult {
  ok: string[];
  queued: string[];
  missing: string[];
}

const actionPath = (item: ActionItem, verb: "done" | "reopen") =>
  `/api/actions/${encodeURIComponent(String(item.id))}/${verb}`;

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
      apiSend<RunStarted>("POST", "/api/runs", preset ? { kind: "prepare", preset } : { kind: "prepare" }),
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
