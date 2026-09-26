import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { StatusSummary } from "./types";

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: () => apiFetch<StatusSummary>("/api/status"),
    staleTime: 30_000,
    retry: false,
  });
}
