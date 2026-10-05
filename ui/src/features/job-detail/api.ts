import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiSend } from "../../api/client";
import type { JobDetail, PipelineStarted, PipelineState, StatusReply } from "./types";

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
    other_files: d.other_files ?? [],
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
export const useOpenFolder = (id: string) => useJobWrite<undefined, { opened: boolean }>(id, "open-folder");
export const useVerifyCompany = (id: string) =>
  useJobWrite<{ risk: string; signals: string[]; evidence?: string[]; domain?: string }, unknown>(id, "safety/verify");
export const useFlagCompany = (id: string) =>
  useJobWrite<{ reason?: string; confidence: string; evidence?: string[]; notes?: string }, unknown>(id, "safety/flag");
export const useClearFlag = (id: string) => useJobWrite<{ note?: string }, unknown>(id, "safety/clear");

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong";
}

// --- the job's pipeline (GET/POST /api/jobs/{id}/pipeline) --------------------------------------------------------

export const pipelineKey = (id: string) => ["job", id, "pipeline"] as const;

/** The stage, next action and running run; `poll` refetches every second (right after a start, until the run
 * record exists and `active_run_id` names it). Under the ["job", id] prefix, so every job write refreshes it. */
export function usePipeline(id: string, poll = false) {
  return useQuery({
    queryKey: pipelineKey(id),
    queryFn: () => apiFetch<PipelineState>(`${jobPath(id)}/pipeline`),
    refetchInterval: poll ? 1000 : false,
    retry: false,
  });
}

/** POST /jobs/{id}/failures/reset: clear the job's run failure count (a job out of retries runs again) and resolve
 * its out-of-retries Action Items. */
export function useResetFailures(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kind?: string | null) =>
      apiSend<{ job_id: string; cleared: string[]; resolved: string[] }>("POST", `${jobPath(id)}/failures/reset`,
        kind ? { kind } : {}),
    onSettled: () => {
      for (const queryKey of [pipelineKey(id), ["job", id], ["actions"], ["status"]]) void qc.invalidateQueries({ queryKey });
    },
  });
}

export function useStartPipeline(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { action: PipelineState["next_action"]; force?: boolean }) =>
      apiSend<PipelineStarted>("POST", `${jobPath(id)}/pipeline`, body),
    onSettled: () => {
      for (const queryKey of [["job", id], ["jobs"], ["jobs-tabs"], ["status"], ["runs"]]) void qc.invalidateQueries({ queryKey });
    },
  });
}

/** The staged form's browser tab: alive ("open"), gone ("needs_refill") or never filled ("none"). Polled so a
 * tab closed by sleep or a crash is never shown as ready. */
export interface ApplicationTab {
  tab: "open" | "needs_refill" | "none";
  submitted: boolean;
  can_fill: boolean;
  marked_applied?: boolean;
  filling?: boolean;
  fill_error?: string;
  fill_log?: string;
  fields_left?: string[];
}
export function useApplicationTab(id: string) {
  return useQuery({
    queryKey: ["job", id, "application"],
    queryFn: () => apiFetch<ApplicationTab>(`${jobPath(id)}/application`),
    refetchInterval: (q) => (q.state.data?.filling ? 3_000 : 15_000),
  });
}
export const useOpenApplication = (id: string) =>
  useJobWrite<{ refill: true } | undefined, { action: "focused" | "filling"; log?: string }>(id, "application/open");

/** REQ-105/106: the job's fill plan (null before Preview fill) and why it can't be filled yet. */
export interface FillField {
  field_id: string;
  label: string;
  type: string;
  value: unknown;
  source: string | null;
  required?: boolean;
  skipped?: boolean;
  options?: string[];
}
export interface FillPlanReply {
  plan: { fields: FillField[] } | null;
  problems: string[];
}
export const useFillPlan = (id: string) =>
  useQuery({ queryKey: ["job", id, "fill-plan"], queryFn: () => apiFetch<FillPlanReply>(`${jobPath(id)}/fill-plan`) });
export const useMakeFillPlan = (id: string) => useJobWrite<undefined, FillPlanReply>(id, "fill-plan");
export const useEditFillField = (id: string, fieldId: string) =>
  useJobWrite<{ value?: string; skip?: boolean; save?: boolean }, { field: FillField; saved: boolean; problems: string[] }>(
    id,
    `fill-plan/fields/${encodeURIComponent(fieldId)}`,
  );
