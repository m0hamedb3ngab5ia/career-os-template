import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { components } from "../../api/schema.gen";

export type JobDetail = components["schemas"]["JobDetail"];

export const useJobDetail = (id: string) =>
  useQuery({ queryKey: ["jobs", "detail", id], queryFn: () => apiFetch<JobDetail>(`/api/jobs/${encodeURIComponent(id)}`) });

export type JobPipeline = components["schemas"]["PipelineState"];

/** Whether the next apply run only stages the form (auto-submit off, or Tier A) or may submit by itself. */
export const useJobPipeline = (id: string) =>
  useQuery({ queryKey: ["jobs", "pipeline", id], queryFn: () => apiFetch<JobPipeline>(`/api/jobs/${encodeURIComponent(id)}/pipeline`) });

export const fileUrl = (id: string, name: string) => `/api/jobs/${encodeURIComponent(id)}/files/${name}`;

/** A job file as text (résumé.txt, cover letter). Never JSON-parsed. */
export function useJobText(id: string, name: string | undefined) {
  return useQuery({
    queryKey: ["jobs", "text", id, name],
    enabled: !!name,
    queryFn: async () => {
      const res = await fetch(fileUrl(id, name!));
      if (!res.ok) throw new Error(`Couldn’t load ${name}`);
      return res.text();
    },
  });
}

/** Approve = mark ready for /apply-job (status queued, ticked). Skip = status skipped. Neither submits anything. */
export function useDecide(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (action: "approve" | "skip") => {
      await apiSend("POST", `/api/jobs/${encodeURIComponent(id)}/status`, {
        status: action === "approve" ? "queued" : "skipped",
        note: action === "approve" ? "approved in inspector" : "skipped in inspector",
      });
      if (action === "approve") await apiSend("POST", "/api/jobs/select", { ids: [id], selected: true });
    },
    onSuccess: () => qc.invalidateQueries(),
  });
}
