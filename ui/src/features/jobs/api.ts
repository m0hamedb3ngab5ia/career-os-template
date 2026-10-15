import { keepPreviousData, useInfiniteQuery, useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { ApiError, apiFetch, apiSend } from "../../api/client";
import type { JobFacets, JobListItem, JobsPage, JobsTabs, TabKey, TrackerOpen, TrackerSync, ViewKey } from "./types";
import { runKeys } from "../runs/api";
import type { RunDetail } from "../runs/types";
import { FILTERS, type FilterField, type Filters } from "./urlState";

export interface FilterParams {
  tab: TabKey;
  q: string;
  location: string;
  filters: Filters;
  /** Count filter values over these rows instead of asking the server (the Start pipeline review table). */
  rows?: JobListItem[];
}

export interface ListParams extends FilterParams {
  sort: string;
  limit: number;
}

/** Column filters as query pairs: repeated `<param>` for values, `<field>_min/_max` for numbers, `<base>_from/_to`
 *  for dates (found_at -> found_from). Also the shape of the export body's filter keys. */
export function filterPairs(filters: Filters): [string, string][] {
  const out: [string, string][] = [];
  for (const [field, f] of Object.entries(filters) as [FilterField, Filters[FilterField]][]) {
    if (!f) continue;
    const spec = FILTERS[field];
    if (f.kind === "values") {
      const key = "param" in spec ? spec.param : field;
      for (const v of f.values) out.push([key, v]);
    } else {
      const [lo, hi] = spec.kind === "date" ? ["from", "to"] : ["min", "max"];
      const base = spec.kind === "date" ? field.replace(/_at$/, "") : field;
      if (f.min) out.push([`${base}_${lo}`, f.min]);
      if (f.max) out.push([`${base}_${hi}`, f.max]);
    }
  }
  return out;
}

function baseParams({ tab, q, location, filters }: FilterParams): URLSearchParams {
  const p = new URLSearchParams({ tab });
  if (q) p.set("q", q);
  if (location) p.set("location", location);
  for (const [k, v] of filterPairs(filters)) p.append(k, v);
  return p;
}

function listUrl(params: ListParams, cursor?: string): string {
  const p = baseParams(params);
  p.set("sort", params.sort);
  p.set("limit", String(params.limit));
  if (cursor) p.set("cursor", cursor);
  return `/api/jobs?${p}`;
}

/** Pages of the live table; the pager fetches the next page by `next_cursor` when it runs past the loaded rows. */
export function useJobsList(params: ListParams, enabled = true) {
  return useInfiniteQuery({
    queryKey: ["jobs", "list", params],
    queryFn: ({ pageParam }) => apiFetch<JobsPage>(listUrl(params, pageParam)),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useJobsTabs(params: FilterParams) {
  const p = baseParams(params);
  p.delete("tab");
  const qs = p.toString();
  return useQuery({
    queryKey: ["jobs-tabs", qs],
    queryFn: () => apiFetch<JobsTabs>(`/api/jobs/tabs${qs ? `?${qs}` : ""}`),
    placeholderData: keepPreviousData,
  });
}

/** Distinct values of one column with counts under every other active filter (the header filter menu). */
export function useJobFacets(field: FilterField, params: FilterParams, enabled: boolean) {
  const { [field]: _own, ...others } = params.filters;
  const p = baseParams({ ...params, filters: others });
  p.set("field", field);
  const qs = p.toString();
  return useQuery({
    queryKey: ["jobs-facets", qs],
    queryFn: () => apiFetch<JobFacets>(`/api/jobs/facets?${qs}`),
    enabled,
    placeholderData: keepPreviousData,
  });
}

/** The column filters as export body keys (same names as the query params; lists for value filters). */
export function exportFilters(filters: Filters): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {};
  for (const [k, v] of filterPairs(filters)) {
    const cur = out[k];
    if (cur === undefined) out[k] = FILTERS[k as FilterField]?.kind === "values" || k === "location_in" ? [v] : v;
    else if (Array.isArray(cur)) cur.push(v);
  }
  return out;
}

export function useSyncTracker() {
  return useMutation({ mutationFn: () => apiSend<TrackerSync>("POST", "/api/tracker/sync") });
}

export function useOpenTracker() {
  return useMutation({ mutationFn: () => apiSend<TrackerOpen>("POST", "/api/tracker/open") });
}

export type ExportRequest =
  | { job_ids: string[]; columns: string[] }
  | ({ tab: TabKey; q?: string; location?: string; sort: string; columns: string[] } & Record<string, unknown>);

function filenameFrom(disposition: string | null): string {
  const m = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return m?.[1] ? decodeURIComponent(m[1]) : "careeros-jobs.xlsx";
}

/** POST /api/jobs/export streams an .xlsx; hand it to the browser as a download. Returns the file name. */
export async function exportJobs(body: ExportRequest): Promise<string> {
  const res = await fetch("/api/jobs/export", {
    method: "POST",
    headers: { "X-CareerOS": "1", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Export failed (${res.status})`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail, null);
  }
  const name = filenameFrom(res.headers.get("content-disposition"));
  const url = URL.createObjectURL(await res.blob());
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
  return name;
}

export function useExportJobs() {
  return useMutation({ mutationFn: exportJobs });
}

/** REQ-104: bulk tick/untick for prepare/apply runs; the list refreshes at once (SSE also does). */
export function useSelectJobs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { ids: string[]; selected: boolean }) => apiSend("POST", "/api/jobs/select", body),
    // Returned, so the mutation stays pending (the tick stays optimistic) until the list has refetched.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export interface ScoreFailure { ids: string[]; message: string }
interface ScoreState { runs: { runId: string; ids: string[] }[]; starting: string[]; failure: ScoreFailure | null }
const SCORE_KEY = ["scoreJobs"];
const NO_SCORE: ScoreState = { runs: [], starting: [], failure: null };

/** REQ-137 Score now: one score run over exactly these jobs; never ticks them. Owns the "Scoring…" state: a job
 * stays scoring until its run ends (polled, like useStepRun), then the list refreshes; a job the run did not score
 * (start refused, run failed or gone) comes back in `failure` so the caller can offer Retry. State lives in the
 * query cache, so leaving the page keeps watching. */
export function useScoreJobs() {
  const qc = useQueryClient();
  const state = useQuery({ queryKey: SCORE_KEY, queryFn: () => NO_SCORE, enabled: false, initialData: NO_SCORE,
    staleTime: Infinity, gcTime: Infinity }).data;
  const edit = (f: (s: ScoreState) => ScoreState) => qc.setQueryData<ScoreState>(SCORE_KEY, (s) => f(s ?? NO_SCORE));
  const polls = useQueries({
    queries: state.runs.map((r) => ({
      queryKey: runKeys.detail(r.runId),
      queryFn: () => apiFetch<RunDetail>(`/api/runs/${encodeURIComponent(r.runId)}`),
      refetchInterval: 1000,
      retry: 3,
    })),
  });
  useEffect(() => {
    state.runs.forEach((r, i) => {
      const p = polls[i];
      const run = p?.data;
      if (!p || (!p.isError && (!run || run.state === "running"))) return;
      const ok = new Set((run?.attempts ?? []).filter((a) => a.outcome === "ok").map((a) => a.job_id));
      const failed = r.ids.filter((id) => !ok.has(id));
      const why = run?.attempts.find((a) => failed.includes(a.job_id ?? "") && a.detail)?.detail || run?.detail
        || (p.error instanceof Error ? p.error.message : "") || `Scoring stopped${run?.stop_reason ? ` (${run.stop_reason})` : ""}`;
      edit((s) => ({ ...s, runs: s.runs.filter((x) => x.runId !== r.runId),
        failure: failed.length ? { ids: failed, message: why } : s.failure }));
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    });
  });
  const start = useMutation({
    mutationFn: (ids: string[]) => apiSend<{ run_id: string; kind: string }>("POST", "/api/jobs/score", { job_ids: ids }),
    onMutate: (ids) => edit((s) => ({ ...s, failure: null, starting: [...s.starting, ...ids] })),
    onSuccess: (r, ids) => edit((s) => ({ ...s, starting: s.starting.filter((x) => !ids.includes(x)),
      runs: [...s.runs, { runId: r.run_id, ids }] })),
    onError: (e, ids) => edit((s) => ({ ...s, starting: s.starting.filter((x) => !ids.includes(x)),
      failure: { ids, message: e instanceof Error ? e.message : "Something went wrong" } })),
  });
  const scoring = new Set([...state.starting, ...state.runs.flatMap((r) => r.ids)]);
  return { score: start.mutate, isPending: start.isPending, scoring, failure: state.failure };
}

export interface UiState {
  tour_done?: boolean;
  jobs_view?: ViewKey;
}

/** data/ui_state.json via GET/PUT /api/ui-state (shared with the first-run tour; PUT merges). */
export function useUiState() {
  return useQuery({ queryKey: ["ui-state"], queryFn: () => apiFetch<UiState>("/api/ui-state"), staleTime: Infinity });
}

export function useRememberView() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobs_view: ViewKey) => apiSend<UiState>("PUT", "/api/ui-state", { jobs_view }),
    onSuccess: (s) => qc.setQueryData(["ui-state"], s),
  });
}

/** Board drag: POST /api/jobs/{id}/status. The server's refusal text rides on the thrown error. */
export function useMoveJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { jobId: string; status: string }) =>
      apiSend<{ job_id: string }>("POST", `/api/jobs/${encodeURIComponent(v.jobId)}/status`, { status: v.status }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}
