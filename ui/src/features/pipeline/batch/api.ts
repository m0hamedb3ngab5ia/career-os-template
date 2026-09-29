import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { apiSend } from "../../../api/client";
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

/** Save the batch, then start its driver. Two calls so a failed start still leaves the saved batch to retry. */
export function useStartBatch() {
  return useMutation({
    mutationFn: async (v: { jobIds: string[]; stopAt: StopAt; name: string }) => {
      const b = await apiSend<Batch>("POST", "/api/batches", { job_ids: v.jobIds, stop_at: v.stopAt, name: v.name });
      return apiSend<Batch>("POST", `/api/batches/${encodeURIComponent(b.id!)}/start`);
    },
  });
}
