import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
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
