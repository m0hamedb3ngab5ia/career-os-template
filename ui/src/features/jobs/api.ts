import { keepPreviousData, useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, apiFetch, apiSend } from "../../api/client";
import type { JobsPage, JobsTabs, TabKey, TrackerOpen, TrackerSync } from "./types";

export interface ListParams {
  tab: TabKey;
  q: string;
  location: string;
  sort: string;
  limit: number;
}

function listUrl({ tab, q, location, sort, limit }: ListParams, cursor?: string): string {
  const p = new URLSearchParams({ tab, sort, limit: String(limit) });
  if (q) p.set("q", q);
  if (location) p.set("location", location);
  if (cursor) p.set("cursor", cursor);
  return `/api/jobs?${p}`;
}

/** Pages of the live table; "Show more" fetches the next page by `next_cursor`. */
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

export function useJobsTabs(q: string, location = "") {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (location) p.set("location", location);
  const qs = p.toString();
  return useQuery({
    queryKey: ["jobs-tabs", q, location],
    queryFn: () => apiFetch<JobsTabs>(`/api/jobs/tabs${qs ? `?${qs}` : ""}`),
    placeholderData: keepPreviousData,
  });
}

export function useSyncTracker() {
  return useMutation({ mutationFn: () => apiSend<TrackerSync>("POST", "/api/tracker/sync") });
}

export function useOpenTracker() {
  return useMutation({ mutationFn: () => apiSend<TrackerOpen>("POST", "/api/tracker/open") });
}

export type ExportRequest =
  | { job_ids: string[]; columns: string[] }
  | { tab: TabKey; q?: string; location?: string; sort: string; columns: string[] };

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
