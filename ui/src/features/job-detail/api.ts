import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { JobDetail, QaRun, StatusReply } from "./types";

export const jobPath = (id: string) => `/api/jobs/${encodeURIComponent(id)}`;
export const fileUrl = (id: string, name: string) =>
  `${jobPath(id)}/files/${name.split("/").map(encodeURIComponent).join("/")}`;

/** Fill the lists and objects the screen maps over, so a partial reply never breaks rendering. */
export function normalize(d: Partial<JobDetail>): JobDetail {
  return {
    ...d,
    job: d.job ?? null,
    posting: d.posting ?? {},
    status: d.status ?? null,
    history: Array.isArray(d.history) ? d.history : [],
    score: d.score ?? null,
    safety: d.safety ?? null,
    qa: d.qa ?? null,
    documents: d.documents ?? [],
    submitted: d.submitted ?? [],
    apply_session: d.apply_session ?? null,
    screenshots: d.screenshots ?? [],
    contacts: d.contacts ?? [],
    log: d.log ?? "",
    override: d.override ?? null,
    registry: d.registry ?? { verified: null, flagged: null },
    outreach: d.outreach ?? null,
    contacts_policy: d.contacts_policy ?? [],
    activity: d.activity ?? [],
  };
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: async () => normalize(await apiFetch<Partial<JobDetail>>(jobPath(id))),
    retry: false,
  });
}

/** A POST to /api/jobs/{id}/<action>. On success the job, the list and the counts refresh at once (SSE also does). */
function useJobWrite<TBody, TReply>(id: string, action: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TBody) => apiSend<TReply>("POST", `${jobPath(id)}/${action}`, body),
    onSuccess: () => {
      for (const queryKey of [["job", id], ["jobs"], ["jobs-tabs"], ["status"]]) void qc.invalidateQueries({ queryKey });
    },
  });
}

export const useSetStatus = (id: string) => useJobWrite<{ status: string; note?: string }, StatusReply>(id, "status");
export const useSetOverride = (id: string) => useJobWrite<{ value: string }, { override: string; queued?: boolean }>(id, "override");
export const useWithdraw = (id: string) => useJobWrite<{ note?: string }, StatusReply>(id, "withdraw");
export const useMarkSubmitted = (id: string) => useJobWrite<{ note?: string }, StatusReply>(id, "submitted");
export const useRerunQa = (id: string) => useJobWrite<undefined, QaRun>(id, "qa");
export const useOpenFolder = (id: string) => useJobWrite<undefined, { opened: boolean }>(id, "open-folder");
export const useVerifyCompany = (id: string) =>
  useJobWrite<{ risk: string; signals: string[]; evidence?: string[]; domain?: string }, unknown>(id, "safety/verify");
export const useFlagCompany = (id: string) =>
  useJobWrite<{ reason?: string; confidence: string; evidence?: string[]; notes?: string }, unknown>(id, "safety/flag");
export const useClearFlag = (id: string) => useJobWrite<{ note?: string }, unknown>(id, "safety/clear");

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong";
}
