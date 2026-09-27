import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { Meta, StatusSummary } from "./types";

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: () => apiFetch<StatusSummary>("/api/status"),
    staleTime: 30_000,
    retry: false,
  });
}

export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: () => apiFetch<Meta>("/api/meta"),
    staleTime: Infinity, // changes only with config; the `changed` event invalidates it
    retry: false,
  });
}
