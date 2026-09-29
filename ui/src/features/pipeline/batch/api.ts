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

export function useBatchPreview(jobIds: string[], stopAt: StopAt) {
  return useQuery({
    queryKey: ["batch-preview", stopAt, jobIds],
    queryFn: () => apiSend<Batch>("POST", "/api/batches", { job_ids: jobIds, stop_at: stopAt, dry_run: true }),
    enabled: jobIds.length > 0,
    placeholderData: keepPreviousData,
  });
}

/** Save the batch once, then start its driver. A failed start keeps the saved id (`savedId`): retrying only calls
 *  /start, so it never saves a duplicate batch. */
export function useStartBatch() {
  const [savedId, setSavedId] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: async (v: { jobIds: string[]; stopAt: StopAt; name: string }) => {
      let id = savedId;
      if (!id) {
        id = (await apiSend<Batch>("POST", "/api/batches", { job_ids: v.jobIds, stop_at: v.stopAt, name: v.name })).id!;
        setSavedId(id);
      }
      return apiSend<Batch>("POST", `/api/batches/${encodeURIComponent(id)}/start`);
    },
  });
  return { ...m, savedId };
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
      return action === "retry" ? post("start") : b; // retry only re-queues; the driver must run again
    },
    onSuccess: (b) => qc.setQueryData(["batch", id], b),
  });
}
