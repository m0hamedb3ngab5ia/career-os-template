import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { Board, Filters, StatusResult } from "./types";

export function boardUrl(f: Filters): string {
  const q = new URLSearchParams();
  for (const k of ["tier", "category", "safety", "location"] as const) if (f[k]) q.append(k, f[k]);
  const s = q.toString();
  return s ? `/api/pipeline?${s}` : "/api/pipeline";
}

export function useBoard(f: Filters) {
  return useQuery({
    queryKey: ["pipeline", f],
    queryFn: () => apiFetch<Board>(boardUrl(f)),
    placeholderData: (prev) => prev,
  });
}

/** POST /api/jobs/{id}/status: status.json + tracker (shared with the Jobs table and Job detail). "applied" goes
 * through the confirmed Mark submitted (POST /api/jobs/{id}/submitted); Set status refuses it. */
export function useSetStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { jobId: string; status: string; note?: string }) =>
      v.status === "applied"
        ? apiSend<StatusResult>("POST", `/api/jobs/${encodeURIComponent(v.jobId)}/submitted`, { note: v.note })
        : apiSend<StatusResult>("POST", `/api/jobs/${encodeURIComponent(v.jobId)}/status`, { status: v.status, note: v.note }),
    onSuccess: (r) => {
      for (const key of [["pipeline"], ["jobs"], ["job", r.job_id], ["status"]]) void qc.invalidateQueries({ queryKey: key });
    },
  });
}
