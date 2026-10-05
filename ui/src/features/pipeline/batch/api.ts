import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, apiSend } from "../../../api/client";
import type { components } from "../../../api/schema.gen";

// Batches (src/careeros/ui/routers/batches.py): POST /api/batches with dry_run previews eligibility per job and
// saves nothing; without it the batch is saved (status "ready") and only runs after POST /api/batches/{id}/start.
export type Batch = components["schemas"]["Batch"];
/** runs/batches.py MAX_JOBS. */
export const MAX_JOBS = 500;
export type StopAt = "score" | "prepare" | "fill" | "submit";

/** Per-job stop points (REQ-118); the server lowers them by its caps. */
export type Stops = Record<string, StopAt>;

export function useBatchPreview(jobIds: string[], stopAt: StopAt, stops?: Stops) {
  return useQuery({
    queryKey: ["batch-preview", stopAt, jobIds, stops],
    queryFn: () => apiSend<Batch>("POST", "/api/batches", { job_ids: jobIds, stop_at: stopAt, stops, dry_run: true }),
    enabled: jobIds.length > 0,
    placeholderData: keepPreviousData,
  });
}

/** Save the batch once, then start its driver. A failed start keeps the saved id: retrying the same choices only
 *  calls /start, so it never saves a duplicate; changed choices save a new batch, so the retry runs what you see. */
export function useStartBatch() {
  const [saved, setSaved] = useState<{ key: string; id: string } | null>(null);
  const m = useMutation({
    mutationFn: async (v: { jobIds: string[]; stopAt: StopAt; name?: string; stops?: Stops }) => {
      const key = JSON.stringify(v);
      let id = saved?.key === key ? saved.id : null;
      if (!id) {
        id = (await apiSend<Batch>("POST", "/api/batches", { job_ids: v.jobIds, stop_at: v.stopAt, name: v.name, stops: v.stops })).id!;
        setSaved({ key, id });
      }
      return apiSend<Batch>("POST", `/api/batches/${encodeURIComponent(id)}/start`);
    },
  });
  return { ...m, savedId: saved?.id ?? null };
}

/** One saved batch; the SSE `changed` event (batches: [ids]) invalidates ["batch", id]. */
export function useBatch(id: string | undefined) {
  return useQuery({
    queryKey: ["batch", id],
    queryFn: () => apiFetch<Batch>(`/api/batches/${encodeURIComponent(id!)}`),
    enabled: !!id,
  });
}

export type BatchAction = "start" | "pause" | "cancel" | "retry";

export function useBatchAction(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (action: BatchAction) => {
      const post = (a: BatchAction) => apiSend<Batch>("POST", `/api/batches/${encodeURIComponent(id)}/${a}`);
      const b = await post(action);
      // retry only re-queues; the driver must run again. It may re-queue nothing (hands-off jobs), and /start
      // refuses a done/cancelled batch, so start only when something went back in the queue.
      return action === "retry" && b.retried ? { ...(await post("start")), retried: b.retried } : b;
    },
    onSuccess: (b) => qc.setQueryData(["batch", id], b),
  });
}
