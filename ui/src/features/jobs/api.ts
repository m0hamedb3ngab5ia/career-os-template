import { keepPreviousData, useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, apiFetch, apiSend } from "../../api/client";
import type { JobFacets, JobsPage, JobsTabs, TabKey, TrackerOpen, TrackerSync } from "./types";
import { FILTERS, type FilterField, type Filters } from "./urlState";

export interface FilterParams {
  tab: TabKey;
  q: string;
  location: string;
  filters: Filters;
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
